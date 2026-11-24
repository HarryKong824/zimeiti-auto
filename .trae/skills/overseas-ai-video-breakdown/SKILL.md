---
name: overseas-ai-video-breakdown
description: 将海外 AI 博主热门视频加工成带证据分级、结构拆解和原创中文口播稿的批量拆解库。用户要求海外 AI 视频复用拆解、博主选题库、pickscribe 转写加工或批量口播稿校验时使用，不用于逐字翻译或脱离来源编造内容。
---

# 海外 AI 热门视频拆解流水线

把博主频道变成可录制的中文拆解库。默认每位博主 50 条，但条数、分类和批次以用户要求为准。

项目根目录是 Skill 目录向上三级，即 `<project>/.trae/skills/overseas-ai-video-breakdown/` 对应的 `<project>`。成品写入用户指定的 `outbox` 目录；网页、转写、清单和测试输出写入当前工作区 `_work/overseas-ai-video-breakdown/<creator>/`，不要混入成品目录。

## 启动时先确认

先梳理博主、频道 ID、条数、编号前缀、分类、输出路径和证据来源。缺什么只问什么；用户已明确授权直接执行时，不重复确认。

分类必须服从博主真实内容。没有副业、避坑或模板素材时，改分类配额，不硬凑。每条必须有独立来源、独立拆解和独立口播稿，禁止用“同上”“已覆盖”“跳过”凑数。

## 标准流程

### 1. 建工作目录与选题清单

优先按播放量倒序抓频道分页，再按受众相关性筛选。受众默认是想学 AI、转行、创业或寻找副业机会的人。

```powershell
python .trae/skills/overseas-ai-video-breakdown/scripts/pickscribe_pipeline.py channel --channel-id CHANNEL_ID --pages 1 2 3 --out WORK_DIR/channel
```

脚本会从 `/v/<video_id>` 相对链接提取 ID 并去重。抓不到时再用浏览器或 WebFetch 获取频道分页，不假定 YouTube 可以直连。

### 2. 补来源并定证据等级

- A：pickscribe 完整转写，且已抽查开头、结尾和正文完整性。
- B：classcentral 等结构化简介，只有摘要，没有完整转写；正式录制前必须补看原片。
- C：只有标题或短摘。只能进候选池，不得据此写具体步骤、数字或引语。

pickscribe 覆盖不足时，用 WebSearch、classcentral 或原片页面补候选。不得把搜索结果摘要升级成 A，不得补猜转写。

### 3. 下载并解析转写

把候选 ID 保存为每行一个的 `ids.txt`，然后执行：

```powershell
python .trae/skills/overseas-ai-video-breakdown/scripts/pickscribe_pipeline.py fetch --ids-file WORK_DIR/ids.txt --out WORK_DIR/raw --workers 6 --timeout 60 --retries 3
python .trae/skills/overseas-ai-video-breakdown/scripts/pickscribe_pipeline.py parse --raw WORK_DIR/raw --out WORK_DIR/clean
```

解析结果包含标题、播放量、时长、字数和清洗文本。`needs_review` 只表示自动检查未通过，不可直接写成 A。播放量抓不到就写“未核实”，时长不能确认也写“未核实”。

网络 502 或超时通常是瞬时错误。重新执行 `fetch` 会跳过已有文件，只重试缺件；不要无上限循环，不要改装浏览器渲染框架。

### 4. 选题、去重与定配额

按“热度、受众相关性、可复用性、证据质量”排序。检查视频 ID、原标题和主题三层重复：

- 同一视频只能出现一次。
- 同一主题重复出现时，必须有不同来源和不同可复用角度，否则换题。
- 真实分类不足时调整配额，并在头部记录实际分布。

### 5. 逐条写拆解

先复制 [assets/library-template.md](assets/library-template.md)，再逐条替换占位符。写稿前阅读 [references/quality-gates.md](references/quality-gates.md)。

每条固定包含：原视频、链接、时长、播放量、资料页、证据等级、适合人群、原文参考关键词、结构拆解表、独立中文原创口播稿、口径与待实测。

拆解稿保留海外工具原名，如 n8n、Supabase、Pinecone、Claude、CrewAI。正式录制版才替换为 WorkBuddy、豆包工作、即梦、可灵、Trae、飞书 aily 等国内产品；没有同等功能时不得声称完全等价。

### 6. 校验并返修

```powershell
python .trae/skills/overseas-ai-video-breakdown/scripts/validate_library.py OUTPUT.md --prefix M --count 50
```

先修所有 ERROR，再逐条处理 WARN。脚本只检查可自动判定的项目；首句钩子、案例占比、数字溯源、转折有效性、结尾动作和证据完整性仍需人工复核。存在未处理警告时，只能说“结构校验通过”，不能说“全部细则通过”。

### 7. 交付

汇报实际条数、分类分布、A/B/C 数量、文件路径和未解决项。不要在未校验时声称全部通过，不要贴完整英文转写。

## 已有成品编辑纪律

- 修改已有 Markdown 只用精确编辑或追加，不整文件覆盖。
- 每次追加后检查编号、代码块和章节数，避免截断或覆盖前一批。
- 过渡笔记放在工作区，不作为成品里的二级标题。
- PowerShell 5 不用 `&&` 或 `||`；复杂 Python 写入 `.py` 后运行，不在命令行塞多行脚本。

## 硬边界

1. 不逐字搬运，不交付完整英文原文，不做逐句翻译冒充原创。
2. 不编造播放量、收入、报价、客户、效果、引语或测试结论。
3. 收入、报价和播放量在口播中必须带“未核实”“案例价”“他的结果”等适当限定。
4. 不承诺“月入 X 万”“三天回本”，不把 demo 写成已上线成果。
5. 未亲自实测的功能、成本、速度和国内访问稳定性，统一列入“待实测”。
6. 涉及录音、手机号、客户隐私和平台规则时，保留告知、授权与人工审核要求。
