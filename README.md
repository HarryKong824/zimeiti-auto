# 自媒体全自动化

**一个人的短视频工厂。你只做两件事：录口播、点发布。**

输入一段口播视频，输出 5 个平台的成品包：竖版 mp4、封面图、平台定制文案、发布检查清单。

| 你负责 | 系统负责 |
|---|---|
| 录 5 分钟口播 | 抓热榜、出选题、写口播稿 |
| 看一眼成品 | 转写、选段、分镜、画面、字幕、合成 |
| 点发布按钮 | 封面、5 平台文案、填进创作页、数据周报 |

抖音 / 视频号 / 小红书 / B站 的个人号都拿不到发布 API，所以系统只把表填好、把浏览器停在那儿，最后那一下必须你来——这不是妥协，是唯一不封号的做法。X 有官方 API，可以全自动。

> 状态：主流程已跑通。画面还是占位图形，未接 AI 出图。
> 更新：2026-11-10

---

## 1. 这个项目是什么

把「一条口播录音」变成「5 个平台可直接发布的成品包」。

输入：一段录好的口播视频/音频 + 一句话主题
输出：竖版成品 mp4、封面图、5 份平台定制文案、发布检查清单

**不是**"一键生成视频"工具，而是**一个人的内容工厂**：它不替你做审美判断，它把你每周耗在剪辑、套字幕、写文案、复制粘贴上的十几个小时压到半小时。

---

## 2. 硬约束（事实基础，不重复论证）

这些是核查过的平台事实，直接决定了架构，不是设计选择：

| 平台 | 发布 API | 个人能否拿到 | 结论 |
|---|---|---|---|
| 抖音 | 有 | 否（企业主体、注册资本≥50万、注册满1年） | 人工发布 |
| 视频号 | 无 | — | 人工发布 |
| 小红书 | 无发布权限 | 否（仅服务商/商家自研） | 人工发布 |
| B站 | 有 | 否（未开放个人开发者入驻） | 人工发布 |
| X | 有（按量付费） | 是 | 可全自动 |

由此推出三条不可协商的边界：

1. **发布必须人工点**。这不是妥协，是唯一合规解。
2. **不做自动登录、不做自动回评、不做多账号矩阵**。小红书已明文封禁 AI 托管代发代互动，抖音按虚假互动处置。
3. **不代点发布按钮**。填表可以做，代点不做。平台禁止的是「自动化程序接入并发布」，不是「帮人把表填好」——这条线划在按钮上。

---

## 3. 设计原则

- **程序化渲染，不是 GUI 自动化**：全线 ffmpeg / 代码渲染，可复现、可版本管理。
- **中间产物全落盘**：转写、分镜、图、时间线都是文件，任一步可单独重跑。
- **固定风格才能自动化**：8 个镜头模板 + 固定 LoRA + 固定种子池。风格一飘，全部失效。
- **用数量换质量**：夜间算力过剩 → 每条出 4 倍候选图 → 自动评分排序 → 人只看 top 2。
- **发布是不可外包的一步**：系统交付"待发布包"，不交付"已发布"。

---

## 4. 流水线

```
选题（抓热榜 → 打分 → 今日清单）
  ↓  ⓪ 口播稿（LLM：按段落结构写，标好每段秒数和字数）
口播录音
  ↓  ① 转写（faster-whisper，本地 CPU）
逐句时间戳
  ↓  ② 分镜（LLM：每句话映射到镜头模板 + 生成提示词）
分镜表 storyboard.json
  ↓  ③ 出图（本地 ComfyUI 夜间批量，4 倍候选）
候选图池
  ↓  ④ 评分筛选（CLIP 相似度 + 美学分）
定稿图
  ↓  ⑤ 时间线合成（ffmpeg：2.5D 运镜、字幕、转场、BGM）
成品视频
  ↓  ⑥ 封面 + 文案（Pillow 模板 + LLM 多平台改写）
  ↓  ⑦ 打包 → outbox/
  ↓  ⑧ 自动上传（Playwright：塞视频、填标题标签封面）
【人工：检查一眼，点发布】
  ↓  ⑨ 数据回填（只读抓取，日频）→ 周报
```

