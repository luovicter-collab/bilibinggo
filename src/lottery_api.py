from __future__ import annotations

import json
import re
import threading
import time

from src.bilibili_client import BilibiliClient
from src.lottery_classifier import UPOWER_BUSINESS_TYPE
from src.sources.common import opus_link

try:
    from src.app_logging import get_logger
except ImportError:  # pragma: no cover
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("api")

LOTTERY_NOTICE_URL = "https://api.vc.bilibili.com/lottery_svr/v1/lottery_svr/lottery_notice"
DYNAMIC_DETAIL_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"
OPUS_DETAIL_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail"
OPUS_DETAIL_FEATURES = "htmlNewStyle,ugcDelete,editable,opusPrivateVisible"

RESERVE_RESERVED_STATUS = 2

RESERVE_RID_RE = re.compile(r'"rid"\s*:\s*(\d+)')

_detail_api_lock = threading.Lock()
_detail_api_enabled = True


def is_detail_api_enabled() -> bool:
    return _detail_api_enabled


def disable_detail_api() -> None:
    global _detail_api_enabled
    with _detail_api_lock:
        _detail_api_enabled = False


def reset_detail_api_state() -> None:
    global _detail_api_enabled
    with _detail_api_lock:
        _detail_api_enabled = True


def fetch_lottery_notice(
    client: BilibiliClient,
    *,
    business_id: str,
    business_type: int,
    referer: str,
    retries: int = 3,
) -> dict | None:
    for attempt in range(max(1, retries)):
        data = client.request_json(
            LOTTERY_NOTICE_URL,
            {"business_id": business_id, "business_type": business_type},
            referer=referer,
            retries=1,
        )
        if data.get("code") == 0:
            notice = data.get("data") or {}
            return notice if notice.get("lottery_id") else None
        if data.get("code") == -9999 and attempt < retries - 1:
            time.sleep(1.2 * (attempt + 1))
            continue
        return None
    return None


def _extract_dynamic_additional(item: dict) -> dict:
    modules = item.get("modules") or {}
    if isinstance(modules, dict):
        return (modules.get("module_dynamic") or {}).get("additional") or {}
    if isinstance(modules, list):
        for mod in modules:
            if not isinstance(mod, dict):
                continue
            additional = (mod.get("module_dynamic") or {}).get("additional")
            if additional:
                return additional
    return {}


def extract_reserve_total_from_detail(item: dict) -> int | None:
    """从动态详情中提取预约人数（预约抽奖在 B 站页面展示的热度）。"""
    reserve = (_extract_dynamic_additional(item).get("reserve") or {})
    total = reserve.get("reserve_total")
    if total is None:
        return None
    try:
        return max(0, int(total))
    except (TypeError, ValueError):
        return None


def extract_activity_heat(item: dict, *, lottery_type: str) -> tuple[int, bool]:
    """返回 (热度值, 是否来自预约人数)。"""
    if lottery_type == "预约抽奖":
        reserve_total = extract_reserve_total_from_detail(item)
        if reserve_total is not None:
            return reserve_total, True
    return extract_repost_count_from_detail(item), False


def extract_repost_count_from_detail(item: dict) -> int:
    """从动态详情中提取转发数（热度）。"""
    modules = item.get("modules") or {}
    stat: dict
    if isinstance(modules, list):
        stat = {}
        for mod in modules:
            if isinstance(mod, dict) and mod.get("module_stat"):
                stat = mod.get("module_stat") or {}
                break
    else:
        stat = modules.get("module_stat") or {}
    forward = stat.get("forward") or {}
    count = forward.get("count")
    if count is None:
        return 0
    try:
        return max(0, int(count))
    except (TypeError, ValueError):
        return 0


def _normalize_dynamic_item(item: dict) -> dict:
    """将 opus/detail 的 modules 列表统一为 dynamic/detail 的字典结构。"""
    modules = item.get("modules")
    if not isinstance(modules, list):
        return item

    modules_dict: dict = {}
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        if mod.get("module_stat"):
            modules_dict["module_stat"] = mod["module_stat"]
        if mod.get("module_author"):
            modules_dict["module_author"] = mod["module_author"]
        if mod.get("module_dynamic"):
            modules_dict["module_dynamic"] = mod["module_dynamic"]

    normalized = dict(item)
    normalized["modules"] = modules_dict
    return normalized


def _fetch_opus_detail_item(client: BilibiliClient, dynamic_id: str) -> dict | None:
    # B 站风控有时会按 Referer 命中；同一动态从 opus 页和旧动态页进入
    # 的结果并不稳定。切换官方页面 Referer 可恢复正文接口，而不改变接口本身。
    referers = (
        opus_link(dynamic_id),
        f"https://t.bilibili.com/{dynamic_id}",
        "https://www.bilibili.com/",
    )
    for referer in referers:
        try:
            data = client.get_json(
                OPUS_DETAIL_URL,
                {
                    "id": dynamic_id,
                    "features": OPUS_DETAIL_FEATURES,
                },
                referer=referer,
                retries=2,
            )
        except Exception as exc:
            logger.debug("opus/detail 请求失败 %s referer=%s: %s", dynamic_id, referer, exc)
            continue
        if data.get("code") != 0:
            logger.debug(
                "opus/detail 返回错误 %s referer=%s: code=%s msg=%s",
                dynamic_id,
                referer,
                data.get("code"),
                data.get("message"),
            )
            continue
        item = (data.get("data") or {}).get("item") or {}
        if item:
            return item
    return None


