from __future__ import annotations

from typing import Optional

from sqlalchemy import Column, Index, Text
from sqlmodel import Field, SQLModel


class SchemaMeta(SQLModel, table=True):
    __tablename__ = "schema_meta"

    id: int = Field(default=1, primary_key=True)
    version: int = Field(default=1)


class ActivityRow(SQLModel, table=True):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_lottery_type", "lottery_type"),
        Index("ix_activities_activity_status", "activity_status"),
        Index("ix_activities_lottery_time", "lottery_time"),
        Index("ix_activities_draw_tag", "draw_tag"),
    )

    dynamic_id: str = Field(primary_key=True, max_length=32)
    source_url: Optional[str] = None
    lottery_type: Optional[str] = Field(default=None, index=False)
    business_id: Optional[str] = None
    business_type: Optional[str] = None
    draw_status: Optional[str] = None
    lottery_time: Optional[int] = Field(default=None)
    activity_status: Optional[str] = None
    draw_tag: Optional[str] = None
    status_classified: bool = False
    skipped: bool = False
    platform_participated: Optional[bool] = None
    reserve_reserved: Optional[bool] = None
    repost_count: Optional[int] = None
    enriched_at: Optional[int] = None
    status_code: Optional[int] = None
    skip_reason: Optional[str] = None
    lottery_detail_url: Optional[str] = None
    user_status_source: Optional[str] = None
    payload_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    updated_at: int = 0


class DeletedActivityRow(SQLModel, table=True):
    __tablename__ = "deleted_activities"
    __table_args__ = (Index("ix_deleted_activities_deleted_at", "deleted_at"),)

    dynamic_id: str = Field(primary_key=True, max_length=32)
    activity_title: str = ""
    source_url: Optional[str] = None
    lottery_type: Optional[str] = None
    prize: str = ""
    deleted_at: int = 0
    activity_snapshot_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class AutoParticipationFailureRow(SQLModel, table=True):
    __tablename__ = "auto_participation_failures"
    __table_args__ = (Index("ix_auto_participation_failures_failed_at", "failed_at"),)

    dynamic_id: str = Field(primary_key=True, max_length=32)
    failed_at: int = 0
    message: str = ""


class ParticipationRow(SQLModel, table=True):
    __tablename__ = "participations"
    __table_args__ = (Index("ix_participations_uid_status", "uid", "user_status"),)

    uid: str = Field(primary_key=True, max_length=64)
    dynamic_id: str = Field(primary_key=True, max_length=32)
    user_status: str = Field(max_length=16)
    updated_at: int = 0
    source: Optional[str] = None


class ParticipationActionRow(SQLModel, table=True):
    __tablename__ = "participation_actions"
    __table_args__ = (Index("ix_participation_actions_uid_recorded", "uid", "recorded_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(index=True, max_length=64)
    recorded_at: int = 0
    dynamic_id: str = Field(default="", index=True, max_length=32)
    lottery_type: str = ""
    status: str = ""
    message: str = ""
    action_text: str = ""
    actions_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    context_snapshot_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class SourceCheckpointRow(SQLModel, table=True):
    __tablename__ = "source_checkpoints"

    source_id: str = Field(primary_key=True, max_length=32)
    container_url: Optional[str] = None
    container_id: Optional[str] = None
    title: Optional[str] = None
    cv_id: Optional[str] = None
    checked_at: Optional[int] = None


class WatchMetaRow(SQLModel, table=True):
    __tablename__ = "watch_meta"

    id: int = Field(default=1, primary_key=True)
    last_synced_at: Optional[int] = None


class PipelineMetaRow(SQLModel, table=True):
    __tablename__ = "pipeline_meta"

    id: int = Field(default=1, primary_key=True)
    last_action: Optional[str] = None
    last_persisted_count: int = 0
    last_synced_at: Optional[int] = None


class WatchUserRow(SQLModel, table=True):
    __tablename__ = "watch_users"

    mid: int = Field(primary_key=True)
    name: str = ""
    updated_at: int = 0


class WatchUsersMetaRow(SQLModel, table=True):
    __tablename__ = "watch_users_meta"

    id: int = Field(default=1, primary_key=True)
    updated_at: int = 0
    seeded_from: Optional[str] = None


class UserSettingsRow(SQLModel, table=True):
    __tablename__ = "user_settings"

    uid: str = Field(primary_key=True, max_length=64)
    participate_text: Optional[str] = None
    participate_fallback_text: Optional[str] = None
    participate_text_mode: Optional[str] = None
    updated_at: int = 0


class DsCheckSnapshotRow(SQLModel, table=True):
    __tablename__ = "ds_check_snapshots"

    source_id: str = Field(primary_key=True, max_length=32)
    updated: bool = False
    container_url: Optional[str] = None
    container_id: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[int] = None
    previous_container_url: Optional[str] = None
    checked_at: Optional[int] = None
    cv_id: Optional[str] = None
    activity_links_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    link_hints_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class WatchSyncSnapshotRow(SQLModel, table=True):
    __tablename__ = "watch_sync_snapshots"

    id: int = Field(default=1, primary_key=True)
    source_id: str = "WATCH"
    synced_at: int = 0
    window_start: Optional[int] = None
    window_end: Optional[int] = None
    checked_at: Optional[int] = None
    activity_links_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    link_count: int = 0
    users_total: int = 0
    users_ok: int = 0
    users_failed: int = 0
    user_results_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class ForwardParseCacheRow(SQLModel, table=True):
    __tablename__ = "forward_parse_cache"

    dynamic_id: str = Field(primary_key=True, max_length=32)
    content_hash: str = ""
    parsed_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    updated_at: int = 0


class ForwardClassifyCacheRow(SQLModel, table=True):
    __tablename__ = "forward_classify_cache"

    dynamic_id: str = Field(primary_key=True, max_length=32)
    content_hash: str = ""
    parsed_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    updated_at: int = 0


class AccountProfileCacheRow(SQLModel, table=True):
    __tablename__ = "account_profile_cache"

    id: int = Field(default=1, primary_key=True)
    uname: Optional[str] = None
    face: Optional[str] = None
    mid: Optional[int] = None
    following: Optional[int] = None
    dynamic_count: Optional[int] = None
    updated_at: int = 0
    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class MessageWatchRow(SQLModel, table=True):
    __tablename__ = "message_watch"

    uid: int = Field(primary_key=True)
    last_seen_unread_at: Optional[int] = None
    updated_at: int = 0


class DrawReminderSnapshotRow(SQLModel, table=True):
    __tablename__ = "draw_reminder_snapshots"

    uid: int = Field(primary_key=True)
    drawing_soon_count: int = 0
    drawing_soon_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    at_notify_url: Optional[str] = None
    updated_at: int = 0


class JobRow(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_state", "state"),
        Index("ix_jobs_finished_at", "finished_at"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = ""
    label: str = ""
    state: str = ""
    source: str = "ui"
    params_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    progress_step: int = 0
    progress_total: int = 0
    message: str = ""
    log_summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    result_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_kind: Optional[str] = None
    created_at: Optional[int] = None
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