### 模块职责

| 模块 | 输入 | 输出 | 工具 |
|---|---|---|---|
| topics | 公开热榜 | `data/topics/日期.md` 选题清单 | requests |
| script | 选题 | `data/scripts/*.md` 口播稿 | LLM / 段落模板 |
| ingest | 口播文件 | job 目录 | Python |
| asr | 音频 | `transcript.json`（词级时间戳） | faster-whisper |
| storyboard | transcript | `storyboard.json` | LLM |
| render_images | storyboard | 候选图 + 评分 | ComfyUI / API |
| compose | 定稿图 + 时间轴 | `final.mp4` | ffmpeg |
| cover | 标题 | `cover.png` | Pillow + 模板 |
| copywrite | transcript + 平台 | 5 份 md | LLM |
| package | 以上全部 | `outbox/<job>/` | Python |
| publish | 成品目录 | 创作页里填好的表单 | Playwright |
| metrics | 平台后台 | `metrics.db` + 周报 | Playwright（只读） |
| comments | 评论列表 | 回复草稿 | LLM |

---

## 5. 八个镜头模板

自动化的核心。LLM 不能自由发挥，只能在下面选，并填参数。

| # | 模板 | 用途 | 实现 |
|---|---|---|---|
| 1 | 人物中景 | 观点、结论 | 图 + 缓慢推进 |
| 2 | 物件特写 | 具体例子 | 图 + 横向位移 |
| 3 | 数据图表 | 数字、对比 | 代码渲染（非 AI） |
| 4 | 地图路径 | 地点、流程 | 代码渲染 |
| 5 | 对比双屏 | A vs B | 双图拼合 |
| 6 | 大字卡 | 金句、章节 | 纯排版 |
| 7 | 引语卡 | 引用 | 纯排版 |
| 8 | 转场 | 段落切换 | 预置动画 |

模板固定 = 风格统一 = 可全自动。所有"运镜"都是 2.5D 视差（分层平移缩放），不依赖视频生成模型。

---

## 6. 技术栈

| 层 | 选择 | 为什么 |
|---|---|---|
| 编排 | Python + 目录状态机 | 不引工作流引擎，调试与回滚成本最低 |
| 转写 | faster-whisper | 免费、CPU 可用、词级时间戳 |
| 出图 | ComfyUI（SD1.5 / SDXL GGUF） | 本地免费、可锁风格 |
| 合成 | ffmpeg | 稳定、免费、可脚本化 |
| 封面 | Pillow | 模板化，零依赖 |
| 文案 | LLM API | 一条几分钱 |
| 数据 | Playwright（只读、日频） | 唯一会周期性坏掉的部分 |

---

## 7. 成本模型

目标 ≤ 500 元/月，实际预估 **60-110 元/月**。

| 项目 | 月成本 |
|---|---|
| 出图（本地） | 0 |
| LLM（分镜 + 文案） | ~10 元 |
| API 补图 / 关键动态镜头 | 50-80 元 |
| 转写 / 合成 / 封面 | 0 |
| **合计** | **60-110 元** |

测算依据：每条 5 分钟约 40 个镜头，本地夜间出 4 倍候选，API 只补救火。

---

## 8. 环境

开发机：Dell G15 5511 / i7-11800H / 16GB / RTX 3060 Laptop 6GB / Win11

| 任务 | 可行性 |
|---|---|
| SD1.5 出图（512-768） | 流畅，2-3 秒/张 |
| SDXL GGUF Q4（768-832） | 可用，6-10 秒/张 |
| 图生视频 | 不可行（需 8GB+）→ 用 2.5D 运镜替代 |
| faster-whisper（CPU） | 5 分钟音频约 1-2 分钟 |
| ffmpeg 1080p 合成 | 3-8 分钟 |

