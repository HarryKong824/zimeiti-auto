---
name: zimeiti-auto
description: 自媒体短视频全流程自动化。用户要把一段口播视频剪成多平台成品、想选题、要口播稿、要发布到抖音/小红书/B站/视频号、或要看数据周报时使用。触发词：剪视频、做短视频、选题、口播稿、发布、上传、周报、账号数据。
---

# 自媒体全自动化

一个人的短视频流水线：

选题 → 口播稿 → 转写 → 选段 → 分镜 → 出图 → 合成 → 打包 → 填表上传 → 数据周报

**用户只做两件事：录视频、点发布按钮。** 其余都交给这里的脚本。

---

## 工作目录

**项目根 = 本文件所在目录。** 所有命令都在项目根执行，不要再 cd 到别处。

需要：Python 3.10+、ffmpeg（必须在 PATH 里）、`pip install -r requirements.txt`。

## 第 0 步：环境自检 + 首次配置

第一次接手任何操作，先跑：

```bash
python run.py --check
```

输出 `✓` 正常、`!` 警告、`✗` 致命。有 `✗` 必须先修，否则后面全崩。

想先看看成品长什么样，不花任何额度和素材：

```bash
python run.py --demo
```

### 首次配置（只问一次）

检查 `config/profile.yaml` 是否已有用户选择。如果没有（或用户说"换方向/change direction"），依次问以下 3 个问题，把答案写进 `config/profile.yaml` 和 `.env`：

**问题 1：平台**
> 你要发哪些平台？国内（抖音/小红书/B站/视频号）、海外（X）、还是全部？

→ 写入 `profile.yaml` 的 `platforms`（对应 key：douyin / xhs / bilibili / shipinhao / x）

**问题 2：LLM 模型（按预算）**
> 口播稿和文案用哪个模型？
> - DeepSeek（约 ¥1/百万token，中文好）← 推荐
> - OpenAI gpt-4o-mini（约 ¥1.5/百万token）
> - Groq（免费额度，速度快）

