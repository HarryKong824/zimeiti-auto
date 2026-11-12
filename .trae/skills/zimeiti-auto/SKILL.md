---
name: zimeiti-auto
description: 自媒体短视频全流程自动化流水线。用户要剪视频、做短视频、选题、生成口播稿、发布到抖音小红书B站视频号X、或查看数据周报时使用。触发词：剪视频、做短视频、选题、口播稿、发布、上传、周报、账号数据、自动化。不要用于和这个项目无关的通用编程任务。
---

# 自媒体全自动化

一个人的短视频流水线：选题 → 口播稿 → 转写 → 选段 → 分镜 → 出图 → 合成 → 打包 → 填表上传 → 数据周报

**用户只做两件事：录视频、点发布按钮。** 其余都交给这里的脚本。

---

## 工作目录

**项目根 = `E:\自媒体全自动化`**（`run.py` 所在目录）。所有命令都在这个目录执行，先 `cd E:\自媒体全自动化` 再跑 `python run.py ...`。

环境：Python 3.10+、ffmpeg（必须在 PATH）、`pip install -r requirements.txt`。

### 首次跑之前

第一次接手任何操作，先在 run.py 所在目录跑：

```bash
python run.py --check
```

输出 `✓` 正常、`!` 警告、`✗` 致命。有 `✗` 必须先修。

想先看看成品长什么样（零成本、零额度、零素材）：

```bash
python run.py --demo
```

### 首次配置（只问一次）

检查 `config/profile.yaml` 是否已有用户选择。如果没有（或用户说"换方向/change direction"），依次问 3 个问题，把答案写进 `config/profile.yaml` 和 `.env`：

**问题 1：平台**
> 你要发哪些平台？国内（抖音/小红书/B站/视频号）、海外（X）、还是全部？

→ 写入 `profile.yaml` 的 `platforms`（key：douyin / xhs / bilibili / shipinhao / x）

**问题 2：LLM 模型（按预算）**
> 口播稿和文案用哪个模型？
> - DeepSeek（约 ¥1/百万token，中文好）← 推荐
> - OpenAI gpt-4o-mini（约 ¥1.5/百万token）
> - Groq（免费额度，速度快）

→ 写入 `profile.yaml` 的 `llm_provider`，并在 `.env` 填对应密钥

**问题 3：出图方式**
> 画面怎么来？
> - placeholder（几何占位图，零成本，默认）← 推荐起步
> - SiliconFlow Z-Image-Turbo（**¥0.10/张**，25 镜≈¥2.50/轮）
> - ComfyUI 本地（免费，需显卡）

→ 写入 `profile.yaml` 的 `image_provider`，并在 `.env` 填密钥

**问完后**：写入配置后告诉用户"下次不再问"。除非用户主动说"换方向"，不要再重复询问。

---

## 五个主命令

### 1. 选题

```bash
python run.py --topics
python run.py --topics --top-n 10
```

抓 B站/知乎/百度 + Reddit/HackerNews，打分，出今日清单。输出 `data/topics/日期.md`。

### 2. 口播稿

**动笔前先读 `references/口播稿标准.md`**，那是硬标准，不是参考建议。核心五条：

1. 主角是观众，不是公司。案例只当证据，占全篇不超过三分之一。
2. 第一句是观众的动作或处境，10–14 字。
3. 每句不超过 18 字，每 5–8 秒一个信息点，40%–60% 处必须有一个短句转折。
4. 给三步能立刻做的动作，每步一个动作，不空喊。
5. 结尾给动作或立场，不给金句、不求关注、不写总结句。

写完用标准文件第 6 节的 10 条自检过一遍，有一条不过就重写。

```bash
python run.py --script-topic 1                  # 取今日清单第 1 条
python run.py --script "企业上AI为什么用不起来"   # 直接给主题
python run.py --script-topic 2 --minutes 2      # 指定时长
```

输出 `data/scripts/日期-标题.md`。配了 LLM 密钥出完整稿；没配出骨架+提示。

### 3. 剪片（核心）

```bash
python run.py --input inbox/口播.mp4 --profiles all
python run.py --input inbox/口播.mp4 --profiles short
python run.py --input inbox/ --profiles short   # 传目录 → 批量
python run.py --input inbox/口播.mp4 --review   # 先出选段清单等人确认
```

输出 `outbox/<job>/<版本>/`：`final.mp4` + 竖版/横版封面 A/B + 5 平台文案×2 风格 + 评论草稿 + 小红书图文卡 + 发布清单。

### 4. 发布（自动填表，人点按钮）

```bash
python run.py --publish outbox/<job>/short --to douyin
python run.py --publish outbox/<job> --to douyin,xhs   # 多版本逐个发
```

脚本打开创作页、塞视频、填标题正文标签，**然后停住**。必须告诉用户：**发布按钮由用户自己点。** 点完后脚本提示粘贴作品链接，写入 `data/links.csv`。