---

## 9. 路线图

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** | 选题 → 口播稿 → 转写 → 分镜 → 出图 → 合成 → 打包 | ✅ 已跑通；出图仍是占位图 |
| **P1** | 5 平台文案变体、封面、字幕样式 | ✅ 一次打包出 5 平台成品 |
| **P2** | 发布前自动上传（填好标题标签封面，停在发布按钮） | 成品自动进创作页，人只需点发布 |
| **P3** | 数据回填 + 每周汇总 | 自动生成周报 |
| **P4** | 评论草稿（只出草稿，人发） | 评论分类 + 回复建议 |
| **P5** | 可选：X 平台 API 全自动发布 | X 端无人工 |

**P0 不做的事**：不做多平台、不做数据、不做评论、不做云端部署、不做 GUI。

---

## 10. 快速开始

```bash
pip install -r requirements.txt      # Pillow / requests / PyYAML / faster-whisper / numpy
python run.py --check                # 环境自检：ffmpeg / 依赖 / 字体 / 目录 / 热榜
python run.py --demo                 # 内置样例跑通全流程，不消耗任何额度

# ⓪ 先从选题到稿子
python run.py --topics                          # 抓热榜，出今天能做的选题
python run.py --script-topic 1                  # 取清单第 1 条，生成口播稿
python run.py --script "企业上AI为什么用不起来"   # 或者跳过热榜，直接给主题
python run.py --script-topic 2 --minutes 2      # 要短的就指定时长

# ① 录完丢进来
python run.py --input inbox/口播.mp4 --profiles all
python run.py --input inbox/口播.mp4 --profiles short   # 只出短版

# ② 发布前自动上传
python run.py --publish outbox/<job>/short --to douyin
python run.py --publish outbox/<job>/short --to douyin,xhs,bilibili
```

**自动上传的边界**：脚本负责打开创作页、塞视频、填标题正文标签、传封面，然后把浏览器停在那儿。
「发布」按钮永远你自己点。登录态存在 `work/browser/<平台>/`，第一次要扫码，之后不用再登。

页面改版会导致选择器失效，改 `config/publish.yaml` 里的 `selectors` 就行，不用动代码。
每个字段给了多个候选，按顺序试第一个存在的。

```bash
# ③ 发完回填数据，出周报
python run.py --stats-template                        # 生成 CSV 模板，按列填后台数字
python run.py --stats-import data/metrics.csv         # 导入并出周报
python run.py --stats                                 # 只出周报
```

周报会给出两类判断：哪条是中位数的几倍（可以照着再拆一条）、哪几条不到中位数一半（先查开头 3 秒）。

口播稿会写到 `data/scripts/日期-标题.md`，每段标好秒数和字数（按 240 字/分换算）。
配了 LLM 密钥就是完整稿；没配就输出结构骨架 + 每段写作提示，照样能指导录制。

### 作为 Skill 使用

项目里有给 AI Agent 读的操作手册，位于 `.trae/skills/zimeiti-auto/SKILL.md`。装好之后不用记命令，直接说「把 inbox 里那个视频剪成短版，发到抖音」就行。

#### Trae（CN / 国际版通用）

**方式 A：项目级 skill（最简单，推荐）**

直接 clone 本仓库、用 Trae 打开这个文件夹即可——skill 已经在仓库里，打开就生效：

```bash
git clone https://github.com/HarryKong824/zimeiti-auto.git
cd zimeiti-auto
pip install -r requirements.txt
python run.py --check
```

在 Trae 里 File → Open Folder 打开 `zimeiti-auto`，然后说「跑个 demo」就会触发 skill。

**方式 B：全局 skill（任何项目里都能用）**

在仓库根目录跑一次安装脚本，它会自动把 skill 复制到全局 skills 目录，并把仓库绝对路径写进 SKILL.md：

