from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """最基础的一套 CRUD：查询、新增、删除、计数、分页列表。"""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, obj_id: int) -> ModelT | None:
        return self.session.get(self.model, obj_id)

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        self.session.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)
        self.session.flush()

    def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        return int(self.session.execute(stmt).scalar_one())

    def list(
        self,
        *,
        order_by: Any | None = None,
        limit: int | None = None,
        offset: int | None = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = select(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.session.execute(stmt).scalars().all()
