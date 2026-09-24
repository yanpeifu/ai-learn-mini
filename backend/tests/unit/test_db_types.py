"""UTCDateTime 类型测试：跨 SQLite / PostgreSQL 统一返回「带时区的 UTC 时间」。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.orm import Session

from app.db.types import UTCDateTime


def _table() -> Table:
    metadata = MetaData()
    return Table(
        "t_utc",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("created_at", UTCDateTime()),
    )


def test_naive_datetime_is_stored_and_returned_as_utc(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'utc.db'}")
    table = _table()
    table.metadata.create_all(engine)
    naive = datetime(2026, 9, 17, 10, 30, 0)

    with Session(engine) as session:
        session.execute(table.insert().values(created_at=naive))
        session.commit()
        stored = session.execute(select(table.c.created_at)).scalar_one()

    assert stored.tzinfo is not None
    assert stored.utcoffset() == timedelta(0)
    assert stored.replace(tzinfo=None) == naive


def test_aware_datetime_is_converted_to_utc(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'utc2.db'}")
    table = _table()
    table.metadata.create_all(engine)
    shanghai = timezone(timedelta(hours=8))
    aware = datetime(2026, 9, 17, 18, 30, 0, tzinfo=shanghai)

    with Session(engine) as session:
        session.execute(table.insert().values(created_at=aware))
        session.commit()
        stored = session.execute(select(table.c.created_at)).scalar_one()

    assert stored == aware
    assert stored.hour == 10
