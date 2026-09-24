from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReportReason = Literal["wrong_answer", "unclear", "duplicate", "other"]


class QuestionReportRequest(BaseModel):
    reason: ReportReason
    detail: str | None = Field(default=None, max_length=256)
