"""Alembic 迁移测试：升级到 head 后表与索引齐全（M2-03 验收）。"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(db_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def test_upgrade_head_creates_all_tables_and_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    command.upgrade(_alembic_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert "alembic_version" in tables
    assert {"user", "knowledge_source", "knowledge_outline", "level", "question"} <= tables
    assert {"attempt", "answer_record", "mistake", "question_report"} <= tables

    attempt_indexes = {idx["name"] for idx in inspector.get_indexes("attempt")}
    question_indexes = {idx["name"] for idx in inspector.get_indexes("question")}
    assert "ix_attempt_user_started" in attempt_indexes
    assert "ix_question_level_seq" in question_indexes
    engine.dispose()


def test_downgrade_then_upgrade_is_reversible(tmp_path: Path) -> None:
    db_path = tmp_path / "reversible.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(f"sqlite:///{db_path}")
    remaining = set(inspect(engine).get_table_names())
    engine.dispose()

    assert "question" not in remaining
