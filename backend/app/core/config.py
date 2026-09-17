"""配置加载：pydantic-settings 读取项目根 .env（兼容 quality_check.py 已用的旧变量名）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

LLMProviderName = Literal["deepseek", "bailian", "volcengine", "mock"]
StructuredMethod = Literal["json_schema", "function_calling", "json_mode"]

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "bailian": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "volcengine": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-1-6",
    },
    "mock": {"base_url": "", "model": "mock-model"},
}


class Settings(BaseSettings):
    """全部配置集中在这一个对象里，业务代码通过 get_settings() 或 app.state.settings 取用。"""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    app_name: str = "ai-learn-mini API"
    app_version: str = "0.1.0"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_llm_calls: bool = True

    # ---------- 数据库 ----------
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'ai_learn.db').as_posix()}"
    db_echo: bool = False

    # ---------- 鉴权 ----------
    # 注意：HS256 要求密钥长度 ≥32 字节，太短 PyJWT 会告警；
    # 上线前请在 .env 里换成随机长字符串。
    token_secret: str = "dev-only-secret-please-change-me-32bytes"
    token_algorithm: str = "HS256"
    token_expire_hours: int = 720

    # ---------- 微信 ----------
    wechat_appid: str | None = None
    wechat_secret: str | None = None
    dev_login_enabled: bool = False

    # ---------- 大模型 ----------
    llm_provider: LLMProviderName = "deepseek"
    llm_structured_method: StructuredMethod = "json_mode"
    llm_fallbacks: str = ""
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY"),
    )
    llm_base_url: str = Field(
        default=PROVIDER_PRESETS["deepseek"]["base_url"], validation_alias="LLM_BASE_URL"
    )
    llm_model: str = Field(
        default=PROVIDER_PRESETS["deepseek"]["model"], validation_alias="LLM_MODEL"
    )
    llm_timeout: float = Field(default=180, validation_alias="LLM_TIMEOUT")
    llm_max_retries: int = 2
    llm_temperature: float = 0.7
    llm_input_price_per_million: float = 1.0
    llm_output_price_per_million: float = 4.0

    bailian_api_key: str | None = None
    bailian_base_url: str = PROVIDER_PRESETS["bailian"]["base_url"]
    bailian_model: str = PROVIDER_PRESETS["bailian"]["model"]

    volcengine_api_key: str | None = None
    volcengine_base_url: str = PROVIDER_PRESETS["volcengine"]["base_url"]
    volcengine_model: str = PROVIDER_PRESETS["volcengine"]["model"]

    # ---------- 业务参数（PRD 2.2 / M3-05）----------
    outline_min_points: int = 3
    outline_max_points: int = 5
    raw_text_min_chars: int = 20
    raw_text_max_chars: int = 2000
    total_level_count: int = 3
    questions_per_level: int = 5
    outline_timeout_seconds: int = 30
    levels_timeout_seconds: int = 60
    daily_outline_quota: int = 20
    daily_level_quota: int = 20
    weak_point_threshold: float = 60.0

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    # ---------- 派生属性 ----------
    @property
    def llm_fallback_providers(self) -> list[str]:
        return [item.strip() for item in self.llm_fallbacks.split(",") if item.strip()]

    @property
    def active_api_key(self) -> str | None:
        return {
            "deepseek": self.llm_api_key,
            "bailian": self.bailian_api_key,
            "volcengine": self.volcengine_api_key,
            "mock": "mock",
        }[self.llm_provider]

    @property
    def active_model(self) -> str:
        if self.llm_provider == "deepseek":
            return self.llm_model
        if self.llm_provider == "bailian":
            return self.bailian_model
        if self.llm_provider == "volcengine":
            return self.volcengine_model
        return "mock-model"

    @property
    def active_base_url(self) -> str:
        if self.llm_provider == "deepseek":
            return self.llm_base_url
        if self.llm_provider == "bailian":
            return self.bailian_base_url
        if self.llm_provider == "volcengine":
            return self.volcengine_base_url
        return ""

    def provider_credentials(self, provider: str) -> tuple[str, str, str | None]:
        """返回 (base_url, model, api_key)，供适配层切换供应商使用。"""
        if provider == "deepseek":
            return self.llm_base_url, self.llm_model, self.llm_api_key
        if provider == "bailian":
            return self.bailian_base_url, self.bailian_model, self.bailian_api_key
        if provider == "volcengine":
            return self.volcengine_base_url, self.volcengine_model, self.volcengine_api_key
        return "", "mock-model", "mock"


@lru_cache
def get_settings() -> Settings:
    """带缓存，避免每个请求重复读 .env；测试里可直接构造 Settings 覆盖。"""
    return Settings()
