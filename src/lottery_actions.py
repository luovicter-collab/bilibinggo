from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal

import httpx

from src.bilibili_auth import get_login_uid, require_login
from src.bilibili_client import BilibiliClient, api_code
from src.lottery_api import fetch_dynamic_detail, fetch_notice_for_interact, fetch_opus_detail_item
from src.sources.common import opus_link

ActionName = Literal["like", "follow", "favorite", "repost", "comment", "reserve"]

DEFAULT_PARTICIPATE_TEXT = "好运连连！"

LIKE_URL = "https://api.bilibili.com/x/dynamic/feed/dyn/thumb"
FOLLOW_URL = "https://api.bilibili.com/x/relation/modify"
RELATION_URL = "https://api.bilibili.com/x/relation"
FAV_LIST_URL = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
FAV_RESOURCE_LIST_URL = "https://api.bilibili.com/x/v3/fav/resource/list"
FAV_DEAL_URL = "https://api.bilibili.com/x/v3/fav/resource/deal"
COSMO_SIMPLE_ACTION_URL = "https://api.bilibili.com/x/community/cosmo/interface/simple_action"
REPOST_URL = "https://api.bilibili.com/x/dynamic/feed/create/dyn"
COMMENT_URL = "https://api.bilibili.com/x/v2/reply/add"
REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"

FAV_CONTENT_TYPE = 24
FOLLOWING_ATTRIBUTES = {2, 6}
SPACE_FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
SPACE_FEED_PAGE_SIZE = 20
SPACE_FEED_MAX_PAGES = 3
ACTION_INTERVAL_SEC = 1.5
ACTION_LABELS: dict[ActionName, str] = {
    "like": "点赞",
    "follow": "关注",
    "favorite": "收藏",
    "repost": "转发",
    "comment": "评论",
    "reserve": "预约",
}
PARTICIPATION_STEPS: tuple[ActionName, ...] = ("like", "follow", "favorite", "repost", "comment")


@dataclass
class ActionResult:
    action: ActionName
    ok: bool
    detail: str = ""


@dataclass
class DynamicContext:
    dynamic_id: str
    sender_uid: int
    referer: str
    comment_rid: str
    comment_type: int
    liked: bool
    favorited: bool
    favorite_available: bool
    followed: bool
    reposted: bool
    commented: bool


def _api_code(payload: dict) -> int:
    code = payload.get("code")
    if code is None:
        return -1
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def _api_message(payload: dict) -> str:
    return str(payload.get("message") or payload.get("msg") or "").strip()


def _default_fav_folder_id(client: BilibiliClient, *, uid: int, referer: str) -> str:
    payload = client.get_json(FAV_LIST_URL, params={"up_mid": uid}, referer=referer)
    folders = (payload.get("data") or {}).get("list") or []
    if not folders:
        raise RuntimeError("未找到可用收藏夹")
    folder = folders[0]
    folder_id = folder.get("id") or folder.get("fid")
    if not folder_id:
        raise RuntimeError("收藏夹 ID 解析失败")
    return str(folder_id)


def resolve_sender_uid(item: dict) -> int:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    for key in ("mid", "uid", "up_mid"):
        value = author.get(key)
        if value:
            return int(value)
    raise RuntimeError("无法从动态详情解析 UP 主 UID")


def _extract_module_stat(item: dict) -> dict:
    modules = item.get("modules") or {}
    if isinstance(modules, dict):
        stat = modules.get("module_stat") or {}
        return stat if isinstance(stat, dict) else {}
    if isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("module_type") != "MODULE_TYPE_STAT" and not module.get("module_stat"):
                continue
            stat = module.get("module_stat") or {}
            if isinstance(stat, dict):
                return stat
    return {}


def _module_stat_confirms_no_favorite(stat: dict) -> bool:
    """同时有转发与评论统计但无 favorite，对应 B 站页面上无收藏按钮的动态。"""
    if not stat or "favorite" in stat:
        return False
    has_forward = any(key in stat for key in ("forward", "repost", "share"))
    has_comment = "comment" in stat
    return has_forward and has_comment


