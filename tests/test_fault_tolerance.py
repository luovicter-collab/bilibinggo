"""针对「单点失败导致全盘失败」三处容错缺口的回归测试。

对应 issue：#3（分类）、#5（监控用户扫描）、#8（数据源检查）。
验证：单个元素失败时流程不再中断，而是记入失败/跳过并继续处理其余元素。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.pipeline.classify_step import ClassifyOutcome
from src.pipeline.refresh_all_pipeline import run_new_links_pipeline
from src.sources.common import CheckResult
from src.watch_feed import ForwardLink
from src.watch_sync import sync_watch_forwards
from src.watch_users import WatchUser
from web.actions import run_action


class _FakeClient:
    """轻量 context-manager 替身，避免测试中真实 BilibiliClient 发起网络请求。"""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_sync_watch_forwards_skips_failed_user(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#5：单个监控用户扫描失败不应中断整轮同步，已扫用户的链接应保留。"""
    users = [
        WatchUser(mid=1, name="坏用户"),
        WatchUser(mid=2, name="好用户"),
    ]

    def fake_collect(client: object, mid: int, *, since_ts: int, until_ts: int | None) -> list[ForwardLink]:
        if mid == 1:
            raise RuntimeError("主页 404")
        return [
            ForwardLink(
                dynamic_id="1208931614786060297",
                url="https://www.bilibili.com/opus/1208931614786060297",
                pub_ts=1786850000,
                forward_id="999",
            )
        ]

    monkeypatch.setattr("src.watch_sync.BilibiliClient", _FakeClient)
    monkeypatch.setattr("src.watch_sync.collect_forward_links_for_user", fake_collect)
    monkeypatch.setattr("src.watch_sync.USER_REQUEST_DELAY", 0)

    result = sync_watch_forwards(users=users)

    assert result.users_total == 2
    assert result.users_ok == 1
    assert len(result.users_failed) == 1
    assert result.users_failed[0]["mid"] == 1
    assert result.users_failed[0]["error"] == "主页 404"
    assert len(result.user_results) == 2
    assert result.user_results[0]["ok"] is False
    assert result.user_results[1]["ok"] is True
    assert result.link_count == 1
    assert result.activity_links == ["https://www.bilibili.com/opus/1208931614786060297"]


def test_run_new_links_pipeline_skips_classify_failure(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3：单条新链接分类失败不应中断整个流水线，其余链接继续分类。"""
    def fake_classify(client: object, dynamic_id: str) -> ClassifyOutcome:
        if dynamic_id.startswith("1"):
            raise RuntimeError("动态已删除")
        return ClassifyOutcome(dynamic_id, None, True, "链接失效")

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.BilibiliClient", _FakeClient)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)

    result = run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1111111111111111111",
            "https://www.bilibili.com/opus/2222222222222222222",
        ]
    )

    assert result.ok is True
    assert result.pipeline_skipped is False
    assert result.new_link_count == 2
    assert result.skip_reasons.get("分类失败") == 1
    assert result.skip_reasons.get("链接失效") == 1
    assert result.classified_count == 0


def test_refresh_all_skips_failed_source(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#8：单个数据源检查失败不应中断整个一键更新，其余数据源照常返回。"""
    def ok_check(force: bool = False) -> CheckResult:
        return CheckResult(
            source_id="DS-1",
            updated=False,
            container_url="u1",
            container_id="c1",
            title="t1",
            published_at=0,
            previous_container_url=None,
            activity_links=[],
            checked_at=int(time.time()),
        )

    def fail_check(force: bool = False) -> CheckResult:
        raise RuntimeError("专栏 404")

    def ok_save(result: CheckResult) -> None:
        return None

    monkeypatch.setattr(
        "web.actions.DS_HANDLERS",
        [
            ("DS-1", ok_check, ok_save),
            ("DS-2", fail_check, ok_save),
        ],
    )

    res = run_action("refresh_all")

    assert res["ok"] is True
    sources = res["result"]["sources"]
    assert len(sources) == 2
    ds2 = next(s for s in sources if s["source_id"] == "DS-2")
    assert ds2["updated"] is False
    assert ds2["saved"] is False
    assert "检查失败" in res["log"]
    # 失败源不能计入「有新专栏」的源数
    assert res["result"]["sources_updated"] == 0
