"""结构化日志：每次 LLM 调用都要能查到 providers/耗时/token（M1-02 验收）。"""

import json
import logging

import pytest
from app.core.logging import JsonFormatter, log_llm_call


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
