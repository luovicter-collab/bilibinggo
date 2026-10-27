from __future__ import annotations

from typing import Any

from src.activity_status import resolve_activity_status
from src.activity_exclusions import (
    auto_failed_activity_ids,
    is_activity_deleted,
    load_deleted_activities,
)
from src.activity_store import load_payload
from src.db.snapshots import load_ds_check_dict, load_watch_sync_dict
from src.draw_reminder import matches_draw_window_filter
from src.lottery_classifier import PARTICIPATABLE_TYPES, is_charging_lottery_activity
from src.lottery_time import format_timestamp, is_activity_past_end, lottery_time_text
from src.participation_log import load_action_entries_for_uid
from src.participation_store import ParticipationRecord, load_participations
from src.sources.common import is_valid_dynamic_id
from src.state_store import DATA_DIR, get_last_pipeline_persisted

from src.watch_sync import OUTPUT_PATH as WATCH_OUTPUT_PATH

DS_OUTPUTS = {
    "DS-1": DATA_DIR / "output" / "ds1_latest.json",
    "DS-2": DATA_DIR / "output" / "ds2_latest.json",
    "DS-3": DATA_DIR / "output" / "ds3_latest.json",
    "DS-4": DATA_DIR / "output" / "ds4_latest.json",
    "DS-5": DATA_DIR / "output" / "ds5_latest.json",
    "DS-6": DATA_DIR / "output" / "ds6_latest.json",
    "DS-7": DATA_DIR / "output" / "ds7_latest.json",
    "WATCH": WATCH_OUTPUT_PATH,
}
SOURCE_LABELS = {
    "DS-1": "哔哩抽奖小助理",
    "DS-2": "番茄薯条喵",
    "DS-3": "你的抽奖工具人",
    "DS-4": "J君名",
    "DS-5": "互动抽奖娘",
    "DS-6": "糯米是个背包",
    "DS-7": "大锦鲤",
    "WATCH": "监控用户",
}
SOURCE_SPACE_URLS = {
    "DS-1": "https://space.bilibili.com/885439/upload/video",
    "DS-2": "https://space.bilibili.com/3546836235193146/upload/opus",
    "DS-3": "https://space.bilibili.com/100680137/upload/opus",
    "DS-4": "https://space.bilibili.com/126038161/upload/opus",
    "DS-5": "https://space.bilibili.com/3546776042736296/upload/opus",
    "DS-6": "https://space.bilibili.com/492426375/upload/opus",
    "DS-7": "https://space.bilibili.com/226257459/upload/opus",
    "WATCH": "",
}


def _load_source_snapshot(source_id: str) -> dict:
    if source_id == "WATCH":
        return load_watch_sync_dict() or {}
    return load_ds_check_dict(source_id) or {}


def _activity_title(item: dict) -> str:
    return _prize_summary(item) or str(item.get("dynamic_id") or "未知活动")


def _load_participation_actions() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for entry in load_action_entries_for_uid():
        if not isinstance(entry, dict):
            continue
        dynamic_id = str(entry.get("dynamic_id") or "")
        if dynamic_id:
            latest[dynamic_id] = entry
    return latest


def _prize_summary(item: dict) -> str:
    prizes = item.get("prizes") or []
    if not prizes:
        return ""
    first = prizes[0] if isinstance(prizes[0], dict) else {}
    description = str(first.get("description") or "").strip()
    count = int(first.get("winner_count") or 0)
    if description and count:
        return f"{description} ×{count}"
    return description or (f"×{count}" if count else "")


def _resolve_activity_status(item: dict, participation: ParticipationRecord | None) -> str:
    if is_charging_lottery_activity(item):
        return str(item.get("activity_status") or "未参加")
    if is_activity_past_end(item, participation):
        return "已结束"
    if item.get("status_classified") and item.get("activity_status"):
        return str(item.get("activity_status"))
    lottery_type = item.get("lottery_type")
    if lottery_type not in PARTICIPATABLE_TYPES:
        return str(item.get("activity_status") or "未参加")
    status, _ = resolve_activity_status(
        draw_status=item.get("draw_status") or "active",
        lottery_type=lottery_type,
        platform_participated=item.get("platform_participated"),
        reserve_reserved=item.get("reserve_reserved"),
        conditions=item.get("conditions") or {},
        participation=participation,
    )
    return status


