from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlmodel import Session, SQLModel

from src.db.engine import get_engine
from src.db.models import SchemaMeta

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
    """新增用户删除名单与自动参与失败名单。create_all 后仍保持幂等。"""
    conn = session.connection()
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS deleted_activities (
                dynamic_id VARCHAR(32) NOT NULL PRIMARY KEY,
                activity_title VARCHAR NOT NULL DEFAULT '',
                source_url VARCHAR,
                lottery_type VARCHAR,
                prize VARCHAR NOT NULL DEFAULT '',
                deleted_at INTEGER NOT NULL DEFAULT 0,
                activity_snapshot_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_deleted_activities_deleted_at "
            "ON deleted_activities(deleted_at)"
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS auto_participation_failures (
                dynamic_id VARCHAR(32) NOT NULL PRIMARY KEY,
                failed_at INTEGER NOT NULL DEFAULT 0,
                message VARCHAR NOT NULL DEFAULT ''
            )
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_auto_participation_failures_failed_at "
            "ON auto_participation_failures(failed_at)"
        )
    )


_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
}


def _jobs_table_has_v2_columns(session: Session) -> bool:
    conn = session.connection()
    if conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'")
    ).fetchone() is None:
        return False
    existing = {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
    }
    return all(name in existing for name, _ in _JOB_V2_COLUMNS)


def _database_matches_code_schema(session: Session) -> bool:
    if SCHEMA_VERSION >= 2 and not _jobs_table_has_v2_columns(session):
        return False
    if SCHEMA_VERSION >= 3:
        conn = session.connection()
        required = {"deleted_activities", "auto_participation_failures"}
        existing = {
            str(row[0])
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if not required.issubset(existing):
            return False
    return True


def _try_reconcile_schema_meta_version(session: Session, recorded: int) -> int | None:
    """若 meta 版本被误标高于代码，但表结构已符合当前代码，则回写 meta（幂等）。"""
    if recorded <= SCHEMA_VERSION:
        return None
    if not _database_matches_code_schema(session):
        return None
    meta = session.get(SchemaMeta, 1)
    if meta is None:
        return None
    meta.version = SCHEMA_VERSION
    session.commit()
    return SCHEMA_VERSION


def _schema_newer_than_code_error(recorded: int) -> RuntimeError:
    from src.db.engine import db_path

    db = db_path()
    return RuntimeError(
        f"数据库 schema_version={recorded} 高于本程序支持的 {SCHEMA_VERSION}，无法安全启动。\n\n"
        f"数据库文件：{db}\n\n"
        "请先安装最新版 Release，并完全退出 Binggo（任务管理器结束所有 Binggo.exe）后重试。\n"
        "若仍失败：备份上述 data 文件夹后删除 binggo.db，再启动（会丢失本地活动库，Cookie 仍在 config）。"
    )


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
            reconciled = _try_reconcile_schema_meta_version(session, current)
            if reconciled is not None:
                current = reconciled
            else:
                raise _schema_newer_than_code_error(current)
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