def favorite_supported(
    item: dict,
    *,
    client: BilibiliClient | None = None,
    dynamic_id: str | None = None,
) -> bool:
    """动态是否支持收藏。不确定时默认尝试收藏，避免 dynamic/detail 缺字段导致误判。"""
    stat = _extract_module_stat(item)
    if stat and "favorite" in stat:
        return True
    if stat and _module_stat_confirms_no_favorite(stat):
        if client is not None and dynamic_id:
            opus_item = fetch_opus_detail_item(client, dynamic_id)
            if opus_item:
                opus_stat = _extract_module_stat(opus_item)
                if opus_stat and "favorite" in opus_stat:
                    return True
        return False
    return True


def build_dynamic_context(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    action_text: str,
    sender_uid: int | None = None,
) -> DynamicContext:
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        raise RuntimeError("无法获取动态详情")

    referer = opus_link(dynamic_id)
    basic = item.get("basic") or {}
    comment_rid = str(basic.get("comment_id_str") or dynamic_id)
    comment_type = int(basic.get("comment_type") or 17)
    uid = sender_uid or resolve_sender_uid(item)

    modules = item.get("modules") or {}
    stat = modules.get("module_stat") or {}
    like_obj = stat.get("like") or {}
    liked = bool(like_obj.get("status"))

    followed = is_following(client, uid=uid, referer=referer)
    favorite_available = favorite_supported(item, client=client, dynamic_id=dynamic_id)
    favorited = (
        is_favorited(client, dynamic_id=dynamic_id, referer=referer)
        if favorite_available
        else False
    )
    reposted = is_reposted(client, dynamic_id=dynamic_id, referer=referer)
    commented = has_comment(
        client,
        rid=comment_rid,
        comment_type=comment_type,
        action_text=action_text,
        referer=referer,
    )

    return DynamicContext(
        dynamic_id=dynamic_id,
        sender_uid=uid,
        referer=referer,
        comment_rid=comment_rid,
        comment_type=comment_type,
        liked=liked,
        favorited=favorited,
        favorite_available=favorite_available,
        followed=followed,
        reposted=reposted,
        commented=commented,
    )


def is_following(client: BilibiliClient, *, uid: int, referer: str) -> bool:
    try:
        payload = client.request_json(RELATION_URL, params={"fid": uid}, referer=referer)
    except RuntimeError:
        return False
    if api_code(payload) != 0:
        return False
    attribute = int((payload.get("data") or {}).get("attribute") or 0)
    return attribute in FOLLOWING_ATTRIBUTES


