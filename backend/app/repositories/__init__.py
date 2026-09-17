"""数据访问层：每张表的基础 CRUD 封装（业务层不直接写 ORM 查询）。"""

from app.repositories.base import BaseRepository
from app.repositories.entities import (
    AnswerRecordRepository,
    AttemptRepository,
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
    MistakeRepository,
    QuestionReportRepository,
    QuestionRepository,
    StatsRepository,
    UserRepository,
)

__all__ = [
    "AnswerRecordRepository",
    "AttemptRepository",
    "BaseRepository",
    "KnowledgeOutlineRepository",
    "KnowledgeSourceRepository",
    "LevelRepository",
    "MistakeRepository",
    "QuestionReportRepository",
    "QuestionRepository",
    "StatsRepository",
    "UserRepository",
]
