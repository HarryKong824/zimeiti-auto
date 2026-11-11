"""提供商抽象层。

所有 LLM 聊天和图片生成都走这里，按 config/providers.yaml 路由。
好处：换提供商只改 YAML，不用改代码；密钥统一从环境变量读。

兼容旧配置：如果提供商专属 env_key 没配，会回退到 OPENAI_BASE_URL / OPENAI_API_KEY。
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import time
from pathlib import Path

import requests

from .config import DATA, env, load_yaml, proxy

PROVIDERS = load_yaml("providers.yaml")
COST_LOG = DATA / "costs.jsonl"


def _post_with_retry(
    url: str, headers: dict, payload: dict, timeout: int, retries: int = 2
) -> requests.Response:
    """POST 带重试：网络异常、5xx、429 才重试；4xx 直接抛。"""
    last: Exception | None = None
    for attempt in range(retries + 1):
        resp = None
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout, proxies=proxy())
        except requests.RequestException as exc:
            last = exc
        if resp is not None:
            if resp.status_code < 500 and resp.status_code != 429:
                resp.raise_for_status()
                return resp
            last = requests.HTTPError(f"HTTP {resp.status_code}")
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise last or RuntimeError("请求失败")


def _log_cost(kind: str, provider: str, cost: float) -> None:
    """记录一次 API 调用花费到 data/costs.jsonl。"""
    try:
        COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": dt.datetime.now().isoformat(),
                "kind": kind,
                "provider": provider,
                "cost": round(cost, 6),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------- 通用解析 ----------

def _cfg(kind: str, name: str) -> dict:
    """取某个提供商的配置。name 为空时取 default（LLM 还会看 LLM_PROVIDER 环境变量）。"""
    section = PROVIDERS.get(kind, {})
    if not name:
        if kind == "llm":
            name = env("LLM_PROVIDER") or section.get("default", "")
        else:
            name = section.get("default", "")
    return dict(section.get(name, {}))


def _resolve_credentials(cfg: dict) -> tuple[str, str]:
    """返回 (base_url, api_key)。优先用提供商专属 env_key，否则回退 OPENAI_*。"""
    base_url = cfg.get("base_url") or env("OPENAI_BASE_URL")
    env_key = cfg.get("env_key", "")
    api_key = env(env_key) if env_key else env("OPENAI_API_KEY")
    return base_url, api_key


def _budget_ok() -> bool:
    """预算熔断：本月累计花费已超 budget 则返回 False。

    熔断时 chat() 返回空 dict → 文案/分镜降级规则模式；
    generate_image() 返回 None → 出图自动降级占位图。
    用户不会被静默扣费。
    """
    info = monthly_cost()
    if info["remaining"] <= 0:
        print(f"⚠️ 本月预算已用完（¥{info['total']:.2f} / ¥{info['budget']:.0f}），自动降级。")
        return False
    # 剩不到 ¥5 也提前提醒，避免最后一次调用刚好花完
    if info["remaining"] < 5 and not getattr(_budget_ok, "_warned", False):
        print(f"💡 本月预算剩 ¥{info['remaining']:.2f}，注意控制调用量。")
        _budget_ok._warned = True
    return True


# ---------- LLM 聊天 ----------

def chat(
    messages: list[dict],
    *,
    provider: str = "",
    model: str = "",
    temperature: float = 0.8,
    response_format: dict | None = None,
    timeout: int = 120,
) -> dict:
    """调用 LLM 聊天接口，返回解析后的 JSON。失败或超预算返回空字典。

    支持所有 OpenAI 兼容接口（DeepSeek / OpenAI / Groq / 硅基流动 / Ollama）。
    """
    if not _budget_ok():
        return {}

    cfg = _cfg("llm", provider)
    base_url, api_key = _resolve_credentials(cfg)
    if not base_url or not api_key:
        return {}

    model = model or cfg.get("model") or env("LLM_MODEL", "deepseek-chat")
    payload: dict = {"model": model, "temperature": temperature, "messages": messages}
    if response_format:
        payload["response_format"] = response_format

    try:
        resp = _post_with_retry(
            f"{base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            payload,
            timeout,
        )
        body = resp.json()
        # 估算花费：按返回的 token 数 × 单价
        usage = body.get("usage", {}) or {}
        total_tokens = usage.get("total_tokens", 0)
        cost_per_1k = float(cfg.get("cost", 0))
        if total_tokens and cost_per_1k:
            _log_cost("llm", cfg.get("name", provider or "llm"), total_tokens * cost_per_1k / 1000)
        return json.loads(body["choices"][0]["message"]["content"])
    except Exception:
        return {}


# ---------- 图片生成 ----------

def generate_image(
    prompt: str,
    out_path: Path,
    *,
    provider: str = "",
    size: str = "",
    timeout: int = 120,
) -> Path | None:
    """调用图片生成 API，保存到 out_path。成功返回路径，失败或超预算返回 None。

    支持所有 OpenAI 兼容的 /v1/images/generations 接口
    （SiliconFlow FLUX / DALL·E 3 / SDXL 等）。
    自动处理 b64_json 和 url 两种返回格式。
    """
    if not _budget_ok():
        return None

    cfg = _cfg("image", provider)
    base_url, api_key = _resolve_credentials(cfg)
    model = cfg.get("model", "")
    if not base_url or not api_key or not model:
        return None

    size = size or cfg.get("size", "1024x1024")
    resp_format = cfg.get("response_format", "b64_json")

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": resp_format,
    }

    try:
        resp = _post_with_retry(
            f"{base_url.rstrip('/')}/images/generations",
            {"Authorization": f"Bearer {api_key}"},
            payload,
            timeout,
        )
        data = resp.json()["data"][0]

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if "b64_json" in data:
            out_path.write_bytes(base64.b64decode(data["b64_json"]))
        elif "url" in data:
            img = None
            for attempt in range(3):
                try:
                    img = requests.get(data["url"], timeout=timeout, proxies=proxy())
                    img.raise_for_status()
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
            out_path.write_bytes(img.content)
        else:
            return None

        # 记录图片花费（按张计费）
        img_cost = float(cfg.get("cost", 0))
        if img_cost:
            _log_cost("image", cfg.get("name", provider or "image"), img_cost)
        return out_path
    except requests.HTTPError as exc:
        # 关键错误码要明确告诉用户，不能静默降级
        status = exc.response.status_code if exc.response else 0
        if status in (401, 403):
            print(f"🔑 图片 API 认证失败（HTTP {status}），请检查密钥。")
        elif status == 402:
            print(f"💸 图片 API 余额不足（HTTP 402），请在 SiliconFlow 充值后再跑。")
        else:
            print(f"⚠️ 图片 API 调用失败（HTTP {status}），降级占位图。")
        return None
    except Exception:
        return None


# ---------- 工具函数 ----------

def image_provider_name(name: str) -> str:
    """把 run.py 的 --provider 值映射到 providers.yaml 里的 key。

    - placeholder / comfyui → 原样（这两个不走 API）
    - api → 取 image.default
    - 其他 → 原样（如 siliconflow、dalle3）
    """
    if name in ("placeholder", "comfyui"):
        return name
    if name == "api":
        return PROVIDERS.get("image", {}).get("default", "siliconflow")
    return name


def is_available(kind: str, name: str) -> bool:
    """检查某提供商是否配了密钥（仅判断能不能调，不验证连通性）。"""
    cfg = _cfg(kind, name)
    _, api_key = _resolve_credentials(cfg)
    if kind == "image" and name in ("placeholder", "comfyui"):
        return True
    return bool(api_key)


def monthly_cost(budget: float | None = None) -> dict:
    """统计本月 API 花费。返回 {total, by_provider, budget, remaining}。"""
    if budget is None:
        budget = float(PROVIDERS.get("budget", 500))
    if not COST_LOG.exists():
        return {"total": 0, "by_provider": {}, "budget": budget, "remaining": budget}

    now = dt.datetime.now()
    by_provider: dict[str, float] = {}
    total = 0.0
    for line in COST_LOG.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            t = dt.datetime.fromisoformat(entry["time"])
            if t.year != now.year or t.month != now.month:
                continue
            cost = float(entry.get("cost", 0))
            prov = entry.get("provider", "unknown")
            by_provider[prov] = by_provider.get(prov, 0) + cost
            total += cost
        except Exception:
            continue
    return {
        "total": round(total, 2),
        "by_provider": {k: round(v, 2) for k, v in by_provider.items()},
        "budget": budget,
        "remaining": round(budget - total, 2),
    }
