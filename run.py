from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import WORK, ensure_dirs, env, load_dotenv, load_yaml  # noqa: E402
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


MEDIA_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".m4v", ".wav", ".mp3", ".m4a", ".aac"}


def _expand_inputs(path: Path) -> list[Path]:
    """--input 传目录时展开成视频/音频列表；传文件时原样返回。"""
    if not path.is_dir():
        return [path]
    files = sorted(
        p for p in path.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS
    )
    if not files:
        raise SystemExit(f"目录里没找到音视频文件：{path}")
    print(f"[批量] {path} 下发现 {len(files)} 个文件", flush=True)
    return files


def _publish_versions(path: Path) -> list[Path]:
    """--publish 传版本目录原样返回；传 job 目录则展开成各版本子目录。"""
    if (path / "final.mp4").exists():
        return [path]
    subs = sorted(p for p in path.iterdir() if p.is_dir() and (p / "final.mp4").exists())
    return subs or [path]


def main() -> None:
    parser = argparse.ArgumentParser(description="自媒体全自动化 · P0 流水线")
    parser.add_argument("--input", help="口播视频/音频路径；传目录则批量处理")
    parser.add_argument("--demo", action="store_true", help="用内置样例跑通全流程")
    parser.add_argument("--platforms", default="", help="逗号分隔，留空则用各版本预设：douyin,xhs,bilibili,shipinhao,x")
    parser.add_argument("--profiles", default="all", help="逗号分隔：short,mid,long，或 all")
    parser.add_argument("--topics", action="store_true", help="只跑选题：抓公开热榜，出每日选题清单")
    parser.add_argument("--top-n", type=int, default=0, help="选题条数，默认读配置")
    parser.add_argument("--script", default=None, help="给主题，直接生成口播稿")
    parser.add_argument("--script-topic", type=int, default=0, help="从今日选题清单取第 N 条生成口播稿")
    parser.add_argument("--minutes", type=float, default=0, help="口播目标时长（分钟），默认读配置 4.8")
    parser.add_argument("--publish", default="", help="成品目录，如 outbox/<job>/short")
    parser.add_argument("--to", default="", help="平台，逗号分隔：douyin,xhs,bilibili,shipinhao,x。发布时默认 douyin，抓数据时默认全部启用")
    parser.add_argument("--no-wait", action="store_true", help="不等待人工确认，填完直接关浏览器")
    parser.add_argument("--account", default="default", help="发布账号名（多账号时区分登录态），如 主号/小号")
    parser.add_argument("--stats", action="store_true", help="生成数据周报")
    parser.add_argument("--stats-import", default="", help="导入后台导出的 CSV，然后出周报")
    parser.add_argument("--stats-template", action="store_true", help="生成 CSV 模板")
    parser.add_argument("--days", type=int, default=7, help="统计/清理的天数，默认 7")
    parser.add_argument("--resume", default="", help="续跑：work 下的 job 目录名，复用已有转写")
    parser.add_argument("--review", action="store_true", help="强制先出选段清单，等你确认后再剪")
    parser.add_argument("--provider", default="", help="出图：placeholder/comfyui/api/siliconflow/dalle3，默认读 IMAGE_PROVIDER 环境变量")
    parser.add_argument("--srt", help="已有字幕文件（跳过转写）")
    parser.add_argument("--title", default="", help="标题提示")
    parser.add_argument("--check", action="store_true", help="环境自检：ffmpeg、依赖、字体、目录")
    parser.add_argument("--cost", action="store_true", help="查看本月 API 花费与预算剩余")
    parser.add_argument("--schedule-install", action="store_true", help="注册定时任务（选题/周报）")
    parser.add_argument("--schedule-remove", action="store_true", help="删除所有定时任务")
    parser.add_argument("--schedule-status", action="store_true", help="查看定时任务状态")
    parser.add_argument("--stats-fetch", action="store_true", help="自动抓取各平台作品数据（需先登录）")
    parser.add_argument("--collect", help="把某版本生成的图收进素材库，如 outbox/xx/short")
    parser.add_argument("--clean", action="store_true", help="清理 work 目录（默认保留 7 天内的）")
    parser.add_argument("--dry-run", action="store_true", help="配合 --clean：只预览不删除")
    parser.add_argument("--watch", action="store_true", help="监听 inbox/ 目录，发现新音视频自动跑流水线")
    parser.add_argument("--interval", type=int, default=30, help="--watch 轮询间隔秒数")
    parser.add_argument("--once", action="store_true", help="配合 --watch：扫一次就退出")
    args = parser.parse_args()

    load_dotenv()

    # 读取用户画像配置（平台/方向/出图/LLM）
    profile = load_yaml("profile.yaml")

    # 出图提供商：CLI > 环境变量 > profile.yaml > placeholder
    provider = (
        args.provider
        or env("IMAGE_PROVIDER")
        or profile.get("image_provider", "placeholder")
    )

    # LLM 提供商：环境变量 > profile.yaml
    if not env("LLM_PROVIDER") and profile.get("llm_provider"):
        os.environ["LLM_PROVIDER"] = str(profile["llm_provider"])

    if args.check:
        from src.health import check

        sys.exit(check(network=True))

    if args.cost:
        from src import providers

        info = providers.monthly_cost()
        print(f"\n本月 API 花费：¥{info['total']:.2f} / ¥{info['budget']:.0f}")
        if info["by_provider"]:
            for prov, cost in info["by_provider"].items():
                print(f"  {prov}: ¥{cost:.2f}")
        print(f"剩余预算：¥{info['remaining']:.2f}\n")
        sys.exit(0)

    if args.schedule_install or args.schedule_remove or args.schedule_status:
        from src import scheduler

        if args.schedule_install:
            sys.exit(scheduler.install())
        if args.schedule_remove:
            sys.exit(scheduler.remove())
        sys.exit(scheduler.status())

    # 平台：CLI > profile.yaml
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    if not platforms:
        platforms = list(profile.get("platforms", []))
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
        names = [n.strip() for n in args.to.split(",") if n.strip()] or ["douyin"]
        versions = _publish_versions(target)
        if len(versions) > 1:
            print(f"[多版本] {target} 下发现 {len(versions)} 个版本，逐个发布", flush=True)
        for version in versions:
            if len(versions) > 1:
                print(f"\n===== 版本：{version.name} =====", flush=True)
            publish.run(version, names, confirm=not args.no_wait, account=args.account)
        return

    if args.collect:
        from src import library

        path = Path(args.collect)
        if not path.exists():
            parser.error(f"目录不存在：{path}")
        n = library.collect_from(path)
        print(f"已收录 {n} 张图到 library/images/（带关键词侧车，下次出图优先复用）")
        return

    if args.clean:
        from src import cleanup

        cleanup.clean(days=args.days, dry_run=args.dry_run)
        return

    if args.watch:
        from src import watchdog

        watchdog.loop(interval=args.interval, once=args.once)
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

    if args.stats_fetch:
        from src import stats_fetch

        names = [n.strip() for n in args.to.split(",") if n.strip()] or None
        stats_fetch.fetch(names, account=args.account)
        return

    if not args.input and not args.resume:
        parser.error("需要 --input，或使用 --demo / --resume")

    sources = _expand_inputs(Path(args.input)) if args.input else [None]
    all_targets: list[Path] = []
    total = len(sources)
    for i, src in enumerate(sources, start=1):
        if total > 1:
            print(f"\n===== 第 {i}/{total} 个：{Path(src).name} =====", flush=True)
        try:
            targets = run_pipeline(
                source=str(src) if src else None,
                profiles=profiles,
                platforms=platforms or None,
                provider=provider,
                srt=args.srt if total == 1 else None,
                title=args.title,
                resume=args.resume or None,
                force_review=args.review,
            )
            all_targets.extend(targets)
        except Exception as exc:
            # 批量时单个失败不中断，其余继续
            print(f"[跳过] {Path(src).name if src else '?'}：{type(exc).__name__} {exc}", flush=True)
            if total == 1:
                raise

    for target in all_targets:
        print(target)


if __name__ == "__main__":
    main()
