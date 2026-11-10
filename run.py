from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import WORK, ensure_dirs, load_dotenv  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

DEMO_LINES = [
    "先说结论，这件事根本没有你想的那么难。",
    "真正难的不是技术，是你能不能坚持下去。",
    "我用了三个月，把剪辑从每天三小时压到二十分钟。",
    "第一件事，把所有重复动作列出来。",
    "第二件事，能写成规则的就不要靠脑子记。",
    "第三件事，把不确定性关进模板里。",
    "数据不会骗人，播放量掉了就是内容出了问题。",
    "所以别急着上工具，先想清楚你的流程。",
]


def _demo_source() -> tuple[Path, Path]:
    ensure_dirs()
    demo_dir = WORK / "_demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    video = demo_dir / "demo.mp4"
    srt = demo_dir / "demo.srt"

    lines = DEMO_LINES * 5
    duration = len(lines) * 3

    if not video.exists():
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x0B0F17:s=1080x1920:d={duration}:r=30",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-shortest", "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
            ],
            check=True,
            capture_output=True,
        )

    def stamp(seconds: float) -> str:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},000"

    blocks = []
    for index, line in enumerate(lines):
        start, end = index * 3, index * 3 + 3
        blocks.append(f"{index + 1}\n{stamp(start)} --> {stamp(end)}\n{line}\n")
    srt.write_text("\n".join(blocks), encoding="utf-8")
    return video, srt


def main() -> None:
    parser = argparse.ArgumentParser(description="自媒体全自动化 · P0 流水线")
    parser.add_argument("--input", help="口播视频或音频路径")
    parser.add_argument("--demo", action="store_true", help="用内置样例跑通全流程")
    parser.add_argument("--platforms", default="", help="逗号分隔，留空则用各版本预设：douyin,xhs,bilibili,shipinhao,x")
    parser.add_argument("--profiles", default="all", help="逗号分隔：short,mid,long，或 all")
    parser.add_argument("--topics", action="store_true", help="只跑选题：抓公开热榜，出每日选题清单")
    parser.add_argument("--top-n", type=int, default=0, help="选题条数，默认读配置")
    parser.add_argument("--script", default=None, help="给主题，直接生成口播稿")
    parser.add_argument("--script-topic", type=int, default=0, help="从今日选题清单取第 N 条生成口播稿")
    parser.add_argument("--minutes", type=float, default=0, help="口播目标时长（分钟），默认读配置 4.8")
    parser.add_argument("--publish", default="", help="成品目录，如 outbox/<job>/short")
    parser.add_argument("--to", default="douyin", help="发布平台，逗号分隔：douyin,xhs,bilibili,shipinhao")
    parser.add_argument("--no-wait", action="store_true", help="不等待人工确认，填完直接关浏览器")
    parser.add_argument("--stats", action="store_true", help="生成数据周报")
    parser.add_argument("--stats-import", default="", help="导入后台导出的 CSV，然后出周报")
    parser.add_argument("--stats-template", action="store_true", help="生成 CSV 模板")
    parser.add_argument("--days", type=int, default=7, help="周报统计天数，默认 7")
    parser.add_argument("--resume", default="", help="续跑：work 下的 job 目录名，复用已有转写")
    parser.add_argument("--review", action="store_true", help="强制先出选段清单，等你确认后再剪")
    parser.add_argument("--provider", default="placeholder", choices=["placeholder", "comfyui", "api"])
    parser.add_argument("--srt", help="已有字幕文件（跳过转写）")
    parser.add_argument("--title", default="", help="标题提示")
    parser.add_argument("--check", action="store_true", help="环境自检：ffmpeg、依赖、字体、目录")
    args = parser.parse_args()

    load_dotenv()

    if args.check:
        from src.health import check

        sys.exit(check(network=True))

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    if not profiles or profiles == ["all"]:
        profiles = None

    if args.demo:
        source, srt = _demo_source()
        args.input = str(source)
        args.srt = str(srt)

    if args.topics:
        from src import topics

        print(topics.run(args.top_n or None))
        return

    if args.script is not None or args.script_topic:
        from src import script

        seconds = args.minutes * 60 if args.minutes else 0
        print(script.run(args.script or "", args.script_topic, seconds))
        return

    if args.publish:
        from src import publish

        target = Path(args.publish)
        if not target.exists():
            parser.error(f"目录不存在：{target}")
        names = [n.strip() for n in args.to.split(",") if n.strip()]
        publish.run(target, names, confirm=not args.no_wait)
        return

    if args.stats_template:
        from src import metrics

        print(metrics.template())
        return

    if args.stats_import:
        from src import metrics

        count = metrics.import_csv(Path(args.stats_import))
        print(f"导入 {count} 条")
        print(metrics.weekly(args.days))
        return

    if args.stats:
        from src import metrics

        print(metrics.weekly(args.days))
        return

    if not args.input and not args.resume:
        parser.error("需要 --input，或使用 --demo / --resume")

    targets = run_pipeline(
        source=args.input or None,
        profiles=profiles,
        platforms=platforms or None,
        provider=args.provider,
        srt=args.srt,
        title=args.title,
        resume=args.resume or None,
        force_review=args.review,
    )
    for target in targets:
        print(target)


if __name__ == "__main__":
    main()