```powershell
# Windows（PowerShell）
.\install.ps1                  # 装到 CN 版  ~/.trae-cn/skills/zimeiti-auto/
.\install.ps1 -Edition international   # 装到国际版  ~/.trae/skills/zimeiti-auto/
```

```bash
# Linux / macOS
bash install.sh                  # 装到 CN 版  ~/.trae-cn/skills/zimeiti-auto/
bash install.sh international    # 装到国际版  ~/.trae/skills/zimeiti-auto/
```

装完重启 Trae，在任何项目里说「剪视频」「选题」「跑 demo」即可触发。

**卸载**：删除 `~/.trae-cn/skills/zimeiti-auto/`（或国际版对应目录）即可。安装脚本会在覆盖前自动备份旧版本。

#### Claude Code

```bash
git clone https://github.com/HarryKong824/zimeiti-auto.git ~/.claude/skills/zimeiti-auto
cd ~/.claude/skills/zimeiti-auto
pip install -r requirements.txt
python run.py --check
```

**整个项目要放进 skills 目录，不能只复制 `SKILL.md`。** Agent 需要执行 `run.py`，脚本和配置都得在。

为什么是 Skill 而不是插件：这个项目没有 UI 需求，交互全靠一句话。插件相比 Skill 多出来的能力是「往宿主界面加按钮」，这里用不上；而 Skill 是插件的内容子集，将来真要升插件，这份 `SKILL.md` 不用重写。

> 转写默认读 `models/faster-whisper-small`。目录不存在时按 `small` 自动联网下载——国内 HuggingFace 官方基本连不上，镜像约 0.2 MB/s，建议直接从 ModelScope 拉这 4 个文件放进该目录：`config.json`、`model.bin`、`tokenizer.json`、`vocabulary.txt`。
>
> 实测：40 秒中文语音用 small 模型在 i7-11800H 上耗时 11.7 秒，8 段，准确率可用（偶有繁体输出）。

冒烟测试（不需要网络和模型，约 6 秒）：

```bash
python -m pytest tests -q
```

覆盖：版本配置完整性、选段清单读写、短版时长收敛、端到端出片与产物齐全。

### 规则全部可配置

没有写死的逻辑。改 `config/profiles.yaml` 就能换风格，不用动代码：

| 配置 | 作用 |
|---|---|
| `duration.target` | 目标时长，自动选段裁到这个长度 |
| `selection.mode` | `auto` 全自动 / `review` 先出候选清单等你确认 |
| `scoring.weights` + `patterns` | 选段打分规则，正则 + 权重随便加 |
| `hook.enabled` | 是否把最抓人的一句提到开头 |
| `pacing.shot_min/max` | 镜头节奏，2 秒快切还是 9 秒长镜 |
| `subtitle.size/margin_v/chars_per_line` | 字幕字号、位置、每行字数 |
| `aspect` | `9:16` / `16:9` / `1:1` |
| `platforms` | 这个版本投哪些平台 |

默认内置三档：`short`（75 秒，抖音/视频号/X）、`mid`（150 秒，小红书）、`long`（300 秒，B站）。

**怎么改**：只动数字，不动代码。比如想把短版压到 60 秒、字幕更大：

```yaml
short:
  duration: {target: 60}          # 75 → 60
  subtitle: {size: 72}            # 64 → 72
  pacing: {shot_min: 1.5, shot_max: 2.5}   # 切得更快
```

改完直接再跑一次，只影响对应版本。想新增一个版本（比如只发视频号的 30 秒竖版），复制 `short` 整段、改名字和数字即可：

```yaml
teaser:
  name: 30秒预热
  platforms: [shipinhao]
  duration: {target: 30, min: 20, max: 40}
  hook: {enabled: true}
  pacing: {shot_min: 1.2, shot_max: 2.0}
  subtitle: {size: 76, chars_per_line: 12}
```

然后 `python run.py --input 你的素材.mp4 --profiles teaser`。

