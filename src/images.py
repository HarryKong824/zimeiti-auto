from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from . import fonts, library, providers
from .config import STYLE, env

CFG = STYLE
W = int(CFG.get("video", {}).get("width", 1080))
H = int(CFG.get("video", {}).get("height", 1920))
ACCENT = CFG.get("style", {}).get("accent", "#4F8CFF")
TEXT = CFG.get("style", {}).get("text", "#F2F5FA")
MUTED = CFG.get("style", {}).get("muted", "#8A94A6")
BGS = CFG.get("style", {}).get("bg", ["#0B0F17"])
FONT_BOLD = fonts.resolve("bold", CFG.get("style", {}).get("font_bold", ""))
FONT_REGULAR = fonts.resolve("regular", CFG.get("style", {}).get("font_regular", ""))
BRAND = CFG.get("style", {}).get("brand", "")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (path, FONT_REGULAR):
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def _gradient(bg: str, width: int | None = None, height: int | None = None) -> Image.Image:
    width = width or W
    height = height or H
    base = Image.new("RGB", (1, 1), bg).getpixel((0, 0))
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        factor = 0.55 + 0.45 * (1 - y / height)
        draw.line([(0, y), (width, y)], fill=tuple(int(c * factor) for c in base))
    return img


# 中文断行禁则：尽量断在这些字之后（助词/代词/介词后是自然停顿）。
# 刻意不含「就、也、都、才、又、能、会、要」这类副词——它们后面紧跟动词，
# 断在它们之后会出现「…说白了就 / 是信息差」这种把词劈开的行。
_SOFT_TAIL = set("的地得了着过是把你这那您他她它我个们上下来去对从被让给")


def _break_point(line: str, cut: int) -> int:
    """贪心断点落在词中间时，往回找一个更自然的停顿位置。"""
    if cut <= 0 or cut >= len(line):
        return cut
    for back in range(cut, max(cut - 4, 0), -1):
        if line[back - 1] in _SOFT_TAIL:
            # 不把英文单词或数字切开
            while 0 < back < len(line) and line[back - 1].isascii() and line[back - 1].isalnum() \
                    and line[back].isascii() and line[back].isalnum():
                back += 1
            return back
    return cut


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, rest = [], text
    while rest:
        current = ""
        for char in rest:
            trial = current + char
            if current and draw.textlength(trial, font=font) > max_width:
                break
            current = trial
        if len(current) < len(rest):
            current = current[: _break_point(current, len(current))]
        lines.append(current)
        rest = rest[len(current):]
    # 末行只剩一两个字很难看，从上一行挪几个字下来
    if len(lines) > 1 and len(lines[-1]) <= 2:
        shift = min(3 - len(lines[-1]), len(lines[-2]) - 2)
        if shift > 0:
            lines[-1] = lines[-2][-shift:] + lines[-1]
            lines[-2] = lines[-2][:-shift]
    return lines


