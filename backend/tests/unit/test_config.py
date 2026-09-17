"""配置加载测试：.env 兼容旧变量名（DEEPSEEK_API_KEY / LLM_BASE_URL / LLM_MODEL / LLM_TIMEOUT）。"""

from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_defaults_without_env_file() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_prefix == "/api"
    assert settings.llm_provider == "deepseek"
    assert settings.llm_structured_method == "json_mode"
    assert settings.llm_base_url == "https://api.deepseek.com/v1"
    assert settings.daily_outline_quota == 20
    assert settings.daily_level_quota == 20
    assert settings.total_level_count == 3
    assert settings.questions_per_level == 5
    assert settings.dev_login_enabled is False


def test_reads_legacy_env_names(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-legacy-key",
                "LLM_BASE_URL=https://api.deepseek.com",
                "LLM_MODEL=deepseek-flash",
                "LLM_TIMEOUT=90",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_api_key == "sk-legacy-key"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-flash"
    assert settings.llm_timeout == 90


def test_new_provider_switch_via_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=bailian",
                "LLM_STRUCTURED_METHOD=function_calling",
                "BAILIAN_API_KEY=sk-bailian",
                "BAILIAN_MODEL=qwen-plus",
                "LLM_FALLBACKS=volcengine",
                "DEV_LOGIN_ENABLED=true",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_provider == "bailian"
    assert settings.llm_structured_method == "function_calling"
    assert settings.llm_fallback_providers == ["volcengine"]
    assert settings.dev_login_enabled is True
    # 当前 provider 的 Key 与模型要能解析对
    assert settings.active_api_key == "sk-bailian"
    assert settings.active_model == "qwen-plus"
    assert settings.active_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_deepseek_active_values_come_from_legacy_fields(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-ds\nLLM_MODEL=deepseek-chat\n", encoding="utf-8"
    )

    settings = Settings(_env_file=env_file)

    assert settings.active_api_key == "sk-ds"
    assert settings.active_model == "deepseek-chat"
    assert settings.active_base_url == "https://api.deepseek.com/v1"


def test_invalid_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="not-a-provider")


def test_fallback_parsing_ignores_blanks() -> None:
    settings = Settings(_env_file=None, llm_fallbacks="bailian, , volcengine ,")

    assert settings.llm_fallback_providers == ["bailian", "volcengine"]