三个可选加速项：

- `--srt xxx.srt`：已有字幕就跳过转写（不装 faster-whisper 也能跑）
- 接本地出图：装 ComfyUI 后，在 `.env` 设 `IMAGE_PROVIDER=comfyui`、`COMFYUI_CHECKPOINT=模型名`
- 接文案 LLM：`.env` 填 `OPENAI_BASE_URL` / `OPENAI_API_KEY`；不填则用规则模板兜底

### 选段确认（短版建议开）

```bash
python run.py --input inbox/口播.mp4 --profiles short --review
# 生成 work/<job>/profiles/short/选段.md，程序在这里停住
# 文件里每句一行，[x] 是打算保留的。把不要的改成 [ ]，保存
python run.py --resume <job_id> --profiles short
```

纯文字确认，不渲染视频、不调模型、不花钱。只要那个目录里有 `选段.md`，续跑就按它执行，优先级高于自动模式。

想让某个版本默认走确认，在 `config/profiles.yaml` 里给它加 `selection: {mode: review}`。

### 选题：先有题目，再录口播

```bash
python run.py --topics                 # 抓公开热榜，出今日选题清单
python run.py --topics --top-n 10      # 只看前 10 条
```

输出到 `data/topics/YYYY-MM-DD.md`，每条给：来源与排名、命中的关键词、可切入的角度、原文链接。

- 数据源：B站排行榜 / 知乎热榜 / 百度热搜，全部公开免登录
- 不做的：抖音、小红书、微博（需要签名或直接 403），以及任何评论区抓取
- 规则在 `config/topics.yaml`：关键词权重、过线分数、角度映射，改数字即可

每个关键词可单独给权重，防止"AI"两个字什么内容都能蹭：`AI: 6`、`数字化转型: 20`、`中小企业: 14`。

`outbox/<job_id>/` 里每个平台会出**两份文案**：`copy_douyin_decision.md`（决策者版）和 `copy_douyin_learner.md`（学习者版）。同一条视频，两种表述：老板看价值与成本，学习者看步骤与模板。

**零付费也能跑全流程**：转写、出图、合成、封面全部本地免费；LLM 文案是可选项，不填就用规则模板兜底。

## 11. 目录结构

```
自媒体全自动化/
├─ README.md
├─ run.py                  # 入口
├─ requirements.txt
├─ .env.example
├─ config/
│   ├─ profiles.yaml       # 版本规则：时长/节奏/字幕/画幅/打分权重
│   ├─ topics.yaml         # 选题规则：关键词权重、门槛分、角度映射
│   ├─ style.yaml          # 风格、分辨率、字幕、封面参数
│   ├─ platforms.yaml      # 各平台文案规则
│   ├─ audiences.yaml      # 双受众（决策者/学习者）文案规则
│   ├─ script.yaml         # 口播稿规则：语速、段落结构、禁用的 AI 味词汇
│   └─ publish.yaml        # 各平台创作页地址与选择器（页面改版只改这里）
├─ src/
│   ├─ pipeline.py         # 编排（按版本循环）
│   ├─ profiles.py         # 版本配置解析
│   ├─ select.py           # 选段打分 + 剪音频 + 重建时间轴
│   ├─ script.py           # 口播稿：选题 → 分段稿 + 每段字数与时长
│   ├─ topics.py           # 选题：热榜采集 + 打分 + 出清单
│   ├─ ingest.py           # 入库 + 抽音轨
│   ├─ asr.py              # 转写 / SRT 解析
│   ├─ storyboard.py       # 分镜（规则 + 可选 LLM）
│   ├─ templates.py        # 8 个镜头模板
│   ├─ images.py           # 出图（placeholder / ComfyUI）
│   ├─ compose.py          # ffmpeg 时间线 + 字幕
│   ├─ cover.py            # 封面
│   ├─ copywrite.py        # 多平台 × 双受众文案
│   ├─ package.py          # 打包 outbox
│   └─ publish.py          # 自动填表上传（不点发布）
├─ inbox/                  # 丢口播素材
├─ work/<job_id>/          # 中间产物
│   └─ profiles/<版本>/     # 每个版本独立的音频、时间轴、分镜、图、片段
├─ outbox/<job_id>/<版本>/  # 待人工发布：final.mp4 + cover.png + 文案 + 清单
├─ library/                # 复用素材库（P2）
└─ data/
    ├─ topics/             # 每日选题清单（md 给人看，json 给程序读）
    ├─ scripts/            # 口播稿
    └─ metrics.db          # 数据回填（P2）
```

