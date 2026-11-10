from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src import cues, images, metrics, publish, review, script, select
from src.pipeline import run_pipeline
from src.profiles import SCORING, names as profile_names, resolve


def _fake_transcript(duration: float = 300.0, step: float = 3.0) -> dict:
    segments = []
    for index in range(int(duration / step)):
        start = index * step
        segments.append(
            {
                "start": start,
                "end": start + step,
                # 每 5 句放一个数字句，验证打分权重生效
                "text": f"第{index}个客户数据是{index * 7}万元。" if index % 5 == 0 else f"这是第{index}句普通说明。",
            }
        )
    return {"language": "zh", "segments": segments, "text": "", "duration": duration}


def test_cues_merge_and_keep_words_whole():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "很多公司"},
        {"start": 1.0, "end": 2.0, "text": "想用AI"},
        {"start": 2.0, "end": 3.0, "text": "但是你一定要搞清楚"},
        {"start": 3.0, "end": 4.0, "text": "AI到底能干什么。"},
        {"start": 8.0, "end": 9.0, "text": "这句前面有大停顿"},
    ]
    cfg = {"chars_per_line": 10, "lines": 2, "min_cue": 1.0, "max_cue": 4.0, "merge_gap": 0.8}
    result = cues.build(segments, cfg)
    texts = [cue["text"] for cue in result]
    assert any("很多公司想用AI" in text for text in texts), texts
    assert all(text.strip() for text in texts)
    assert all(cue["end"] - cue["start"] >= 0.99 for cue in result), "字幕不能一闪而过"
    # 无标点长串按字数切，但不能把 AI 拆到两行
    joined = "".join(texts)
    assert "A I" not in joined


def test_break_point_never_splits_words():
    # 断点必须回退到自然停顿，不能把「解决不了」「就是」劈成两行
    assert images._break_point("最后发现他解决不了问题", 7) == 5
    assert images._break_point("这事儿说白了就是信息差", 7) == 6
    assert images._break_point("花十几万上AI最后还是失败", 7) == 5
    # 边界：整行放得下 / 空串不应崩
    assert images._break_point("短句", 2) == 2
    assert images._break_point("", 0) == 0


def test_profiles_have_required_fields():
    assert profile_names(), "至少要有一个版本配置"
    for key in profile_names():
        prof = resolve(key)
        assert prof["duration"]["target"] > 0, key
        assert prof["pacing"]["shot_min"] < prof["pacing"]["shot_max"], key
        assert prof["platforms"], key


def test_review_roundtrip(tmp_path: Path):
    transcript = _fake_transcript(30)
    scores = select.score_segments(transcript["segments"], SCORING)
    chosen = [0, 2, 5]
    path = review.write(
        tmp_path / "选段.md", transcript["segments"], scores, chosen,
        {"key": "short", "name": "短版", "duration": {"target": 75}}, 30.0,
    )
    assert review.read(path) == chosen

    text = path.read_text(encoding="utf-8").replace("- [x] 002", "- [ ] 002")
    path.write_text(text, encoding="utf-8")
    assert review.read(path) == [0, 5]


def test_short_selection_hits_target():
    transcript = _fake_transcript(300)
    prof = resolve("short")
    target = prof["duration"]["target"]
    plan = select.plan(
        transcript, 300.0, target, SCORING,
        prof["selection"].get("pad", 0.06), bool(prof["hook"]["enabled"]),
    )
    ranges = plan["ranges"]
    total = sum(end - start for start, end in ranges)
    assert ranges, "必须选出至少一段"
    assert 0.75 * target <= total <= 1.15 * target, f"实际 {total:.1f}s，目标 {target}s"
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert next_start >= prev_end - 1e-6, "时间轴不能重叠"


def test_script_outline_matches_duration():
    sections = script._sections(290)
    assert abs(sum(s["seconds"] for s in sections) - 290) < 1.5
    assert all(s["hint"] and s["chars"] > 0 for s in sections), "每段都要有写作提示和字数目标"
    # 260 字/分 × 4 分 50 秒 ≈ 1256 字
    assert 1200 <= sum(s["chars"] for s in sections) <= 1350
    # 时长翻倍，字数也跟着翻倍
    assert 2450 <= sum(s["chars"] for s in script._sections(580)) <= 2650


def test_short_title_cuts_at_clause():
    long = "失业缓冲期首次出现在国家政策内，以应对人工智能带来的冲击，怎么看待这一政策？"
    assert script._short_title(long) == "失业缓冲期首次出现在国家政策内"
    assert script._short_title("短标题") == "短标题"


def test_publish_parse_copy(tmp_path: Path):
    (tmp_path / "copy_douyin_decision.md").write_text(
        "# 抖音 · 决策者版\n\n## 标题\n老板别急着上AI\n\n"
        "## 正文\n第一段讲成本\n第二段讲代价\n\n## 标签\n#AI #转型\n",
        encoding="utf-8",
    )
    copy = publish._read_copy(tmp_path, "douyin")
    assert copy["title"] == "老板别急着上AI"
    assert "第一段讲成本" in copy["body"] and "第二段讲代价" in copy["body"]
    assert copy["tags"] == "#AI #转型"
    # 没配这个平台的文案时返回空，不抛错
    assert publish._read_copy(tmp_path, "xhs") == {}


def test_metrics_weekly_reads_data(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(metrics, "DB", tmp_path / "m.db")
    monkeypatch.setattr(metrics, "DATA", tmp_path)
    for title, views, likes in (("A", 1000, 50), ("B", 8000, 600), ("C", 100, 1)):
        metrics.add({"platform": "douyin", "title": title, "views": views, "likes": likes})

    path = metrics.weekly(7)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "数据周报" in text
    assert "8,000" in text            # 播放合计
    assert "倍" in text               # 头名是中位数 8 倍，应给出"再拆一条"的建议


def test_metrics_csv_import(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(metrics, "DB", tmp_path / "m.db")
    source = tmp_path / "in.csv"
    source.write_text("platform,title,views,likes\nbilibili,测试视频,500,10\n", encoding="utf-8")
    assert metrics.import_csv(source) == 1
    items = metrics.rows()
    assert len(items) == 1 and items[0]["views"] == 500


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg")
def test_pipeline_end_to_end(tmp_path: Path):
    source = tmp_path / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0B0F17:s=540x960:d=12:r=30",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=12",
         "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True, capture_output=True,
    )
    srt = tmp_path / "in.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\n这是第一句话。\n\n"
        "2\n00:00:03,000 --> 00:00:06,000\n这是第二句话，有数字30。\n\n"
        "3\n00:00:06,000 --> 00:00:09,000\n这是第三句话。\n\n"
        "4\n00:00:09,000 --> 00:00:12,000\n这是第四句话。\n",
        encoding="utf-8",
    )
    targets = run_pipeline(source=source, profiles=["short"], srt=srt, title="冒烟测试")
    assert targets, "没有产出"
    final = targets[0] / "final.mp4"
    assert final.exists() and final.stat().st_size > 10_000
    assert (targets[0] / "cover.png").exists()
    assert list(targets[0].glob("copy_douyin*")), "缺少抖音文案"
