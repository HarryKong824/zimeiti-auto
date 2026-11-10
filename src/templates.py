"""八个镜头模板。

自动化的核心约束：LLM 只能在这 8 个模板里选，不允许自由发挥。
模板固定 = 风格统一 = 可全自动。
"""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "person": {
        "name": "人物中景",
        "motion": "zoom_in",
        "purpose": "观点、结论、自我介绍",
        "prompt": "a single character standing, medium shot, centered, plain backdrop, flat illustration, cinematic lighting",
    },
    "object": {
        "name": "物件特写",
        "motion": "pan_right",
        "purpose": "具体例子、工具、产品",
        "prompt": "close-up of a single object on a clean surface, shallow depth of field, flat illustration, soft rim light",
    },
    "chart": {
        "name": "数据图表",
        "motion": "none",
        "purpose": "数字、对比、趋势",
        "prompt": "minimal bar chart infographic, dark background, single accent color, no text",
    },
    "map": {
        "name": "地图路径",
        "motion": "pan_left",
        "purpose": "地点、流程、路径",
        "prompt": "minimal abstract map with dotted route and location pins, dark background, single accent color, no text",
    },
    "split": {
        "name": "对比双屏",
        "motion": "none",
        "purpose": "A vs B、前后对比",
        "prompt": "split screen comparison, left and right panels, contrasting moods, flat illustration",
    },
    "title": {
        "name": "大字卡",
        "motion": "zoom_in",
        "purpose": "金句、章节标题",
        "prompt": "typographic poster, abstract geometric background, dark, single accent color",
    },
    "quote": {
        "name": "引语卡",
        "motion": "none",
        "purpose": "引用、他人观点",
        "prompt": "editorial quote card, large quotation mark, dark background, minimal",
    },
    "transition": {
        "name": "转场",
        "motion": "none",
        "purpose": "段落切换",
        "prompt": "abstract geometric transition frame, diagonal shapes, dark background, single accent color",
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