def is_upower_dynamic(item: dict | None) -> bool:
    if not item:
        return False
    additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
    return bool(
        additional.get("upower_lottery")
        or additional.get("type") == "ADDITIONAL_TYPE_UPOWER_LOTTERY"
    )


def probe_dynamic_detail_api(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    retries: int = 2,
) -> tuple[dict | None, int | None, str]:
    """请求 web-dynamic/v1/detail，返回 (item, code, message)。网络/限流失败时 code 为 None。"""
    if not is_detail_api_enabled():
        return None, None, ""
    referers = (
        opus_link(dynamic_id),
        f"https://t.bilibili.com/{dynamic_id}",
        "https://www.bilibili.com/",
    )
    last_code: int | None = None
    last_message = ""
    last_error = ""
    for referer in referers:
        try:
            data = client.get_json(
                DYNAMIC_DETAIL_URL,
                {"id": dynamic_id},
                referer=referer,
                retries=retries,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.debug("dynamic/detail 请求失败 %s referer=%s: %s", dynamic_id, referer, exc)
            continue
        code = data.get("code")
        try:
            code_int = int(code) if code is not None else None
        except (TypeError, ValueError):
            code_int = None
        message = str(data.get("message") or "")
        last_code, last_message = code_int, message
        if code_int != 0:
            continue
        item = (data.get("data") or {}).get("item") or None
        if item:
            return item, 0, message
    if last_code is not None:
        return None, last_code, last_message
    return None, None, last_error


def _fetch_dynamic_api_item(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    retries: int = 2,
) -> dict | None:
    """仅请求 web-dynamic/v1/detail，不降级 opus（供正文抓取按序尝试）。"""
    item, code, message = probe_dynamic_detail_api(client, dynamic_id, retries=retries)
    if code != 0:
        if code is not None:
            logger.debug(
                "dynamic/detail 返回错误 %s: code=%s msg=%s",
                dynamic_id,
                code,
                message,
            )
        return None
    return item or None


def fetch_opus_detail_item(client: BilibiliClient, dynamic_id: str) -> dict | None:
    """获取 opus/detail 并归一化 modules，供收藏入口等二次探测。"""
    item = _fetch_opus_detail_item(client, dynamic_id)
    if not item:
        return None
    return _normalize_dynamic_item(item)


def fetch_dynamic_detail(client: BilibiliClient, dynamic_id: str) -> dict | None:
    if not is_detail_api_enabled():
        return None
    referer = opus_link(dynamic_id)
    item: dict | None = _fetch_dynamic_api_item(client, dynamic_id)
    if not item:
        item = _fetch_opus_detail_item(client, dynamic_id)
        if item:
            logger.info("dynamic/detail 不可用，已回退 opus/detail: %s", dynamic_id)

    if not item:
        return None
    return _normalize_dynamic_item(item)


def resolve_reserve_business(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    detail_item: dict | None = None,
) -> tuple[str, int] | None:
    """预约抽奖：解析 reserve.rid 与 business_type=10。"""
    item = detail_item
    if item is None:
        item = fetch_dynamic_detail(client, dynamic_id)
    if item:
        additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
        reserve = additional.get("reserve") or {}
        rid = reserve.get("rid")
        if rid:
            return str(rid), 10

    referer = opus_link(dynamic_id)
    try:
        html = client.get_text(referer, referer="https://www.bilibili.com", retries=1)
    except RuntimeError:
        return None
    match = RESERVE_RID_RE.search(html)
    if match:
        return match.group(1), 10
    return None


def fetch_reserve_button_status(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    detail_item: dict | None = None,
) -> bool | None:
    """返回是否已预约。button.status=2 表示已预约。"""
    item = detail_item
    if item is None:
        item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        return None
    additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
    reserve = additional.get("reserve") or {}
    button = reserve.get("button") or {}
    status = button.get("status")
    if status is None:
        return None
    return int(status) == RESERVE_RESERVED_STATUS


def fetch_notice_for_interact(client: BilibiliClient, dynamic_id: str) -> tuple[dict, int, str] | None:
    referer = opus_link(dynamic_id)
    notice = fetch_lottery_notice(
        client,
        business_id=dynamic_id,
        business_type=1,
        referer=referer,
    )
    if notice:
        return notice, 1, dynamic_id
    return None


def fetch_notice_for_upower(client: BilibiliClient, dynamic_id: str) -> tuple[dict, int, str] | None:
    referer = opus_link(dynamic_id)
    notice = fetch_lottery_notice(
        client,
        business_id=dynamic_id,
        business_type=UPOWER_BUSINESS_TYPE,
        referer=referer,
    )
    if notice:
        return notice, UPOWER_BUSINESS_TYPE, dynamic_id
    return None


def fetch_notice_for_reserve(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    detail_item: dict | None = None,
) -> tuple[dict, int, str] | None:
    resolved = resolve_reserve_business(client, dynamic_id, detail_item=detail_item)
    if not resolved:
        return None
    business_id, business_type = resolved
    notice = fetch_lottery_notice(
        client,
        business_id=business_id,
        business_type=business_type,
        referer=opus_link(dynamic_id),
    )
    if not notice:
        return None
    return notice, business_type, business_id