def _opus_favorite_status(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool | None:
    try:
        payload = client.get_json(
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail",
            params={
                "id": dynamic_id,
                "features": "htmlNewStyle,ugcDelete,editable,opusPrivateVisible",
            },
            referer=referer,
        )
    except RuntimeError:
        return None
    if _api_code(payload) != 0:
        return None
    item = (payload.get("data") or {}).get("item") or {}
    for module in item.get("modules") or []:
        if module.get("module_type") != "MODULE_TYPE_STAT":
            continue
        favorite = (module.get("module_stat") or {}).get("favorite") or {}
        return bool(favorite.get("status"))
    return None


def is_favorited(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool:
    status = _opus_favorite_status(client, dynamic_id=dynamic_id, referer=referer)
    return bool(status)


def is_reposted(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool:
    notice = fetch_notice_for_interact(client, dynamic_id)
    if notice:
        return bool(notice[0].get("reposted"))
    return has_reposted_in_space_feed(client, dynamic_id=dynamic_id)


def has_reposted_in_space_feed(client: BilibiliClient, *, dynamic_id: str) -> bool:
    uid = get_login_uid()
    if not uid:
        return False
    referer = f"https://space.bilibili.com/{uid}/dynamic"
    offset = ""
    target = str(dynamic_id)
    for _ in range(SPACE_FEED_MAX_PAGES):
        try:
            payload = client.request_json(
                SPACE_FEED_URL,
                params={"host_mid": uid, "offset": offset, "type": "all"},
                referer=referer,
            )
        except RuntimeError:
            return False
        if api_code(payload) != 0:
            return False
        data = payload.get("data") or {}
        items = data.get("items") or []
        for item in items:
            if item.get("type") != "DYNAMIC_TYPE_FORWARD":
                continue
            orig = item.get("orig") or {}
            if str(orig.get("id_str") or "") == target:
                return True
        offset = str(data.get("offset") or "")
        if not offset or len(items) < SPACE_FEED_PAGE_SIZE:
            break
    return False


def has_comment(
    client: BilibiliClient,
    *,
    rid: str,
    comment_type: int,
    action_text: str,
    referer: str,
) -> bool:
    uid = get_login_uid()
    if not uid:
        return False
    try:
        payload = client.request_json(
            REPLY_MAIN_URL,
            params={"oid": rid, "type": comment_type, "mode": 3, "next": 0, "ps": 20},
            referer=referer,
        )
    except RuntimeError:
        return False
    if api_code(payload) != 0:
        return False
    replies = (payload.get("data") or {}).get("replies") or []
    target = action_text.strip()
    for reply in replies:
        member = reply.get("member") or {}
        if str(member.get("mid")) != str(uid):
            continue
        content = reply.get("content") or {}
        message = str(content.get("message") or "")
        if target and target in message:
            return True
    return False


def like_dynamic(client: BilibiliClient, *, dynamic_id: str, csrf: str, referer: str) -> ActionResult:
    payload = client.post_json(
        LIKE_URL,
        {
            "dyn_id_str": dynamic_id,
            "up": 1,
            "spmid": "333.1369.0.0",
            "from_spmid": "333.999.0.0",
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        return ActionResult("like", True, "")
    if code == 65006:
        return ActionResult("like", True, "已赞过")
    return ActionResult("like", False, f"code={code} {_api_message(payload)}".strip())


def follow_user(client: BilibiliClient, *, uid: int, csrf: str, referer: str) -> ActionResult:
    payload = client.post_form(
        FOLLOW_URL,
        {"fid": uid, "act": 1, "re_src": 11, "csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        return ActionResult("follow", True, f"uid={uid}")
    if code == 22014:
        return ActionResult("follow", True, f"uid={uid} 已关注")
    return ActionResult("follow", False, f"code={code} {_api_message(payload)}".strip())


def favorite_dynamic(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    csrf: str,
    referer: str,
) -> ActionResult:
    if is_favorited(client, dynamic_id=dynamic_id, referer=referer):
        return ActionResult("favorite", True, "已收藏，跳过")

    payload = client.post_json(
        COSMO_SIMPLE_ACTION_URL,
        {
            "meta": {
                "spmid": "444.42.0.0",
                "from_spmid": "333.1365.0.0",
                "from": "unknown",
            },
            "entity": {
                "object_id_str": dynamic_id,
                "type": {"biz": 2},
            },
            "action": 3,
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    message = _api_message(payload)
    if code == 0:
        for attempt in range(4):
            if is_favorited(client, dynamic_id=dynamic_id, referer=referer):
                return ActionResult("favorite", True, "")
            if attempt < 3:
                time.sleep(0.6 + attempt * 0.4)
        return ActionResult("favorite", False, message or "收藏状态未更新")
    if code in (65006, 75008):
        return ActionResult("favorite", True, message or "已收藏")
    return ActionResult("favorite", False, f"code={code} {message}".strip())


def repost_dynamic(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    my_uid: int,
    csrf: str,
    referer: str,
    content: str,
) -> ActionResult:
    text = content[:233] or "转发动态"
    try:
        # This creates a public dynamic. Never replay an ambiguous submission.
        payload = client.post_json(
            REPOST_URL,
            {
                "dyn_req": {
                    "content": {"contents": [{"raw_text": text, "type": 1, "biz_id": ""}]},
                    "scene": 4,
                    "meta": {"app_meta": {"from": "create.dynamic.web", "mobi_app": "web"}},
                },
                "web_repost_src": {"dyn_id_str": str(dynamic_id)},
            },
            params={"csrf": csrf, "platform": "web"},
            referer=referer,
            retries=0,
            raise_on_code=False,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        status = f"HTTP {exc.response.status_code}；" if isinstance(exc, httpx.HTTPStatusError) else ""
        # Do not log the request URL: its query contains the CSRF token.
        raise RuntimeError(
            f"{status}转发结果未确认，未自动重试。请先到 B 站个人动态核对是否已发布，再决定是否重试。"
        ) from None
    if not isinstance(payload, dict):
        raise RuntimeError("转发响应格式异常，未自动重试。请先到 B 站个人动态核对。")
    code = _api_code(payload)
    if code == 0:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("转发响应缺少结果，未自动重试。请先到 B 站个人动态核对。")
        result = data.get("result")
        if result is not None and result != 0:
            return ActionResult("repost", False, f"转发未成功 result={result}")
        new_id = str(data.get("dyn_id_str") or data.get("dyn_id") or "")
        if result == 0 or (new_id.isdecimal() and int(new_id) > 0):
            return ActionResult("repost", True, text[:80])
        raise RuntimeError("转发响应缺少成功标志，未自动重试。请先到 B 站个人动态核对。")
    message = _api_message(payload)
    return ActionResult("repost", False, f"code={code} {message}".strip())


def comment_dynamic(
    client: BilibiliClient,
    *,
    rid: str,
    comment_type: int,
    message: str,
    csrf: str,
    referer: str,
) -> ActionResult:
    payload = client.post_form(
        COMMENT_URL,
        {"oid": rid, "type": comment_type, "message": message, "csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        return ActionResult("comment", True, message[:80])
    if code == 12051:
        return ActionResult("comment", True, "已有相同评论")
    return ActionResult("comment", False, f"code={code} {_api_message(payload)}".strip())


def execute_full_participation(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    sender_uid: int | None = None,
    action_text: str = DEFAULT_PARTICIPATE_TEXT,
    dry_run: bool = False,
    on_step: Callable[[int, int, str, ActionName], None] | None = None,
) -> tuple[list[ActionResult], DynamicContext]:
    text = (action_text or DEFAULT_PARTICIPATE_TEXT).strip() or DEFAULT_PARTICIPATE_TEXT
    context = build_dynamic_context(
        client,
        dynamic_id=dynamic_id,
        action_text=text,
        sender_uid=sender_uid,
    )

    total_steps = len(PARTICIPATION_STEPS)

    def report_step(step_index: int, action_name: ActionName, detail: str = "") -> None:
        if not on_step:
            return
        label = ACTION_LABELS.get(action_name, action_name)
        message = f"正在{label}（{step_index}/{total_steps}）"
        if detail:
            message = f"{message} · {detail}"
        on_step(step_index, total_steps, message, action_name)

    if dry_run:
        return [
            ActionResult("like", True, "跳过" if context.liked else "将点赞"),
            ActionResult("follow", True, "跳过" if context.followed else f"将关注 uid={context.sender_uid}"),
            ActionResult(
                "favorite",
                True,
                "跳过"
                if context.favorited
                else ("无收藏入口，跳过" if not context.favorite_available else f"将收藏 rid={context.comment_rid}"),
            ),
            ActionResult("repost", True, "跳过" if context.reposted else f"将转发 {text[:40]}"),
            ActionResult(
                "comment",
                True,
                "跳过" if context.commented else f"将评论 type={context.comment_type}",
            ),
        ], context

    csrf, my_uid = require_login()
    actions: list[ActionResult] = []

    report_step(1, "like")
    if context.liked:
        actions.append(ActionResult("like", True, "已点赞，跳过"))
    else:
        actions.append(like_dynamic(client, dynamic_id=dynamic_id, csrf=csrf, referer=context.referer))
    time.sleep(ACTION_INTERVAL_SEC)

    report_step(2, "follow")
    if context.followed:
        actions.append(ActionResult("follow", True, f"uid={context.sender_uid} 已关注，跳过"))
    else:
        actions.append(follow_user(client, uid=context.sender_uid, csrf=csrf, referer=context.referer))
    time.sleep(ACTION_INTERVAL_SEC)

    report_step(3, "favorite")
    if not context.favorite_available:
        actions.append(ActionResult("favorite", True, "无收藏入口，跳过"))
    elif context.favorited:
        actions.append(ActionResult("favorite", True, "已收藏，跳过"))
    else:
        actions.append(
            favorite_dynamic(client, dynamic_id=dynamic_id, csrf=csrf, referer=context.referer)
        )
    time.sleep(ACTION_INTERVAL_SEC)

    report_step(4, "repost")
    if context.reposted:
        actions.append(ActionResult("repost", True, "已转发，跳过"))
    else:
        actions.append(
            repost_dynamic(
                client,
                dynamic_id=dynamic_id,
                my_uid=my_uid,
                csrf=csrf,
                referer=context.referer,
                content=text,
            )
        )
    time.sleep(ACTION_INTERVAL_SEC)

    report_step(5, "comment")
    if context.commented:
        actions.append(ActionResult("comment", True, "已评论，跳过"))
    else:
        actions.append(
            comment_dynamic(
                client,
                rid=context.comment_rid,
                comment_type=context.comment_type,
                message=text,
                csrf=csrf,
                referer=context.referer,
            )
        )

    return actions, context