---

## 12. 自动化的三档边界

技术上，"账号自动运营 + 自动回评"早就有人做出来了。但这个项目按**风险**而不是按**技术**划线。

### 三档划分

| 环节 | 全自动 | 折中（人在环） | 不做 |
|---|---|---|---|
| 评论 | 抓取、分类、生成回复 | ✅ 一键填充，人工点发送 | ❌ 全自动发送 |
| 数据 | 抓取、汇总、周报 | — | — |
| 发布 | X（官方 API） | ✅ 4 个国内平台：自动填表，人点发布按钮 | ❌ 脚本代点发布 |
| 私信 | — | 生成草稿 | ❌ 自动发送 |
| 账号 | — | 发布日历、内容提醒 | ❌ 自动登录、养号、切号、矩阵 |
| 内容 | 分镜、画面、字幕、封面、文案 | — | ❌ 伪造真人出镜 |

### 为什么"写入侧"不能全自动

这是安全治理环节，不是能力不足。四个理由：

1. **平台判的是行为，不是工具。** 识别信号是：IP/设备指纹突变、发布节奏精确到秒、互动时间 24 小时无间断、回复文本同质化。工具本身不是判据，行为是。
2. **明文规则已经封死。** 小红书 2026-03-10 公告：通过 AI 托管工具完成注册/发布/互动 → 封禁；抖音用户协议 5.1 禁止自动化程序接入，自动回复按"虚假互动/水军"处置（近半年 400 万账号）；小红书同期处置风险设备关联账号 49.5 万个。
3. **风险和收益不对称。** 全自动每天多省 10 分钟；被封的代价是一个号的全部历史、权重、粉丝。新号权重为零，一次判罚直接归零。
4. **"人在环"本身就是最好的伪装。** 你点那一下，恰好把最容易被识别的信号消掉了。折中方案省掉 90% 脑力，风险降一个量级。

### 明确不做

- ❌ 自动登录（首次扫码必须人做）、代点发布与互动按钮、指纹浏览器、云手机
- ❌ 自动发送评论/私信
- ❌ 多账号矩阵、批量起号
- ❌ 无人审核直接发布
- ❌ 用生成模型伪造真人出镜

补充一条容易混淆的：**"自动填表"不等于"自动发布"**。前者把 8 分钟的重复劳动压到 10 秒，后者把账号所有权押上去。这条线划在"点按钮"上，不划在"打开浏览器"上。

不是做不到，是做了会封号，且申诉无依据。想做矩阵号的人可以自己改，但那是另一个风险模型：他们封了有备份，个人主号封了归零。

---

## 13. 开源说明

- 项目定位：**个人创作者的自建内容工厂**，不是 SaaS，不碰平台风控。
- 可复用部分：镜头模板系统、时间线合成器、评分筛选、多平台文案改写。
- 不可复用部分：`config/style.yaml`（个人风格配置）。
- 建议仓库名：`auto-media-pipeline`。

---

## 14. 当前待定

- [ ] 风格方向与 LoRA 选型
- [ ] 8 个模板的具体视觉规范
- [ ] P0 是否先只做抖音单平台
- [ ] `title` / `quote` 镜头的中央大字卡与底部字幕内容重复（同一句话出现两次），考虑该镜头屏蔽字幕 —— 暂缓，不影响链路

