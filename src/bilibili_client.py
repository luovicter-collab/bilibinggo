from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import httpx

from src.bilibili_rate_limit import acquire_bilibili_request_slot

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_RATE_LIMIT_CODES = frozenset({-352, -509})

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]

WBI_FILTER_RE = re.compile(r"[!'()*]")


def api_code(payload: dict) -> int:
    """解析 B 站 API 响应 code；code=0 表示成功（勿用 ``code or -1``，0 会被误判）。"""
    code = payload.get("code")
    if code is None:
        return -1
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def _load_cookie_string() -> str | None:
    from src import app_paths

    env = os.environ.get("BILI_COOKIE", "").strip()
    if env:
        return env
    path = app_paths.cookie_file()
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _mixin_key(img_key: str, sub_key: str) -> str:
    material = img_key + sub_key
    return "".join(material[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    signed = {k: WBI_FILTER_RE.sub("", str(v)) for k, v in params.items()}
    signed["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((query + _mixin_key(img_key, sub_key)).encode()).hexdigest()
    return signed


class BilibiliClient:
    def __init__(self, timeout: float = 25.0, *, warmup: bool = True) -> None:
        headers = dict(DEFAULT_HEADERS)
        cookie = _load_cookie_string()
        if cookie:
            headers["Cookie"] = cookie
        self._client = httpx.Client(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._img_key: str | None = None
        self._sub_key: str | None = None
        self._http_lock = threading.Lock()
        if warmup:
            self._warmup()

    def _warmup(self) -> None:
        try:
            self._http_get("https://www.bilibili.com")
            if "buvid3" not in self._client.cookies:
                self._client.cookies.set(
                    "buvid3",
                    f"{uuid.uuid4().hex}infoc",
                    domain=".bilibili.com",
                )
        except httpx.HTTPError:
            pass

    def _http_get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        acquire_bilibili_request_slot()
        with self._http_lock:
            return self._client.get(url, params=params or {}, headers=headers)

    def _http_post(
        self,
        url: str,
        *,
        data: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        acquire_bilibili_request_slot()
        with self._http_lock:
            return self._client.post(
                url,
                params=params or {},
                data=data,
                json=json,
                headers=headers,
            )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BilibiliClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _reset_wbi_keys(self) -> None:
        self._img_key = None
        self._sub_key = None

    def _ensure_wbi_keys(self) -> None:
        if self._img_key and self._sub_key:
            return
        resp = self._http_get("https://api.bilibili.com/x/web-interface/nav")
        resp.raise_for_status()
        data = resp.json()
        wbi = (data.get("data") or {}).get("wbi_img") or {}
        img = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
        sub = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
        if not img or not sub:
            raise RuntimeError("无法获取 WBI 签名密钥")
        self._img_key, self._sub_key = img, sub

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        *,
        wbi: bool = False,
        referer: str | None = None,
        retries: int = 3,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            req_params = dict(params or {})
            headers = {"Referer": referer} if referer else None
            if wbi:
                if attempt > 0:
                    self._reset_wbi_keys()
                self._ensure_wbi_keys()
                req_params = wbi_sign(req_params, self._img_key, self._sub_key)
            try:
                resp = self._http_get(url, params=req_params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                code = data.get("code")
                if code in (0, None):
                    return data
                if code in (-352, -509, -799) and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {data.get('message')}")
                    continue
                raise RuntimeError(f"API error {code}: {data.get('message')}")
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def request_json(self, url: str, params: dict | None = None, *, referer: str | None = None, retries: int = 3) -> dict:
        """请求 JSON 但不因业务 code 非 0 抛错（供 lottery_notice 等接口使用）。"""
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_get(url, params=params or {}, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < retries and (
                    isinstance(exc, httpx.RequestError)
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise RuntimeError("响应不是有效 JSON") from exc
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def post_form(
        self,
        url: str,
        data: dict,
        *,
        referer: str | None = None,
        retries: int = 3,
        raise_on_code: bool = True,
    ) -> dict:
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_post(url, data=data, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                code = payload.get("code")
                if code in (0, None):
                    return payload
                if not raise_on_code and code not in _RATE_LIMIT_CODES:
                    return payload
                if code in _RATE_LIMIT_CODES and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {payload.get('message')}")
                    continue
                if raise_on_code:
                    message = payload.get("message") or payload.get("msg") or ""
                    raise RuntimeError(f"API error {code}: {message}")
                return payload
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                if isinstance(exc, json.JSONDecodeError):
                    raise RuntimeError("响应不是有效 JSON") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def post_json(
        self,
        url: str,
        payload: dict,
        *,
        params: dict | None = None,
        referer: str | None = None,
        retries: int = 3,
        raise_on_code: bool = True,
    ) -> dict:
        headers = {"Referer": referer, "Content-Type": "application/json"} if referer else {
            "Content-Type": "application/json"
        }
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_post(url, params=params or {}, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise RuntimeError("响应不是 JSON 对象")
                code = data.get("code")
                if code in (0, None):
                    return data
                if not raise_on_code and code not in _RATE_LIMIT_CODES:
                    return data
                if code in _RATE_LIMIT_CODES and attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    last_error = RuntimeError(f"API error {code}: {data.get('message')}")
                    continue
                if raise_on_code:
                    message = data.get("message") or data.get("msg") or ""
                    raise RuntimeError(f"API error {code}: {message}")
                return data
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                if attempt < retries and (
                    isinstance(exc, (httpx.RequestError, json.JSONDecodeError))
                    or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 412, 429, 500, 502, 503, 504))
                ):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                if isinstance(exc, json.JSONDecodeError):
                    raise RuntimeError("响应不是有效 JSON") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def get_text(self, url: str, *, referer: str | None = None, retries: int = 3) -> str:
        headers = {"Referer": referer} if referer else None
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http_get(url, headers=headers)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if isinstance(exc, httpx.RequestError):
                    raise RuntimeError(f"网络请求失败: {exc}") from exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("请求失败")

    def get_latest_video(self, mid: int) -> dict:
        referer = f"https://space.bilibili.com/{mid}/video"
        params = {
            "mid": mid,
            "pn": 1,
            "ps": 1,
            "tid": 0,
            "order": "pubdate",
            "platform": "web",
        }
        errors: list[str] = []
        try:
            data = self.get_json(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=params,
                wbi=True,
                referer=referer,
            )
            vlist = (data.get("data") or {}).get("list", {}).get("vlist") or []
            if vlist:
                return vlist[0]
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            errors.append(str(exc))

        try:
            return self._get_latest_video_fallback(mid, referer=referer)
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            errors.append(str(exc))
            raise RuntimeError(
                "获取最新视频失败（B 站风控 -352/-412）。\n"
                "请将浏览器 Cookie 保存到 config/cookies.txt 后重试。\n"
                "参考 config/cookies.txt.example\n"
                + "\n".join(errors)
            ) from exc

    def _get_latest_video_fallback(self, mid: int, *, referer: str) -> dict:
        """WBI 风控时，尝试旧接口（有 Cookie 时通常可用）。"""
        data = self.get_json(
            "https://api.bilibili.com/x/space/arc/search",
            params={"mid": mid, "pn": 1, "ps": 1, "order": "pubdate"},
            referer=referer,
        )
        vlist = (data.get("data") or {}).get("list", {}).get("vlist") or []
        if not vlist:
            raise RuntimeError("未找到该 UP 的投稿视频")
        return vlist[0]

    def get_video_detail(self, bvid: str) -> dict:
        referer = f"https://www.bilibili.com/video/{bvid}"
        try:
            data = self.get_json(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                referer=referer,
            )
            detail = data.get("data")
            if detail:
                return detail
        except RuntimeError:
            pass
        return self._get_video_detail_from_page(bvid, referer=referer)

    def _get_video_detail_from_page(self, bvid: str, *, referer: str) -> dict:
        html = self.get_text(f"https://www.bilibili.com/video/{bvid}", referer=referer)
        state_match = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
            html,
            re.S,
        )
        if not state_match:
            raise RuntimeError(f"无法从视频页解析详情: {bvid}")
        state = json.loads(state_match.group(1))
        video_data = state.get("videoData") or {}
        if not video_data:
            raise RuntimeError(f"无法从视频页解析详情: {bvid}")
        return video_data

    def get_latest_article(self, mid: int) -> dict:
        return self.get_recent_articles(mid, limit=1)[0]

    def get_recent_articles(self, mid: int, *, limit: int = 2) -> list[dict]:
        referer = f"https://space.bilibili.com/{mid}/upload/opus"
        data = self.get_json(
            "https://api.bilibili.com/x/space/article",
            params={"mid": mid, "pn": 1, "ps": max(1, limit), "sort": "publish_time"},
            referer=referer,
        )
        articles = (data.get("data") or {}).get("articles") or []
        if not articles:
            raise RuntimeError("未找到该 UP 的专栏文章")
        return articles[:limit]

    def get_article_detail(self, cv_id: int) -> dict:
        referer = f"https://www.bilibili.com/read/cv{cv_id}"
        data = self.get_json(
            "https://api.bilibili.com/x/article/view",
            params={"id": cv_id},
            referer=referer,
        )
        detail = data.get("data")
        if not detail:
            raise RuntimeError(f"无法获取专栏详情: cv{cv_id}")
        return detail
