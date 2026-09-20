"""结构化日志：每次 LLM 调用都要能查到 providers/耗时/token（M1-02 验收）。"""

import json
import logging

import pytest
from app.core.logging import HumanFormatter, JsonFormatter, configure_logging, log_llm_call


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_emits_structured_fields() -> None:
    record = logging.LogRecord(
        name="app.services.llm",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="llm call finished",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace-1"

    payload = _format(record)

    assert payload["level"] == "INFO"
    assert payload["msg"] == "llm call finished"
    assert payload["trace_id"] == "trace-1"
    assert payload["ts"]


def test_log_llm_call_records_cost_related_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.llm"):
        log_llm_call(
            provider="deepseek",
            model="deepseek-chat",
            purpose="outline",
            latency_ms=1234,
            prompt_tokens=600,
            completion_tokens=3500,
            estimated_cost=0.015,
        )

    assert caplog.records, "应至少产生一条日志"
    record = caplog.records[-1]
    assert record.provider == "deepseek"
    assert record.model == "deepseek-chat"
    assert record.latency_ms == 1234
    assert record.total_tokens == 4100
    assert record.estimated_cost == 0.015


def test_human_formatter_outputs_readable_chinese() -> None:
    """默认格式是中文可读文本：级别、字段名、用途、错误码都翻译成中文。"""
    record = logging.LogRecord(
        name="app.llm",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="大模型调用成功（生成关卡与题目）",
        args=(),
        exc_info=None,
    )
    record.purpose = "levels"
    record.latency_ms = 41600
    record.estimated_cost = 0.0519

    line = HumanFormatter().format(record)

    assert "[信息]" in line
    assert "大模型调用成功" in line
    assert "用途=生成关卡与题目" in line
    assert "耗时(毫秒)=41600" in line
    assert "预计花费(元)=0.0519" in line


def test_human_formatter_translates_codes_and_levels() -> None:
    record = logging.LogRecord(
        name="app.error",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="业务处理失败",
        args=(),
        exc_info=None,
    )
    record.code = "LLM_UNAVAILABLE"
    record.error_type = "LLMTimeoutError"

    line = HumanFormatter().format(record)

    assert "[警告]" in line
    assert "错误码=模型服务不可用（通常是密钥或余额问题）" in line
    assert "错误类型=模型响应太慢" in line


def test_configure_logging_defaults_to_chinese_human_format() -> None:
    configure_logging("WARNING")

    formatter = logging.getLogger().handlers[0].formatter

    assert isinstance(formatter, HumanFormatter)
