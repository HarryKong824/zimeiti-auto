"""八个镜头模板。

自动化的核心约束：LLM 只能在这 8 个模板里选，不允许自由发挥。
模板固定 = 风格统一 = 可全自动。

AI 生图模型通病：写不好中文，容易瞎编伪中文。
所以所有模板都必须显式加 "no text, no letters, no words"。
大字卡/引语卡/图表这类"天生想写字"的模板，用视觉隐喻替代文字描述。
"""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "person": {
        "name": "人物中景",
        "motion": "zoom_in",
        "purpose": "观点、结论、自我介绍",
        "prompt": "a single character standing, medium shot, centered, plain backdrop, cinematic lighting, no text, no letters",
    },
    "object": {
        "name": "物件特写",
        "motion": "pan_right",
        "purpose": "具体例子、工具、产品",
        "prompt": "close-up of a single object on a clean surface, shallow depth of field, soft rim light, no text, no letters",
    },
    "chart": {
        "name": "数据图表",
        "motion": "none",
        "purpose": "数字、对比、趋势",
        "prompt": "abstract visual metaphor for data trend, rising bars of light, glowing particles forming a curve, dark background, single accent color, absolutely no text, no numbers, no letters",
    },
    "map": {
        "name": "地图路径",
        "motion": "pan_left",
        "purpose": "地点、流程、路径",
        "prompt": "minimal abstract landscape with a glowing path winding through, dotted light markers, dark background, single accent color, no text, no labels",
    },
    "split": {
        "name": "对比双屏",
        "motion": "none",
        "purpose": "A vs B、前后对比",
        "prompt": "split screen composition, left side warm and bright, right side dark and cold, contrasting moods, no text, no labels",
    },
    "title": {
        "name": "大字卡（视觉隐喻）",
        "motion": "zoom_in",
        "purpose": "金句开场、章节标题",
        "prompt": "powerful symbolic visual that evokes a key idea — e.g. a spotlight cutting through darkness, a single object standing tall, breaking through a barrier — dramatic lighting, centered composition, dark background, absolutely NO TEXT, no letters, no words anywhere in image",
    },
    "quote": {
        "name": "引语卡（视觉隐喻）",
        "motion": "none",
        "purpose": "引用、他人观点",
        "prompt": "contemplative scene suggesting wisdom or a borrowed idea — e.g. an old open book with light emanating from pages, a statue in quiet pose, soft focus background — absolutely NO TEXT, no letters, no quotation marks as text",
    },
    "transition": {
        "name": "转场",
        "motion": "none",
        "purpose": "段落切换",
        "prompt": "abstract geometric composition, diagonal shapes splitting frame, dark background, single accent color, no text, no letters",
    },
}

# 轮转顺序：保证连续镜头不重复
ROTATION = ["person", "object", "title", "chart", "split", "map", "quote", "transition"]

# 关键词 → 模板的强规则
KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (("百分", "%", "倍", "数据", "增长", "下降", "第一", "排名", "万", "亿"), "chart"),
    (("城市", "国家", "从", "到", "路线", "地图", "地区", "全球", "国内"), "map"),
    (("对比", "相比", "但是", "然而", "以前", "现在", "不同", "区别", "vs"), "split"),
    (("他说", "有人说", "有句话", "引用", "认为", "研究显示"), "quote"),
]


def pick_template(text: str, index: int) -> str:
    for keywords, template in KEYWORD_RULES:
        if any(k in text for k in keywords):
            return template
    return ROTATION[index % len(ROTATION)]