### 5. 数据周报

```bash
python run.py --stats-template                 # 生成 CSV 模板
python run.py --stats-import data/metrics.csv  # 导入后台数字
python run.py --stats                          # 只出周报
python run.py --stats-fetch --to douyin        # 自动抓创作中心数据（需登录态）
```

输出 `data/reports/日期-周报.md`。自动抓取页面改版会失效，**优先用 CSV 导入**。

---

## 辅助命令

| 命令 | 作用 |
|---|---|
| `python run.py --cost` | 本月 API 花费 / 预算剩余 |
| `python run.py --check` | 环境自检 |
| `python run.py --demo` | 内置样例跑全流程（零成本零素材） |
| `python run.py --watch --once` | inbox 目录监听（放文件自动跑一次） |
| `python run.py --collect outbox/<job>/short` | 把生成的图收进素材库（省 API 费） |
| `python run.py --clean --dry-run` | 预览清理 work 目录 |
| `python run.py --schedule-install` | 注册 Windows 定时任务 |
| `python run.py --stats-fetch --to douyin` | 自动抓平台数据 |
| `python run.py --resume <job_id>` | 复用已有转写，不重新跑 ASR |

---

## 关键配置（改过记得重跑）

| 文件 | 管什么 |
|---|---|
| `.env` | `IMAGE_PROVIDER`（placeholder 默认零成本）、API 密钥、代理 |
| `config/providers.yaml` | 提供商、**价格（¥0.10/张）**、预算熔断 |
| `config/profile.yaml` | 用户选择（平台/LLM/出图方式） |
| `config/script.yaml` | 语速 260字/分、段落结构、禁用词 |
| `config/topics.yaml` | 选题关键词权重、门槛分、海外方向 |
| `config/style.yaml` | 配色、字体、分辨率、画幅 |
| `config/profiles.yaml` | 版本时长（short≈76s / mid≈180s / long≈290s）、选段打分 |
| `config/publish.yaml` | 各平台创作页地址、选择器、**login_url_patterns（登录失效检测）** |
| `config/platforms.yaml` | 各平台文案上限（title_limit / body_limit） |
| `config/stats.yaml` | 自动数据抓取脚本、**login_url_patterns** |

---

## 成本和预算熔断

- **SiliconFlow Z-Image-Turbo：¥0.10/张**（2026-11-11 账单核实，之前错配成 ¥0.02）
- Demo 每轮 25 镜 = ¥2.50（真实 AI），placeholder 模式 ¥0
- **预算熔断机制**：`providers.py` 里 `_budget_ok()` 每次 API 调用前检查本月累计花费，**超 ¥500 自动降级**（文案→规则模式，图片→占位图）
- **关键错误显式提示**：401 认证、402 余额不足会打印中文提示，**不再静默降级**
- `IMAGE_PROVIDER=placeholder` 默认开启，跑 demo 零成本

---

## 排错（常见问题）

| 现象 | 处理 |
|---|---|
| 图片全变占位图 + `💸 图片 API 余额不足（HTTP 402）` | SiliconFlow 账号欠费，充值后自动恢复 |
| 图片全变占位图 + `🔑 图片 API 认证失败` | `.env` 里密钥错了 |
| 发布时报"登录态已失效" | 重新 `--publish` 让浏览器自动复用登录态，或删 `work/browser/` 重扫 |
| 找不到元素 | 页面改版了。改 `config/publish.yaml` 的 `selectors`，每个字段有多个候选 |
| Reddit/HN 超时 | 在 `.env` 配 `HTTP_PROXY=http://127.0.0.1:7890`（国内源仍直连不受影响） |
| `--demo` 正常跑但 `--input` 报"没有识别到语音" | 素材无声或 ASR 失败，用 `--srt` 提供已有字幕 |
| LLM 偶发失败 | 内置 2 次重试（网络异常/5xx/429），仍失败降级为规则文案 |
| `.env` 里 `IMAGE_PROVIDER` 改了没生效 | 重启终端（python-dotenv 只在启动时读一次） |

---

## 硬边界（绝对不要做）

1. **不要代点「发布」按钮**。填完表就停住，让用户自己点。
2. **不要自动登录**。首次扫码必须用户本人做。
3. **不要自动发评论、私信、回复**。只出草稿，人发。
4. **不要做批量起号、矩阵养号**。`--account` 只是隔离登录态，不是批量注册工具。
5. **不要无人审核直接发布**。每次发布前人都要看一眼。

---

## 交付给用户时

- 成品：给 `outbox/<job>/<版本>/final.mp4` 路径
- 周报：给 `data/reports/日期-周报.md` 路径
- 口播稿：给 `data/scripts/日期-标题.md` 路径
- 不要贴整个路径树，只给最相关的那一个