def _can_participate(item: dict, activity_status: str) -> bool:
    return (
        not item.get("skipped")
        and str(item.get("draw_status") or "") == "active"
        and activity_status != "已参加"
        and activity_status != "已结束"
    )


def _should_list_activity(item: dict, activity_status: str, can_participate: bool) -> bool:
    if is_charging_lottery_activity(item):
        return False
    if activity_status == "已参加":
        return True
    if activity_status == "已结束":
        return True
    if activity_status == "未参加" and can_participate:
        return True
    return False


def invalidate_activity_cache() -> None:
    """兼容旧调用点；活动数据已走 DB，无需文件 mtime 缓存。"""
    return None


def _sort_key(item: dict, *, sort: str, order: str) -> tuple:
    if sort == "heat":
        repost = int(item.get("repost_count") or 0)
        heat_key = -repost if order == "desc" else repost
        return (heat_key, str(item.get("dynamic_id") or ""))
    status_rank = {"未参加": 0, "已参加": 1, "已结束": 2}
    draw_rank = {"active": 0, "ended": 1}
    activity_status = str(item.get("activity_status") or "")
    draw_status = str(item.get("draw_status") or "")
    return (
        status_rank.get(activity_status, 9),
        draw_rank.get(draw_status, 9),
        str(item.get("dynamic_id") or ""),
    )


def _normalize_activity(
    item: dict,
    action_map: dict[str, dict],
    participation: ParticipationRecord | None,
) -> dict[str, Any]:
    dynamic_id = str(item.get("dynamic_id") or "")
    last_action = action_map.get(dynamic_id)
    activity_status = _resolve_activity_status(item, participation)
    can_participate = _can_participate(item, activity_status)
    repost_count = int(item.get("repost_count") or 0)
    repost_fetched = bool(item.get("repost_fetched"))
    heat_missing = not repost_fetched or (
        repost_count == 0 and not item.get("repost_zero_confirmed")
    )
    return {
        "dynamic_id": dynamic_id,
        "source_url": str(item.get("source_url") or ""),
        "activity_title": _activity_title(item),
        "lottery_type": str(item.get("lottery_type") or ""),
        "activity_status": activity_status,
        "draw_tag": str(item.get("draw_tag") or ""),
        "draw_status": str(item.get("draw_status") or ""),
        "prize": _prize_summary(item),
        "repost_count": repost_count,
        "repost_fetched": repost_fetched,
        "heat_missing": heat_missing,
        "lottery_time": lottery_time_text(item) or "—",
        "check_at_recommended": False,
        "skipped": bool(item.get("skipped")),
        "skip_reason": str(item.get("skip_reason") or ""),
        "can_participate": can_participate,
        "last_participation": {
            "status": last_action.get("status") if last_action else None,
            "message": last_action.get("message") if last_action else None,
            "recorded_at": last_action.get("recorded_at") if last_action else None,
            "actions": last_action.get("actions") if last_action else None,
        }
        if last_action
        else None,
    }


def _participatable_stored(item: dict) -> bool:
    return (
        isinstance(item, dict)
        and not item.get("skipped")
        and not is_charging_lottery_activity(item)
    )


def _load_activities_payload() -> dict:
    return load_payload()


def get_summary() -> dict[str, Any]:
    enriched = _load_activities_payload()
    participations = load_participations()
    activities = [
        item for item in (enriched.get("activities") or []) if _participatable_stored(item)
    ]
    status_counts = {"已结束": 0, "已参加": 0, "未参加": 0}
    draw_counts = {"active": 0, "ended": 0}
    for item in activities:
        dynamic_id = str(item.get("dynamic_id") or "")
        status = _resolve_activity_status(item, participations.get(dynamic_id))
        if status in status_counts:
            status_counts[status] += 1
        if str(item.get("draw_status") or "") == "ended":
            draw_counts["ended"] += 1
        else:
            draw_counts["active"] += 1

    sources: list[dict[str, Any]] = []
    for source_id, _path in DS_OUTPUTS.items():
        if source_id == "WATCH":
            continue
        data = _load_source_snapshot(source_id)
        checked_at = data.get("checked_at") or data.get("synced_at")
        title = str(data.get("title") or "")
        sources.append(
            {
                "id": source_id,
                "name": SOURCE_LABELS.get(source_id, source_id),
                "updated": bool(data.get("updated")) if data else False,
                "link_count": len(data.get("activity_links") or []),
                "title": title,
                "checked_at": checked_at,
                "checked_at_text": format_timestamp(int(checked_at)) if checked_at else "尚未更新",
                "space_url": SOURCE_SPACE_URLS.get(source_id, ""),
                "container_url": str(data.get("container_url") or ""),
            }
        )
    last_pipeline = get_last_pipeline_persisted()
    deleted_count = len(load_deleted_activities())
    return {
        "enriched_at": enriched.get("updated_at") or enriched.get("enriched_at"),
        "total_count": len(activities),
        "new_count": last_pipeline["persisted_count"],
        "last_pipeline_sync": last_pipeline,
        "user_status_counts": status_counts,
        "counts": draw_counts,
        "deleted_count": deleted_count,
        "sources": sources,
    }


