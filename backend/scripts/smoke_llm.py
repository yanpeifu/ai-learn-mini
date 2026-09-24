"""真实模型冒烟测试：验证 LangChain 适配层能连通配置里的供应商并返回结构化数据。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\smoke_llm.py

说明：
- 不打印任何密钥，只打印 provider / model / base_url / 耗时 / token / 估算成本；
- 一次调用成本约 0.001 元（很短的输入输出）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, Field  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.llm import ChatMessage, LLMError, build_provider  # noqa: E402


class SmokeOut(BaseModel):
    """冒烟用的最小结构化输出。"""

    topic: str = Field(description="用不超过 8 个字概括这段知识")
    points: list[str] = Field(description="拆出 3 个知识点，每个不超过 12 个字")


PROMPT = (
    "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例。"
    "提高准备金率会减少商业银行可用于放贷的资金，是货币政策三大工具之一，"
    "另外两个是再贴现率和公开市场操作。"
)


def main() -> int:
    settings = get_settings()
    print(
        f"[配置] provider={settings.llm_provider} model={settings.active_model} "
        f"base_url={settings.active_base_url} structured={settings.llm_structured_method}"
    )
    if not settings.active_api_key:
        print("[失败] 当前供应商没有配置 API Key（检查 .env）")
        return 2

    provider = build_provider(settings)
    try:
        parsed, result = provider.chat_json(
            [
                ChatMessage.system("你是资深教研专家，只输出结构化结果。"),
                ChatMessage.user(f"请把下面的内容拆成知识点：\n{PROMPT}"),
            ],
            SmokeOut,
            purpose="smoke",
        )
    except LLMError as exc:
        print(f"[失败] {type(exc).__name__}: {str(exc)[:200]}")
        print(f"[提示] 错误分类 retryable={exc.retryable} code={exc.code}")
        return 1

    usage = result.usage
    print(f"[成功] topic={parsed.topic!r} points={parsed.points}")
    print(
        f"[用量] latency={result.latency_ms}ms "
        f"prompt_tokens={usage.prompt_tokens if usage else 'n/a'} "
        f"completion_tokens={usage.completion_tokens if usage else 'n/a'} "
        f"cost≈{provider.cost_estimate(usage):.6f} 元"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
