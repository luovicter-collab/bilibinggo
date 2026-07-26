from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlmodel import Session, SQLModel

from src.db.engine import get_engine
from src.db.models import ActivityDismissalRow, SchemaMeta

# 确保全部表注册到 metadata
from src.db import models as _models  # noqa: F401

SCHEMA_VERSION = 3

_JOB_V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("label", "TEXT NOT NULL DEFAULT ''"),
    ("source", "TEXT NOT NULL DEFAULT 'ui'"),
    ("params_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("result_json", "TEXT"),
    ("error_kind", "TEXT"),
)


def migrate_v1_to_v2(session: Session) -> None:
    """为已有 jobs 表补齐 v2 列与索引；列已存在则跳过（幂等）。"""
    conn = session.connection()
    table_exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'")
    ).fetchone()
    if table_exists is None:
        # create_all 应已建表；若仍无表则交由下轮 create_all/启动失败暴露
        return
    existing = {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
    }
    for name, decl in _JOB_V2_COLUMNS:
        if name not in existing:
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {decl}"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs(state)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_finished_at ON jobs(finished_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON jobs(created_at)"))


def migrate_v2_to_v3(session: Session) -> None:
    """新增活动手动移除墓碑表；checkfirst 保证迁移可重复执行。"""
    ActivityDismissalRow.__table__.create(bind=session.connection(), checkfirst=True)


_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
}


def init_db() -> None:
    """创建表结构并执行 schema_version 迁移。可重复调用。"""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        row = session.get(SchemaMeta, 1)
        if row is None:
            session.add(SchemaMeta(id=1, version=SCHEMA_VERSION))
            session.commit()
            return
        current = int(row.version)
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"数据库 schema_version={current} 高于代码支持的 {SCHEMA_VERSION}，请升级程序"
            )
        while current < SCHEMA_VERSION:
            migrate = _MIGRATIONS.get(current)
            if migrate is None:
                raise RuntimeError(f"缺少 schema 迁移：{current} -> {current + 1}")
            migrate(session)
            current += 1
            meta = session.get(SchemaMeta, 1)
            if meta is None:
                session.add(SchemaMeta(id=1, version=current))
            else:
                meta.version = current
            session.commit()
