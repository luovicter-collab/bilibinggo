from __future__ import annotations

import time
from typing import Any

from sqlmodel import col, select

from src.db.json_cols import dumps_json, loads_json
from src.db.models import ActivityRow, AutoParticipationFailureRow, DeletedActivityRow
from src.db.session import session_scope


def _prize_summary(item: dict[str, Any]) -> str:
    prizes = item.get("prizes") or []
    if not prizes or not isinstance(prizes[0], dict):
        return ""
    first = prizes[0]
    description = str(first.get("description") or "").strip()
    count = int(first.get("winner_count") or 0)
    if description and count:
        return f"{description} ×{count}"
    return description or (f"×{count}" if count else "")


def deleted_activity_ids() -> set[str]:
    with session_scope() as session:
        rows = session.exec(select(DeletedActivityRow.dynamic_id)).all()
        return {str(item) for item in rows if item}


def is_activity_deleted(dynamic_id: str) -> bool:
    did = str(dynamic_id or "").strip()
    if not did:
        return False
    with session_scope() as session:
        return session.get(DeletedActivityRow, did) is not None


def delete_activity(dynamic_id: str) -> dict[str, Any] | None:
    from src.db.activity_codec import row_to_activity_dict

    did = str(dynamic_id or "").strip()
    if not did:
        return None
    with session_scope() as session:
        existing_deleted = session.get(DeletedActivityRow, did)
        activity = session.get(ActivityRow, did)
        if activity is None:
            return deleted_row_to_dict(existing_deleted) if existing_deleted else None

        snapshot = row_to_activity_dict(activity)
        title = str(snapshot.get("activity_title") or snapshot.get("prize") or "").strip()
        title = title or _prize_summary(snapshot) or did
        deleted_at = int(time.time())
        row = existing_deleted or DeletedActivityRow(dynamic_id=did)
        row.activity_title = title
        row.source_url = str(snapshot.get("source_url") or "") or None
        row.lottery_type = str(snapshot.get("lottery_type") or "") or None
        row.prize = str(snapshot.get("prize") or "").strip() or _prize_summary(snapshot)
        row.deleted_at = deleted_at
        row.activity_snapshot_json = dumps_json(snapshot)
        if existing_deleted is None:
            session.add(row)
        session.delete(activity)
        return deleted_row_to_dict(row)


def restore_activity(dynamic_id: str) -> dict[str, Any] | None:
    from src.db.activity_codec import activity_dict_to_row

    did = str(dynamic_id or "").strip()
    if not did:
        return None
    with session_scope() as session:
        deleted = session.get(DeletedActivityRow, did)
        if deleted is None:
            return None
        snapshot = loads_json(deleted.activity_snapshot_json, default={})
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot["dynamic_id"] = did
        restored = activity_dict_to_row(snapshot, updated_at=int(time.time()))
        existing = session.get(ActivityRow, did)
        if existing is None:
            session.add(restored)
        else:
            for name in ActivityRow.model_fields:
                if name != "dynamic_id":
                    setattr(existing, name, getattr(restored, name))
        session.delete(deleted)
        return snapshot


def deleted_row_to_dict(row: DeletedActivityRow) -> dict[str, Any]:
    return {
        "dynamic_id": row.dynamic_id,
        "activity_title": row.activity_title or row.prize or row.dynamic_id,
        "source_url": row.source_url or "",
        "lottery_type": row.lottery_type or "",
        "prize": row.prize or "",
        "deleted_at": int(row.deleted_at or 0),
    }


def load_deleted_activities() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.exec(
            select(DeletedActivityRow).order_by(col(DeletedActivityRow.deleted_at).desc())
        ).all()
        return [deleted_row_to_dict(row) for row in rows]


def record_auto_participation_failure(dynamic_id: str, message: str) -> None:
    did = str(dynamic_id or "").strip()
    if not did:
        return
    with session_scope() as session:
        row = session.get(AutoParticipationFailureRow, did)
        if row is None:
            row = AutoParticipationFailureRow(dynamic_id=did)
            session.add(row)
        row.failed_at = int(time.time())
        row.message = str(message or "参与失败")[:500]


def clear_auto_participation_failure(dynamic_id: str) -> None:
    did = str(dynamic_id or "").strip()
    if not did:
        return
    with session_scope() as session:
        row = session.get(AutoParticipationFailureRow, did)
        if row is not None:
            session.delete(row)


def auto_failed_activity_ids() -> set[str]:
    with session_scope() as session:
        rows = session.exec(select(AutoParticipationFailureRow.dynamic_id)).all()
        return {str(item) for item in rows if item}
