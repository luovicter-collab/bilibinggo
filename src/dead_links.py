from __future__ import annotations

from typing import Iterable

import httpx

from src.activity_store import active_activity_ids, remove_activity_ids
from src.source_outputs import SOURCE_OUTPUTS  # noqa: F401 — re-export for scripts/tests

_DELETED_DETAIL_MARKERS = (
    "不存在",
    "已删除",
    "已失效",
    "not found",
    "稿件不可见",
)


class DynamicDeletedError(RuntimeError):
    """动态已删除或不可访问（如 404）。"""

    def __init__(self, dynamic_id: str) -> None:
        self.dynamic_id = dynamic_id
        super().__init__(f"动态已删除或不可访问: {dynamic_id}")


def is_http_not_found(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 404
    message = str(exc)
    return "404" in message and "Not Found" in message


def is_dynamic_detail_permanently_gone(
    *,
    item: dict | None,
    code: int | None,
    message: str,
) -> bool:
    """dynamic/detail 明确表示动态不存在时返回 True；限流/网络失败返回 False。"""
    if item is not None:
        return False
    if code is None:
        return False
    if code == 0:
        return True
    if code in (-404, 404):
        return True
    lowered = (message or "").lower()
    if any(marker in lowered for marker in _DELETED_DETAIL_MARKERS):
        return True
    return False


def is_dynamic_deleted(client, dynamic_id: str) -> bool:
    """检测动态是否已删除。优先 dynamic/detail API，避免额外 HTML 请求。"""
    from src.lottery_api import probe_dynamic_detail_api

    try:
        item, code, message = probe_dynamic_detail_api(client, dynamic_id, retries=0)
    except Exception as exc:
        return is_http_not_found(exc)
    return is_dynamic_detail_permanently_gone(item=item, code=code, message=message)


def partition_alive_dynamic_ids(client, dynamic_ids: Iterable[str]) -> tuple[list[str], list[str]]:
    alive: list[str] = []
    dead: list[str] = []
    for raw_id in dynamic_ids:
        dynamic_id = str(raw_id or "").strip()
        if not dynamic_id:
            continue
        if is_dynamic_deleted(client, dynamic_id):
            dead.append(dynamic_id)
        else:
            alive.append(dynamic_id)
    return alive, dead


def purge_dynamic_ids(dynamic_ids: Iterable[str]) -> list[str]:
    """从本地活动库中移除已删除动态。"""
    removed: list[str] = []
    ids = {str(raw_id or "").strip() for raw_id in dynamic_ids if str(raw_id or "").strip()}
    if not ids:
        return removed
    if remove_activity_ids(ids) > 0:
        removed = sorted(ids)
    return removed


def collect_all_local_dynamic_ids() -> list[str]:
    """汇总本地活动库中的动态 ID。"""
    return sorted(active_activity_ids())
