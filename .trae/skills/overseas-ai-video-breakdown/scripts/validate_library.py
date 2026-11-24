#!/usr/bin/env python3
"""校验海外 AI 视频拆解库的章节、口播稿和常见硬性格式问题。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[._/@:-][A-Za-z0-9]+)*|"
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
TRANSITION_RE = re.compile(r"^(?:但|不过|然而|等等|问题是|可问题是|其实|没想到|他们没|只是|真正的问题)")
FORBIDDEN_EARNING_RE = re.compile(r"月入\s*\d+\s*万|三天回本")
ABSTRACT_RE = re.compile(r"真正值得学的|本质上|值得深思|核心逻辑|底层逻辑|赋能|闭环|抓手|总而言之|拥抱变化")
ALLOWED_H2 = {"分类与配额", "总目录", "使用说明", "工具替换清单", "合规提醒"}
REQUIRED_FIELDS = ("原视频", "链接", "资料页", "证据等级", "适合", "原文参考", "结构拆解", "口径与待实测")


def units(text: str) -> int:
    """中文逐字，连续英文/数字/工具标识按一个词元，标点与空白不计。"""
    return len(TOKEN_RE.findall(text))


def sentences(script: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。！？!?；;\n]+", script) if item.strip()]


def check_entry(section: str, entry_id: str, min_chars: int, max_chars: int) -> list[dict]:
    issues = []

    def add(level: str, code: str, message: str) -> None:
        issues.append({"entry": entry_id, "level": level, "code": code, "message": message})

    for field in REQUIRED_FIELDS:
        if field not in section:
            add("error", "missing_field", f"缺少字段：{field}")
    grade_match = re.search(r"证据等级\s*(?:\*\*)?\s*[：:]?\s*(?:\*\*)?\s*([ABC])", section)
    if not grade_match:
        add("error", "invalid_grade", "证据等级必须明确写 A、B 或 C")
    elif grade_match.group(1) == "A" and "pickscribe.com/v/" not in section:
        add("error", "grade_source", "A 级条目缺少 pickscribe 资料页")
    if re.search(r"同上|已覆盖|跳过|待补|占位符|替换为\s*260", section):
        add("error", "placeholder", "存在跳过、占位或待补内容")

    scripts = re.findall(r"```text\s*\n(.*?)\n```", section, flags=re.S)
    if len(scripts) != 1:
        add("error", "script_block", f"口播稿 text 代码块应为 1 个，实际 {len(scripts)} 个")
        return issues
    script = scripts[0].strip()
    total = units(script)
    if not min_chars <= total <= max_chars:
        add("error", "script_length", f"全篇 {total} 字，要求 {min_chars}–{max_chars}")

    lines = sentences(script)
    if not lines:
        add("error", "empty_script", "口播稿为空")
        return issues
    first = units(lines[0])
    if not 9 <= first <= 15:
        add("error", "first_sentence", f"首句 {first} 字，可接受范围 9–15，目标 10–14")
    elif first in (9, 15):
        add("warn", "first_sentence_edge", f"首句 {first} 字属于边界，建议改为 10–14 字")
    for index, sentence in enumerate(lines, start=1):
        length = units(sentence)
        if length > 18:
            add("error", "sentence_length", f"第 {index} 句 {length} 字：{sentence}")

    cumulative = 0
    has_mid_transition = False
    for sentence in lines:
        length = units(sentence)
        midpoint = cumulative + length / 2
        ratio = midpoint / total if total else 0
        if 0.4 <= ratio <= 0.6 and length <= 14 and TRANSITION_RE.search(sentence):
            has_mid_transition = True
        cumulative += length
    if not has_mid_transition:
        add("warn", "mid_transition", "40%–60% 处未识别到短句转折，需人工确认")
    for marker in ("第一", "第二", "第三"):
        if marker not in script:
            add("error", "three_steps", f"缺少三步动作标记：{marker}")
    if FORBIDDEN_EARNING_RE.search(script):
        add("error", "earning_claim", "存在月入 X 万或三天回本级禁词")
    abstract = ABSTRACT_RE.findall(script)
    if abstract:
        add("warn", "abstract_words", "存在抽象或总结腔词语：" + "、".join(abstract))
    if len(re.findall(r"不是[^。！？\n]*而是", script)) > 1:
        add("warn", "contrast_overuse", "“不是……而是……”使用超过一次")
    if re.search(r"关注我|点关注|求关注|点个赞|点赞关注", lines[-1]):
        add("warn", "ending_cta", "结尾疑似求关注或点赞")
    return issues


def validate(path: Path, prefix: str, expected_count: int, min_chars: int, max_chars: int) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    entry_pattern = re.compile(rf"(?m)^##\s+({re.escape(prefix)})(\d+)｜([^\n]+)$")
    matches = list(entry_pattern.finditer(text))
    issues: list[dict] = []
    numbers = [int(match.group(2)) for match in matches]
    counts = Counter(numbers)
    for number in sorted(set(numbers)):
        if counts[number] > 1:
            issues.append(
                {
                    "entry": f"{prefix}{number:02d}",
                    "level": "error",
                    "code": "duplicate_number",
                    "message": f"编号重复 {counts[number]} 次",
                }
            )
    for number in range(1, expected_count + 1):
        if counts[number] == 0:
            issues.append(
                {
                    "entry": f"{prefix}{number:02d}",
                    "level": "error",
                    "code": "missing_number",
                    "message": "编号缺失",
                }
            )
    unexpected = [number for number in numbers if number < 1 or number > expected_count]
    for number in unexpected:
        issues.append(
            {
                "entry": f"{prefix}{number:02d}",
                "level": "error",
                "code": "unexpected_number",
                "message": f"编号超出 1–{expected_count}",
            }
        )

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entry_id = f"{prefix}{int(match.group(2)):02d}"
        issues.extend(check_entry(text[match.start():end], entry_id, min_chars, max_chars))

    for heading in re.finditer(r"(?m)^##\s+([^\n]+)$", text):
        title = heading.group(1).strip()
        if entry_pattern.match(heading.group(0)):
            continue
        if title not in ALLOWED_H2:
            issues.append(
                {
                    "entry": "document",
                    "level": "warn",
                    "code": "unexpected_h2",
                    "message": f"非章节二级标题，确认是否残留草稿：{title}",
                }
            )
    errors = sum(issue["level"] == "error" for issue in issues)
    warnings = sum(issue["level"] == "warn" for issue in issues)
    return {
        "file": str(path),
        "prefix": prefix,
        "expected": expected_count,
        "found": len(matches),
        "unique_entries": len(counts),
        "errors": errors,
        "warnings": warnings,
        "issues": issues,
        "units_rule": "中文逐字，连续英文数字及工具标识按一个词元，标点空白不计",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="待校验 Markdown 文件")
    parser.add_argument("--prefix", required=True, help="编号前缀，例如 M、N、L")
    parser.add_argument("--count", type=int, default=50, help="应有条数，默认 50")
    parser.add_argument("--min-chars", type=int, default=260)
    parser.add_argument("--max-chars", type=int, default=390)
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not re.fullmatch(r"[A-Z]+", args.prefix):
        print("prefix 只能是大写英文字母", file=sys.stderr)
        return 2
    if args.count < 1 or args.min_chars < 1 or args.max_chars < args.min_chars:
        print("count 和字数范围参数无效", file=sys.stderr)
        return 2
    path = Path(args.file)
    if not path.is_file():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2
    report = validate(path, args.prefix, args.count, args.min_chars, args.max_chars)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for issue in report["issues"]:
            print(f"[{issue['level'].upper()}] {issue['entry']} {issue['code']}: {issue['message']}")
        print(
            f"SUMMARY entries={report['found']} unique={report['unique_entries']} "
            f"expected={report['expected']} errors={report['errors']} warnings={report['warnings']}"
        )
        print("自动校验不替代数字溯源、首句钩子、案例占比和转写完整性人工复核。")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