def _placeholder(shot: dict, out_path: Path) -> None:
    """零依赖占位图：把 8 个模板画出可看的版式，用于跑通链路。"""
    rnd = _seed(str(shot.get("index")) + shot.get("keyword", ""))
    img = _gradient(BGS[rnd % len(BGS)])
    draw = ImageDraw.Draw(img)
    template = shot.get("template", "title")
    keyword = shot.get("keyword") or shot.get("text", "")
    # 封面/字卡只放短句，取第一个分句，避免整段话糊在画面上
    keyword = re.split(r"[，。！？；、,.!?;:：]", keyword.strip())[0][:14] or keyword[:14]

    # 顶部品牌条
    draw.text((72, 80), BRAND, font=_font(FONT_REGULAR, 34), fill="#6E7A8F")
    draw.line([(72, 132), (72 + 120, 132)], fill=ACCENT, width=4)
    draw.text((W - 190, 74), f"{shot.get('index', 0) + 1:02d}", font=_font(FONT_BOLD, 110), fill="#1B2230")

    graphic_top = int(H * 0.30)
    text_top = int(H * 0.63)

    if template == "person":
        cx, cy, r = W // 2, graphic_top, 140
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#222B3A")
        draw.rounded_rectangle([cx - 230, cy + r + 36, cx + 230, cy + r + 500], radius=70, fill="#1C2432")
    elif template == "object":
        draw.rounded_rectangle([W // 2 - 300, graphic_top - 260, W // 2 + 300, graphic_top + 260], radius=44, outline=ACCENT, width=6)
        draw.rounded_rectangle([W // 2 - 210, graphic_top - 180, W // 2 + 210, graphic_top + 180], radius=28, fill="#1A2230")
    elif template == "chart":
        base_y = graphic_top + 300
        for i in range(6):
            height = 110 + ((rnd >> (i * 3)) % 380)
            x0 = 170 + i * 130
            color = ACCENT if i % 2 == 0 else "#2E3A4F"
            draw.rounded_rectangle([x0, base_y - height, x0 + 90, base_y], radius=12, fill=color)
        draw.line([(140, base_y + 10), (W - 140, base_y + 10)], fill="#2A3446", width=3)
    elif template == "map":
        points = [(220, graphic_top - 280), (420, graphic_top - 40), (330, graphic_top + 240), (620, graphic_top + 380), (820, graphic_top + 100), (760, graphic_top - 200)]
        draw.line(points, fill=ACCENT, width=8, joint="curve")
        for point in points:
            draw.ellipse([point[0] - 18, point[1] - 18, point[0] + 18, point[1] + 18], fill=ACCENT)
    elif template == "split":
        draw.rectangle([0, 0, W // 2 - 6, int(H * 0.56)], fill="#141B26")
        draw.rectangle([W // 2 + 6, 0, W, int(H * 0.56)], fill="#101720")
        draw.line([(W // 2, 0), (W // 2, int(H * 0.56))], fill=ACCENT, width=6)
    elif template == "quote":
        draw.text((90, 250), "“", font=_font(FONT_BOLD, 300), fill="#2C3A52")
        text_top = int(H * 0.48)
    elif template == "transition":
        for i in range(-4, 14):
            x = i * 130
            draw.polygon([(x, H), (x + 70, H), (x + 320, 0), (x + 250, 0)], fill="#141C28")
        text_top = int(H * 0.55)

    # 画面文字只留给大字卡/引语卡，其余模板只放图形。
    # 否则每镜都把同一句话再糊一遍在中间，与底部字幕重复。
    if template in ("title", "quote"):
        size = 120 if template == "title" else 84
        font = _font(FONT_BOLD, size)
        lines = _wrap(draw, keyword, font, W - 220)[:3]
        total = len(lines) * (size + 24)
        y = int(H * 0.5) - total // 2 if template == "title" else text_top
        for line in lines:
            width = draw.textlength(line, font=font)
            draw.text(((W - width) / 2, y), line, font=font, fill=TEXT)
            y += size + 24

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def _comfyui(shot: dict, out_path: Path) -> None:
    base = env("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    ckpt = env("COMFYUI_CHECKPOINT")
    if not ckpt:
        raise RuntimeError("未配置 COMFYUI_CHECKPOINT")

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": shot["prompt"], "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "text, watermark, logo, lowres, blurry", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 1344, "batch_size": 1}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": _seed(shot.get("keyword", "")) % 2**31,
                "steps": 6,
                "cfg": 2.0,
                "sampler_name": "dpmpp_sde",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "shot", "images": ["6", 0]}},
    }

    resp = requests.post(f"{base}/prompt", json={"prompt": workflow}, timeout=30)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    for _ in range(300):
        history = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()
        if prompt_id in history:
            images = history[prompt_id]["outputs"]["7"]["images"]
            info = images[0]
            data = requests.get(
                f"{base}/view",
                params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": "output"},
                timeout=60,
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data.content)
            return
        time.sleep(2)
    raise TimeoutError(f"ComfyUI 出图超时：{shot.get('index')}")


def _api(shot: dict, out_path: Path, provider_name: str, size: str | None = None) -> bool:
    """调 API 出图。成功返回 True，失败返回 False（由调用方降级占位图）。"""
    prompt = shot.get("prompt", "")
    if not prompt:
        return False
    result = providers.generate_image(prompt, out_path, provider=provider_name, size=size)
    return result is not None


def render(shot: dict, out_path: Path, provider: str = "placeholder", api_size: str | None = None) -> Path:
    """provider 可以是：placeholder / comfyui / api / siliconflow / dalle3 ...

    素材库命中图片 → 复制 png；命中视频 → 复制 mp4，由 compose 按视频片段处理。
    """
    name = providers.image_provider_name(provider)

    # 1. 优先用素材库（图或视频，复用省钱）
    keywords = [shot.get("keyword", ""), shot.get("template", "")]
    keywords = [k for k in keywords if k]
    lib_asset = library.pick_asset(keywords) if keywords else None
    if lib_asset:
        import shutil

        out_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = lib_asset.suffix.lower()
        if suffix in library.VIDEO_EXTS:
            # 视频素材：改扩展名复制，避免 png 名装视频
            video_out = out_path.with_suffix(".mp4")
            shutil.copy2(lib_asset, video_out)
            return video_out
        shutil.copy2(lib_asset, out_path)
        return out_path

    # 2. 否则按提供商出图
    if name == "comfyui":
        _comfyui(shot, out_path)
    elif name != "placeholder":
        if not _api(shot, out_path, name, size=api_size):
            _placeholder(shot, out_path)
    else:
        _placeholder(shot, out_path)
    return out_path


def render_all(
    shots: list[dict], job_dir: Path, provider: str = "placeholder",
    video_size: tuple[int, int] | None = None,
) -> list[Path]:
    """video_size=(w,h) 用来推算 API 出图尺寸，与视频同比例。"""
    image_dir = job_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    # 并发上限：本地占位图很快，API/ComfyUI 受服务端限制，统一 4
    max_workers = 4

    # 从视频尺寸算 API 出图 size 字符串（如 "1024x1792"）
    api_size = _api_size(video_size) if video_size else None

    paths: list[Path | None] = [None] * len(shots)

    def _one(shot: dict) -> tuple[int, Path]:
        path = image_dir / f"shot_{shot['index']:03d}.png"
        actual = render(shot, path, provider, api_size=api_size)
        return shot["index"], actual

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_one, shot) for shot in shots]
        for fut in as_completed(futures):
            idx, path = fut.result()
            paths[idx] = path

    return [p for p in paths if p is not None]


def _api_size(video_size: tuple[int, int]) -> str | None:
    """把视频宽高转成 API 支持的 size 字符串。

    SiliconFlow/Z-Image 支持 {宽}x{高} 格式，
    且两边要是 32 的倍数。统一缩到最长边 ~1280（避免太贵）。
    """
    w, h = video_size
    scale = 1280 / max(w, h)
    w2 = int(w * scale)
    h2 = int(h * scale)
    # 对齐到 32
    w2 = (w2 // 32) * 32
    h2 = (h2 // 32) * 32
    return f"{w2}x{h2}"
