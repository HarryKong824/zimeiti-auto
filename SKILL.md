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

## 第 0 步：环境自检

第一次接手任何操作，先跑：

```bash
python run.py --check
```

输出 `✓` 正常、`!` 警告、`✗` 致命。有 `✗` 必须先修，否则后面全崩。

想先看看成品长什么样，不花任何额度和素材：

```bash
python run.py --demo
```

---

## 五个命令

### 1. 选题

```bash
python run.py --topics            # 抓 B站/知乎/百度热榜，打分，出今日清单
python run.py --topics --top-n 10 # 只要前 10 条
```

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
python run.py --input inbox/口播.mp4 --review           # 先出选段清单，等用户勾选再剪
```

输出 `outbox/<job>/<版本>/`：`final.mp4` + `cover.png` + 5 平台文案 + 发布清单。

**先跟用户确认版本**。`--profiles` 可用的值看 `config/profiles.yaml`，默认 short / mid / long。短版 77 秒左右，长版 5 分钟。

续跑（复用已有转写，不重新跑 ASR）：

```bash
python run.py --resume <job_id> --profiles short
```

### 4. 发布前自动上传

```bash
python run.py --publish outbox/<job>/short --to douyin
python run.py --publish outbox/<job>/short --to douyin,xhs,bilibili
```

脚本会打开创作页、塞视频、填标题正文标签，**然后停住**。

必须先跟用户说清楚：**发布按钮由用户自己点。** 不要试图绕过。

第一次要用户扫码登录，登录态存在 `work/browser/<平台>/`，之后复用。

### 5. 数据周报

```bash
python run.py --stats-template                     # 生成 CSV 模板
python run.py --stats-import data/metrics.csv      # 导入后台数字并出周报
python run.py --stats                              # 只出周报
```

输出 `data/reports/日期-周报.md`，含分平台统计和规则型建议（哪条值得再拆、哪条该止损）。

---

## 常用参数

| 参数 | 作用 |
|---|---|
| `--input` | 口播素材路径 |
| `--profiles` | `all` 或逗号分隔的版本名：`short,mid` |
| `--review` | 强制先出选段清单等人确认 |
| `--resume` | 复用 work 下已有 job 的转写 |
| `--srt` | 已有字幕，跳过转写 |
| `--provider` | 出图方式：`placeholder`（默认，几何图形）/ `comfyui` / `api` |
| `--check` | 环境自检 |
| `--demo` | 内置样例跑全流程 |

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

---

## 硬边界：这些事不要做

不是做不到，是做了账号会没。

1. **不要代点「发布」按钮。** 填完表就停住，让用户自己点。
2. **不要自动登录。** 首次扫码必须用户本人做，也不要保存密码。
3. **不要自动发评论、私信、回复。** 只出草稿，人发。
4. **不要做多账号矩阵、批量起号。** 一机一号。
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
| `platforms.yaml` | 各平台文案规则 |
| `audiences.yaml` | 决策者/学习者双受众文案规则 |
| `publish.yaml` | 各平台创作页地址与选择器 |

用户说"短版再短一点""选题别要娱乐新闻"，先看能不能改配置解决。改配置解决不了才动代码。