→ 写入 `profile.yaml` 的 `llm_provider`，并在 `.env` 填对应密钥（`DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 或 `GROQ_API_KEY`）

**问题 3：出图方式**
> 画面怎么来？
> - placeholder（几何占位图，零成本，先跑通流程）← 推荐起步
> - SiliconFlow FLUX（约 ¥0.02/张，32 张≈¥0.64）
> - ComfyUI 本地（免费，需显卡）

→ 写入 `profile.yaml` 的 `image_provider`，并在 `.env` 填 `SILICONFLOW_API_KEY`（如果选了 API）或 `COMFYUI_CHECKPOINT`（如果选了本地）

**问完后**：把答案写入 `config/profile.yaml`，把密钥写入 `.env`，告诉用户"配置已保存，下次不再问"。之后除非用户主动说"换方向"，不要再重复询问。

---

## 五个命令

### 1. 选题

```bash
python run.py --topics            # 抓 B站/知乎/百度 + Reddit/HackerNews，打分，出今日清单
python run.py --topics --top-n 10 # 只要前 10 条
```

国内源用中文关键词，国外源（Reddit/HN）用英文关键词，都在 `config/topics.yaml` 的 `directions.<方向>.keywords_zh/en`。Reddit 子版块也按方向配在 `subreddits`。单个源抓取失败不影响其他源。

输出 `data/topics/日期.md`（给人看）和 `日期.json`（给程序读）。

选题规则在 `config/topics.yaml`：关键词带权重、门槛分、角度映射。觉得选题不对就改这里，不要改代码。

### 2. 口播稿

```bash
python run.py --script-topic 1                  # 取今日清单第 1 条
python run.py --script "企业上AI为什么用不起来"   # 或者直接给主题
python run.py --script-topic 2 --minutes 2      # 指定时长
```

输出 `data/scripts/日期-标题.md`，每段标好秒数和字数（按 240 字/分换算）。

- 配了 `.env` 里的 `OPENAI_BASE_URL` + `OPENAI_API_KEY`：出完整稿
- 没配：出结构骨架 + 每段写作提示，照样能指导录制

段落结构、语速、禁用的 AI 味词汇都在 `config/script.yaml`。

### 3. 剪片

```bash
python run.py --input inbox/口播.mp4 --profiles all
python run.py --input inbox/口播.mp4 --profiles short   # 只出短版
python run.py --input inbox/ --profiles short           # 传目录 → 批量处理，单个失败不中断
python run.py --input inbox/口播.mp4 --review           # 先出选段清单，等用户勾选再剪
```

批量处理时，目录下所有 `mp4/mov/mkv/avi/flv/m4v/wav/mp3/m4a/aac` 会逐个跑；某个文件失败只跳过它，其余继续。

输出 `outbox/<job>/<版本>/`：`final.mp4` + 竖版/横版封面 + 5 平台文案 + 评论草稿 + 发布清单。

**先跟用户确认版本**。`--profiles` 可用的值看 `config/profiles.yaml`，默认 short / mid / long。短版 77 秒左右，长版 5 分钟。

续跑（复用已有转写，不重新跑 ASR）：

```bash
python run.py --resume <job_id> --profiles short
```

### 4. 发布前自动上传

```bash
python run.py --publish outbox/<job>/short --to douyin
python run.py --publish outbox/<job> --to douyin,xhs   # 传 job 目录 → short/mid 多版本逐个发布
python run.py --publish outbox/<job>/short --to douyin --account 小号   # 多账号：登录态按账号隔离
```

脚本会打开创作页、塞视频、填标题正文标签，**然后停住**。

必须先跟用户说清楚：**发布按钮由用户自己点。** 不要试图绕过。

用户点完发布后，脚本会提示粘贴作品链接（可留空）：
- 链接写入版本目录 `links.md`
- 同时追加 `data/links.csv`（date/platform/version/url），方便周报对应具体作品

第一次要用户扫码登录，登录态存在 `work/browser/<平台>/<账号>/`，之后复用。已经登录过主号，换账号要单独扫一次。

### 5. 数据周报

```bash
python run.py --stats-template                     # 生成 CSV 模板
python run.py --stats-import data/metrics.csv      # 导入后台数字并出周报
python run.py --stats                              # 只出周报
python run.py --stats-fetch                        # 自动抓各平台创作中心数据（尽力而为）
python run.py --stats-fetch --to douyin --account 小号   # 只抓某个平台/账号
```

输出 `data/reports/日期-周报.md`，含分平台统计和规则型建议（哪条值得再拆、哪条该止损）。

自动抓取需要先有登录态（跟发布共用 `work/browser/`），页面改版会失效；抓不到会明确提示，不会静默。**优先用 CSV 导入**，抓取只是省事的一路。

### 6. 定时任务

```bash
python run.py --schedule-install   # 按 config/schedule.yaml 注册（每日选题 08:00、周一 09:00 周报）
python run.py --schedule-status    # 看下次运行时间
python run.py --schedule-remove    # 全部删除
```

时间改完要重新 `--schedule-install`。

### 7. 花费追踪

```bash
python run.py --cost    # 本月 API 花费 / 预算剩余 / 分提供商明细
```

每次 LLM 和图片 API 调用都会记到 `data/costs.jsonl`。预算在 `providers.yaml` 的 `budget` 配置。

### 8. 素材回流与清理

```bash
python run.py --collect outbox/<job>/short   # 把这一版生成的图收进 library/images（带关键词侧车）
python run.py --clean --dry-run              # 预览：work 下超过 7 天的目录
python run.py --clean --days 3               # 真删（browser 登录态、demo 素材永久保留）
```

`--collect` 传 outbox 版本目录即可，脚本会自动映射回 `work/<job>/profiles/<版本>` 找图。收进库后下次出图优先复用，省 API 费用。

---

## 常用参数

| 参数 | 作用 |
|---|---|
| `--input` | 口播素材路径；传目录则批量处理 |
| `--profiles` | `all` 或逗号分隔的版本名：`short,mid` |
| `--review` | 强制先出选段清单等人确认 |
| `--resume` | 复用 work 下已有 job 的转写 |
| `--srt` | 已有字幕，跳过转写 |
| `--provider` | 出图方式：`placeholder`（默认）/ `comfyui` / `api` / `siliconflow` / `dalle3` |
| `--account` | 发布/抓数据用的账号名（多账号隔离登录态） |
| `--check` | 环境自检 |
| `--demo` | 内置样例跑全流程 |
| `--cost` | 本月 API 花费与预算 |
| `--schedule-*` | 定时任务安装/状态/删除 |
| `--stats-fetch` | 自动抓取平台数据 |
| `--collect` | 把某版本生成的图收进素材库 |
| `--clean` / `--days` / `--dry-run` | 清理 work 旧目录 |

---

## 排错

| 现象 | 处理 |
|---|---|
| `--check` 报 ffmpeg ✗ | 装 ffmpeg 并加进 PATH，重启终端 |
| 转写报 `av` 相关错误 | 已用 ffmpeg 解码绕开，仍报错说明 ffmpeg 本身坏了 |
| 找不到 whisper 模型 | 模型放 `models/faster-whisper-small/`，或用 `WHISPER_MODEL` 环境变量指路径 |
| Linux 上字幕是方框 | 装 `fonts-noto-cjk`，字体回退逻辑在 `src/fonts.py` |
| 出图慢 | 正常。32 个镜头约 30 秒 |
| 上传时找不到元素 | 页面改版了。改 `config/publish.yaml` 的 `selectors`，每个字段有多个候选 |
| 选段结果不满意 | 用 `--review` 出清单，改完再剪。打分权重在 `config/profiles.yaml` 的 `scoring` |
| 字幕一句话被劈开 | 断行规则在 `src/images.py` 的 `_SOFT_TAIL` 和 `src/cues.py` |
| 海外源（Reddit/HN）超时 | 在 `.env` 配 `HTTP_PROXY` / `HTTPS_PROXY`，国内源仍会直连 |
| 发布页打不开 / 转圈 | 浏览器也要走代理时配 `BROWSER_PROXY` |
| 自动抓数据抓到 0 条 | 多半没登录或页面改版。先 `--publish` 过一次登录，再核对 `config/stats.yaml` 的 `js` |
| 批量处理全跳过 | 提示"没有识别到语音"说明素材无声或 ASR 失败，用 `--srt` 提供字幕 |
| LLM/图片偶发失败 | 已内置 2 次重试（网络异常/5xx/429），仍失败才降级为规则文案或占位图 |

---

## 硬边界：这些事不要做

不是做不到，是做了账号会没。

1. **不要代点「发布」按钮。** 填完表就停住，让用户自己点。
2. **不要自动登录。** 首次扫码必须用户本人做，也不要保存密码。
3. **不要自动发评论、私信、回复。** 只出草稿，人发。
4. **不要做批量起号、矩阵养号。** `--account` 只是把用户自己不同账号的登录态分开存，不是拿来批量注册/养号。
5. **不要无人审核直接发布。** 每次发布前人都要看一眼。

原因写在 README 第 12 节：小红书 2026-03 明文公告 AI 托管发布即封号，抖音协议 5.1 禁止自动化接入，平台近半年处置 400 万账号。新号权重为零，封一次归零，没有申诉依据。

**"自动填表"不等于"自动发布"。** 前者把 8 分钟重复劳动压到 10 秒，后者把账号所有权押上去。这条线划在"点按钮"上。

---

## 交付给用户时

- 成品：给 `outbox/<job>/<版本>/final.mp4` 的完整路径
- 周报：给 `data/reports/日期-周报.md` 的路径
- 口播稿：给 `data/scripts/日期-标题.md` 的路径
- 不要把整个路径树贴出来，只给最相关的那一个

## 改配置而不是改代码

这个项目的规则全部外置在 `config/`：

| 文件 | 管什么 |
|---|---|
| `profiles.yaml` | 版本时长、节奏、字幕、画幅、选段打分权重 |
| `topics.yaml` | 选题关键词权重、门槛分 |
| `script.yaml` | 口播稿语速、段落结构、禁用词 |
| `style.yaml` | 配色、字体、分辨率 |
| `platforms.yaml` | 各平台文案规则（标题/正文字数上限 `title_limit` / `body_limit`） |
| `audiences.yaml` | 决策者/学习者双受众文案规则 |
| `publish.yaml` | 各平台创作页地址与选择器 |
| `comments.yaml` | 各平台评论草稿数量与风格 |
| `schedule.yaml` | 定时任务的时间与命令 |
| `stats.yaml` | 各平台创作中心地址与抓取脚本 |
| `profile.yaml` | 用户选择：平台、选题方向、出图/LLM 提供商 |

## 额外产出

流水线除了视频，还会自动生成：
- **封面多比例**：一次出 4 张——竖版 `cover.png` / `cover_b.png`（3:4，抖音/小红书）+ 横版 `cover_wide.png` / `cover_wide_b.png`（16:9，B站/视频号）。张数看 `style.yaml` 的 `cover.variants`，比例看 `cover.sizes`。发布时横版平台自动选 `cover_wide.png`。
- **评论草稿**：`comments_<平台>.md`，每条 3-5 条，手动复制发布（不自动发）
- **小红书图文卡**：`xhs_cards/` 目录，6 张轮播图（封面+观点+收尾），仅当平台含 `xhs` 时生成
- **素材库复用**：图片放 `library/images/`，视频放 `library/videos/`；文件名含关键词（如 `企业_办公室.png`）或放同名 `.yaml` 写 `tags:`。出图时优先匹配，视频会自动裁剪循环到镜头时长

用户说"短版再短一点""选题别要娱乐新闻"，先看能不能改配置解决。改配置解决不了才动代码。
