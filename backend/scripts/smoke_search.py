"""联网检索冒烟：真实调用 Tavily + 真实模型，验证「取资料 → 大纲 → 出题」整条链路。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\smoke_search.py                    # 默认：新知识（关键词检索）
    .\\.venv\\Scripts\\python.exe scripts\\smoke_search.py --repeat 3         # 连续跑 3 次
    .\\.venv\\Scripts\\python.exe scripts\\smoke_search.py --url https://...  # 网址输入（抓整页正文）

成本：每次完整学习约 0.05–0.1 元（模型）+ 1–4 个 Tavily credits。
脚本只打印统计结果与摘要，不打印任何密钥。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services.llm import build_provider  # noqa: E402
from app.services.outline_service import UNVERIFIED_MARK, generate_outline  # noqa: E402
from app.services.quality import (  # noqa: E402
    audit_question_set,
    fatal_issues,
    warning_issues,
)
from app.services.question_service import generate_question_set  # noqa: E402
from app.services.search import (  # noqa: E402
    KnowledgeTraits,
    build_search_provider,
    gather_references,
)

#: 模型训练数据里没有的「新知识」：用来验证系统会不会靠联网资料纠正自己
SAMPLE_TEXT = (
    "Harness Engineering：围绕 AI 编码代理（coding agent）的一套工程实践。"
    "我想搞清楚它的准确定义、它要解决的核心问题，以及实际落地时具体怎么做。"
)


class _LogCollector(logging.Handler):
    """收集检索相关日志，用来回报「抓到多长正文」「拿到几条资料」等真实数字。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def last_attr(self, name: str):
        for record in reversed(self.records):
            if hasattr(record, name):
                return getattr(record, name)
        return None


def _describe_grounding(label: str, grounding, collector: _LogCollector) -> int:
    """打印一次取资料的结果，返回消耗的 credits。"""
    if grounding.ok:
        print(
            f"[{label}] 拿到 {len(grounding.references)} 条资料"
            f"（credits {grounding.credits}，耗时 {collector.last_attr('latency_ms')}ms，"
            f"取整页正文 {collector.last_attr('include_raw_content')}）"
        )
        for hit in grounding.references[:3]:
            print(f"        来源：{hit.url}")
    else:
        print(f"[{label}] 没有可用资料（原因：{grounding.reason}）")
    return grounding.credits or 0


def run_once(
    index: int,
    total: int,
    *,
    text: str,
    url: str | None,
    settings,
    provider,
    search,
) -> tuple[bool, int]:
    collector = _LogCollector()
    # 注意：检索相关的日志分属两个 logger —— 取资料的编排在 app.search，
    # 而「按网址抓到正文」这条是 app.outline 发的，两个都要挂才能统计全。
    watched = [logging.getLogger(name) for name in ("app.search", "app.outline")]
    for logger in watched:
        logger.disabled = False
        logger.addHandler(collector)
        logger.setLevel(logging.INFO)

    prefix = f"[{index}/{total}]"
    print(f"\n{prefix} 输入：{url or text}")
    credits = 0
    try:
        outline = generate_outline(provider, url or text, settings, search=search)
    except AppError as exc:
        print(f"{prefix} [失败] 大纲生成失败：{exc.code} - {exc.message}")
        return False, credits
    finally:
        for logger in watched:
            logger.removeHandler(collector)

    if url:
        chars = collector.last_attr("chars")
        print(f"{prefix} [抽取] 抓到正文 {chars} 字（来源 {outline.source_url}）")

    credits += _describe_grounding("资料·大纲", outline.grounding, collector)
    marked = any(UNVERIFIED_MARK in point.summary for point in outline.payload.points)
    outline_cost = provider.cost_estimate(outline.call.llm.usage)
    print(
        f"{prefix} [大纲] {outline.payload.title}"
        f"（模型调用 {outline.attempts} 次，约 {outline_cost:.4f} 元，"
        f"{'带未联网核实标注' if marked else '已由资料支撑'}）"
    )
    for point in outline.payload.points:
        print(f"          - {point.id}｜{point.title}：{point.summary}")

    points = list(outline.payload.points)
    # 与 level_service 的真实路径一致：出题阶段按知识点再取一次资料
    grounding = gather_references(
        search,
        queries=[point.title for point in points][: settings.search_max_queries],
        traits=KnowledgeTraits(complexity="complex"),
        settings=settings,
        purpose="levels",
    )
    credits += _describe_grounding("资料·出题", grounding, collector)

    try:
        result = generate_question_set(
            provider, points, settings, references=grounding.references
        )
    except AppError as exc:
        print(f"{prefix} [失败] 出题失败：{exc.code} - {exc.message}")
        return False, credits

    issues = audit_question_set(
        result.payload.to_payload(),
        total_levels=settings.total_level_count,
        per_level=settings.questions_per_level,
    )
    per_level: dict[int, int] = {}
    for question in result.payload.questions:
        per_level[question.level_seq] = per_level.get(question.level_seq, 0) + 1
    fatal = fatal_issues(issues)
    warn = warning_issues(issues)
    question_cost = provider.cost_estimate(result.call.llm.usage)
    print(
        f"{prefix} [出题] {len(result.payload.questions)} 题，"
        f"各关 {dict(sorted(per_level.items()))}，"
        f"重生 {result.regenerated} / 丢弃 {result.dropped} / 补题 {result.backfilled}，"
        f"致命问题 {len(fatal)}，警告 {len(warn)}，约 {question_cost:.4f} 元"
    )
    for issue in warn[:3]:
        print(f"          ! {issue.code} {issue.where}：{issue.message}")
    print(
        f"{prefix} [成本] 模型合计约 {outline_cost + question_cost:.4f} 元 + {credits} credits"
    )
    return not fatal, credits


def main() -> int:
    parser = argparse.ArgumentParser(description="联网检索 + 出题的真实冒烟")
    parser.add_argument("--text", default=SAMPLE_TEXT, help="要学习的知识文本（默认用新知识样例）")
    parser.add_argument("--url", default=None, help="改用网址输入（会抓整页正文）")
    parser.add_argument("--repeat", type=int, default=1, help="连续跑几次")
    args = parser.parse_args()

    settings = get_settings()
    print(
        f"[配置] 模型 {settings.llm_provider}/{settings.active_model}｜"
        f"检索 {settings.search_effective_mode}"
        f"（条数 {settings.search_max_results_min}-{settings.search_max_results_max}，"
        f"每日上限 {settings.daily_search_quota}）"
    )
    if not settings.search_enabled:
        print("[退出] 检索没有启用（缺少 TAVILY_API_KEY，或 SEARCH_MODE=off）")
        return 1

    provider = build_provider(settings)
    search = build_search_provider(settings)
    print(f"[配置] 检索实现：{search.name}")

    ok_runs = 0
    total_credits = 0
    for index in range(1, args.repeat + 1):
        ok, credits = run_once(
            index,
            args.repeat,
            text=args.text,
            url=args.url,
            settings=settings,
            provider=provider,
            search=search,
        )
        total_credits += credits
        ok_runs += 1 if ok else 0

    print(f"\n[汇总] {ok_runs}/{args.repeat} 次通过，共消耗 {total_credits} credits")
    return 0 if ok_runs == args.repeat else 1


if __name__ == "__main__":
    raise SystemExit(main())
