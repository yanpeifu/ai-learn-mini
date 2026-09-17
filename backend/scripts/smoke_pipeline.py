"""端到端真实冒烟：一段知识文本 → 大纲 → 15 道题 → 质量校验报告。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\smoke_pipeline.py

成本：一次完整学习约 0.02–0.05 元（与 PRD 的成本目标一致）。
脚本只打印统计结果与题目摘要，不打印任何密钥。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services.llm import build_provider  # noqa: E402
from app.services.outline_service import generate_outline  # noqa: E402
from app.services.quality import audit_question_set, fatal_issues, warning_issues  # noqa: E402
from app.services.question_service import generate_question_set  # noqa: E402

SAMPLE_TEXT = (
    "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例。"
    "提高准备金率会减少商业银行可用于放贷的资金，是货币政策三大工具之一。"
    "另外两个工具是再贴现率和公开市场操作：再贴现率是商业银行向央行借款的利率，"
    "提高它会抑制银行借款；公开市场操作则是央行在市场上买卖证券，"
    "买入证券投放基础货币、卖出证券回笼资金。三大工具的灵活性和作用强度不同，"
    "公开市场操作可以小额高频微调，准备金率则是作用猛烈的重武器。"
)


def main() -> int:
    settings = get_settings()
    provider = build_provider(settings)
    print(
        f"[配置] provider={settings.llm_provider} model={settings.active_model} "
        f"structured={settings.llm_structured_method} "
        f"levels={settings.total_level_count}x{settings.questions_per_level}"
    )

    total_cost = 0.0
    try:
        outline = generate_outline(provider, SAMPLE_TEXT, settings)
    except AppError as exc:
        print(f"[失败] 大纲生成失败：{exc.code} - {exc.message}")
        return 1

    points = outline.payload.points
    outline_cost = provider.cost_estimate(outline.call.llm.usage)
    total_cost += outline_cost
    print(f"[大纲] {outline.payload.title}（尝试 {outline.attempts} 次，约 {outline_cost:.4f} 元）")
    print(f"   token：输入 {outline.call.llm.usage.prompt_tokens if outline.call.llm.usage else 'n/a'} / "
          f"输出 {outline.call.llm.usage.completion_tokens if outline.call.llm.usage else 'n/a'}")
    for point in points:
        print(f"   - {point.id}｜{point.title}：{point.summary}")

    try:
        result = generate_question_set(provider, list(points), settings)
    except AppError as exc:
        print(f"[失败] 出题失败：{exc.code} - {exc.message}")
        return 1

    total_cost += provider.cost_estimate(result.call.llm.usage)
    usage = result.call.llm.usage
    print(
        f"[出题] token：输入 {usage.prompt_tokens if usage else 'n/a'} / "
        f"输出 {usage.completion_tokens if usage else 'n/a'}，"
        f"耗时 {result.call.llm.latency_ms}ms"
    )
    per_level: dict[int, int] = {}
    for question in result.payload.questions:
        per_level[question.level_seq] = per_level.get(question.level_seq, 0) + 1

    issues = audit_question_set(
        result.payload.to_payload(),
        total_levels=settings.total_level_count,
        per_level=settings.questions_per_level,
    )
    print(
        f"[题库] 共 {len(result.payload.questions)} 题，各关题数 {dict(sorted(per_level.items()))}，"
        f"重生 {result.regenerated} 题，丢弃 {result.dropped} 题，补题 {result.backfilled} 题"
    )
    print(f"[质量] 致命问题 {len(fatal_issues(issues))} 个，警告 {len(warning_issues(issues))} 个")
    for issue in warning_issues(issues)[:5]:
        print(f"   ! {issue.code} {issue.where}：{issue.message}")
    print(f"[成本] 本次完整学习约 {total_cost:.4f} 元")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