PARTICIPATE_TRIPLE_LIMIT = 3
ACTIVITY_PAGE_SIZE = 20


def participate_step_budget(lottery_type: str, *, dynamic_id: str | None = None) -> int:
    """单次参与在进度条上占用的步数（预约抽奖为关注 + 预约共 2 步）。"""
    normalized = (lottery_type or "").strip()
    if normalized == "预约抽奖":
        return 2
    if normalized in ("互动抽奖", "转发抽奖"):
        return 5
    if dynamic_id:
        try:
            resolved = lookup_lottery_type(dynamic_id)
            return 2 if resolved == "预约抽奖" else 5
        except RuntimeError:
            pass
    return 5


def build_triple_progress_plan(
    targets: list[dict[str, Any]],
) -> tuple[int, dict[str, tuple[int, int]]]:
    """返回总步数与各活动的 (offset, budget) 映射。"""
    plan: dict[str, tuple[int, int]] = {}
    offset = 0
    for target in targets:
        dynamic_id = str(target.get("dynamic_id") or "").strip()
        if not dynamic_id:
            continue
        budget = participate_step_budget(str(target.get("lottery_type") or ""), dynamic_id=dynamic_id)
        plan[dynamic_id] = (offset, budget)
        offset += budget
    return offset, plan


def _filtered_activity_rows(
    *,
    status: str | None = None,
    lottery_type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    enriched = _load_activities_payload()
    action_map = _load_participation_actions()
    participations = load_participations()
    items = [item for item in (enriched.get("activities") or []) if isinstance(item, dict)]

    normalized: list[dict[str, Any]] = []
    draw_window_value = (draw_window or "").strip().lower()
    if draw_window_value not in {"", "soon"}:
        draw_window_value = ""
    for item in items:
        dynamic_id = str(item.get("dynamic_id") or "")
        participation = participations.get(dynamic_id)
        if draw_window_value and not matches_draw_window_filter(
            item, participation, draw_window_value
        ):
            continue
        activity_status = _resolve_activity_status(item, participation)
        can_participate = _can_participate(item, activity_status)
        if not _should_list_activity(item, activity_status, can_participate):
            continue
        row = _normalize_activity(item, action_map, participation)
        normalized.append(row)

    if draw_window_value:
        status = None
    if status:
        normalized = [item for item in normalized if item.get("activity_status") == status]
    if lottery_type:
        normalized = [item for item in normalized if item.get("lottery_type") == lottery_type]
    if draw and not status:
        normalized = [item for item in normalized if item.get("draw_status") == draw]
    if q:
        keyword = q.strip().lower()
        if keyword:

            def _matches(item: dict) -> bool:
                fields = [
                    str(item.get("dynamic_id") or ""),
                    str(item.get("activity_title") or ""),
                    str(item.get("prize") or ""),
                    str(item.get("skip_reason") or ""),
                    str(item.get("lottery_time") or ""),
                ]
                return any(keyword in field.lower() for field in fields if field)

            normalized = [item for item in normalized if _matches(item)]

    sort_mode = (sort or "default").strip().lower()
    sort_order = (order or "desc").strip().lower()
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    if sort_mode not in ("heat", "default"):
        sort_mode = "default"
    normalized.sort(key=lambda item: _sort_key(item, sort=sort_mode, order=sort_order))
    return normalized


def _pick_triple_from_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int = PARTICIPATE_TRIPLE_LIMIT,
    exclude_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    excluded = exclude_ids or set()
    for row in rows:
        if str(row.get("activity_status") or "") != "未参加":
            continue
        if not row.get("can_participate"):
            continue
        dynamic_id = str(row.get("dynamic_id") or "").strip()
        if not is_valid_dynamic_id(dynamic_id) or dynamic_id in seen_ids or dynamic_id in excluded:
            continue
        row_lottery_type = str(row.get("lottery_type") or "")
        if row_lottery_type not in PARTICIPATABLE_TYPES:
            continue
        seen_ids.add(dynamic_id)
        targets.append(row)
        if len(targets) >= limit:
            break
    return targets


def _format_triple_target_items(targets: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "dynamic_id": str(item.get("dynamic_id") or ""),
            "activity_title": str(item.get("activity_title") or item.get("prize") or "未知活动"),
            "lottery_type": str(item.get("lottery_type") or ""),
            "activity_status": str(item.get("activity_status") or ""),
        }
        for item in targets
    ]


def build_triple_target_preview(targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(targets),
        "limit": PARTICIPATE_TRIPLE_LIMIT,
        "items": _format_triple_target_items(targets),
    }


def pick_triple_participate_targets(
    *,
    status: str | None = None,
    lottery_type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    limit: int = PARTICIPATE_TRIPLE_LIMIT,
    exclude_auto_failures: bool = False,
) -> list[dict[str, Any]]:
    """按当前列表筛选与排序，取最前面可参与的未参加活动（默认最多 3 个）。"""
    rows = _filtered_activity_rows(
        status=status,
        lottery_type=lottery_type,
        draw=draw,
        draw_window=draw_window,
        q=q,
        sort=sort,
        order=order,
    )
    excluded = auto_failed_activity_ids() if exclude_auto_failures else set()
    return _pick_triple_from_rows(rows, limit=limit, exclude_ids=excluded)


def summarize_triple_participate_targets(
    *,
    status: str | None = None,
    lottery_type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> dict[str, Any]:
    """预览三连参与将命中的活动（供前端展示按钮状态）。"""
    targets = pick_triple_participate_targets(
        status=status,
        lottery_type=lottery_type,
        draw=draw,
        draw_window=draw_window,
        q=q,
        sort=sort,
        order=order,
    )
    return build_triple_target_preview(targets)


def list_activities(
    *,
    status: str | None = None,
    lottery_type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = ACTIVITY_PAGE_SIZE,
) -> dict[str, Any]:
    normalized = _filtered_activity_rows(
        status=status,
        lottery_type=lottery_type,
        draw=draw,
        draw_window=draw_window,
        q=q,
        sort=sort,
        order=order,
    )
    total = len(normalized)
    page = max(1, page)
    page_size = ACTIVITY_PAGE_SIZE
    start = (page - 1) * page_size
    page_items = normalized[start : start + page_size]
    triple_targets = build_triple_target_preview(_pick_triple_from_rows(normalized))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": page_items,
        "triple_targets": triple_targets,
    }


def lookup_lottery_type(dynamic_id: str) -> str:
    if is_activity_deleted(dynamic_id):
        raise RuntimeError(f"活动 {dynamic_id} 已删除，不会参与")
    enriched = _load_activities_payload()
    for item in enriched.get("activities") or []:
        if str(item.get("dynamic_id") or "") == dynamic_id:
            lottery_type = str(item.get("lottery_type") or "")
            if lottery_type in PARTICIPATABLE_TYPES:
                return lottery_type
    raise RuntimeError(f"未找到活动 {dynamic_id} 的类型信息")


def list_deleted_activity_rows() -> dict[str, Any]:
    items = load_deleted_activities()
    for item in items:
        deleted_at = int(item.get("deleted_at") or 0)
        item["deleted_at_text"] = format_timestamp(deleted_at) if deleted_at else "—"
    return {"total": len(items), "items": items}


def resolve_participate_lottery_type(dynamic_id: str, *, hint: str | None = None) -> str:
    """参与时以 enriched 缓存中的类型为准，列表类型仅作兜底。"""
    hinted = str(hint or "").strip()
    try:
        return lookup_lottery_type(dynamic_id)
    except RuntimeError:
        if hinted in PARTICIPATABLE_TYPES:
            return hinted
        raise
