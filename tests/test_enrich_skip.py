from __future__ import annotations

import pytest

from src.lottery_enricher import ENRICH_SKIP_REASON, EnrichSkippedError, enrich_forward_activity
from src.pipeline.refresh_all_pipeline import run_new_links_pipeline


def test_enrich_forward_skips_when_parse_not_lottery(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.lottery_enricher.fetch_dynamic_content_with_retry",
        lambda *args, **kwargs: "足够长的正文用于详情解析测试，包含转发与奖品语义",
    )
    monkeypatch.setattr(
        "src.pipeline.enrich_fetch_context.fetch_dynamic_detail",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "src.lottery_enricher.parse_forward_content",
        lambda dynamic_id, content: {
            "is_lottery": False,
            "prize_description": "",
            "winner_count": 0,
            "confidence": "low",
        },
    )

    class _Client:
        pass

    with pytest.raises(EnrichSkippedError) as exc:
        enrich_forward_activity(_Client(), dynamic_id="1224962472871460885")
    assert exc.value.reason == ENRICH_SKIP_REASON


def test_pipeline_continues_when_enrich_skipped(monkeypatch) -> None:
    saved: list[dict] = []

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(dynamic_id, "转发抽奖", False)

    def fake_enrich(client, **kwargs):
        dynamic_id = str(kwargs["dynamic_id"])
        if dynamic_id == "1224962472871460885":
            raise EnrichSkippedError(dynamic_id)
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
            lottery_type="转发抽奖",
            enriched_at=1,
            business_id=dynamic_id,
            business_type=0,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=1,
            repost_fetched=True,
        )

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.apply_initial_status",
        lambda row: row,
    )
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.append_activities",
        lambda rows: saved.extend(rows) or len(rows),
    )

    result = run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1224962472871460885",
            "https://www.bilibili.com/opus/1224962472871460886",
        ],
        workers=2,
    )

    assert result.ok is True
    assert result.skipped_count == 1
    assert result.skip_reasons[ENRICH_SKIP_REASON] == 1
    assert result.enriched_count == 1
    assert result.persisted_count == 1
    assert len(saved) == 1
    assert saved[0]["dynamic_id"] == "1224962472871460886"


def test_pipeline_passes_classify_content_to_enrich(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(
            dynamic_id,
            "转发抽奖",
            False,
            classify_content="分类正文缓存用于详情复用足够长度",
        )

    def fake_enrich(client, **kwargs):
        dynamic_id = str(kwargs["dynamic_id"])
        captured["dynamic_id"] = dynamic_id
        captured["classify_content"] = kwargs.get("classify_content")
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
            lottery_type="转发抽奖",
            enriched_at=1,
            business_id=dynamic_id,
            business_type=0,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=1,
            repost_fetched=True,
        )

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.apply_initial_status",
        lambda row: row,
    )
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.append_activities", lambda rows: len(rows))

    run_new_links_pipeline(
        ["https://www.bilibili.com/opus/1224962472871460886"],
        workers=1,
    )
    assert captured["classify_content"] == "分类正文缓存用于详情复用足够长度"


def test_pipeline_continues_on_legacy_not_lottery_runtime_error(monkeypatch) -> None:
    saved: list[dict] = []

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(dynamic_id, "转发抽奖", False)

    def fake_enrich(client, **kwargs):
        dynamic_id = str(kwargs["dynamic_id"])
        if dynamic_id == "1224962472871460885":
            raise RuntimeError(f"未识别为抽奖活动: {dynamic_id}")
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
            lottery_type="转发抽奖",
            enriched_at=1,
            business_id=dynamic_id,
            business_type=0,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=1,
            repost_fetched=True,
        )

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.apply_initial_status",
        lambda row: row,
    )
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.append_activities",
        lambda rows: saved.extend(rows) or len(rows),
    )

    result = run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1224962472871460885",
            "https://www.bilibili.com/opus/1224962472871460886",
        ],
        workers=2,
    )

    assert result.ok is True
    assert result.skip_reasons[ENRICH_SKIP_REASON] == 1
    assert len(saved) == 1


def test_pipeline_collects_classify_failure_and_continues(monkeypatch) -> None:
    saved: list[dict] = []

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        if dynamic_id == "1224962472871460885":
            raise RuntimeError("404 Not Found")
        return ClassifyOutcome(dynamic_id, "互动抽奖", False)

    def fake_enrich(client, **kwargs):
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        dynamic_id = str(kwargs["dynamic_id"])
        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
            lottery_type="互动抽奖",
            enriched_at=1,
            business_id=dynamic_id,
            business_type=1,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=1,
            repost_fetched=True,
        )

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.apply_initial_status", lambda row: row)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.append_activities",
        lambda rows: saved.extend(rows) or len(rows),
    )

    result = run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1224962472871460885",
            "https://www.bilibili.com/opus/1224962472871460886",
        ],
        workers=1,
    )

    assert result.ok is True
    assert result.failed_count == 1
    assert result.failures == [
        {
            "dynamic_id": "1224962472871460885",
            "stage": "分类",
            "error": "404 Not Found",
        }
    ]
    assert result.persisted_count == 1
    assert saved[0]["dynamic_id"] == "1224962472871460886"


def test_pipeline_collects_unexpected_enrich_failure_and_continues(monkeypatch) -> None:
    saved: list[dict] = []

    def fake_classify(client, dynamic_id):
        from src.pipeline.classify_step import ClassifyOutcome

        return ClassifyOutcome(dynamic_id, "转发抽奖", False)

    def fake_enrich(client, **kwargs):
        dynamic_id = str(kwargs["dynamic_id"])
        if dynamic_id == "1224962472871460885":
            raise RuntimeError("详情接口临时失败")
        from src.lottery_enricher import EnrichedActivity, PrizeTier

        return EnrichedActivity(
            dynamic_id=dynamic_id,
            source_url=f"https://www.bilibili.com/opus/{dynamic_id}",
            lottery_type="转发抽奖",
            enriched_at=1,
            business_id=dynamic_id,
            business_type=0,
            draw_status="active",
            lottery_time=9999999999,
            prizes=[PrizeTier(tier="first", winner_count=1, description="奖")],
            participants=0,
            conditions={},
            winners=None,
            platform_participated=None,
            repost_count=1,
            repost_fetched=True,
        )

    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.known_activity_ids", lambda: set())
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.classify_new_link", fake_classify)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.load_participations", lambda: {})
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.enrich_activity", fake_enrich)
    monkeypatch.setattr("src.pipeline.refresh_all_pipeline.apply_initial_status", lambda row: row)
    monkeypatch.setattr(
        "src.pipeline.refresh_all_pipeline.append_activities",
        lambda rows: saved.extend(rows) or len(rows),
    )

    result = run_new_links_pipeline(
        [
            "https://www.bilibili.com/opus/1224962472871460885",
            "https://www.bilibili.com/opus/1224962472871460886",
        ],
        workers=2,
    )

    assert result.ok is True
    assert result.failed_count == 1
    assert result.failures[0]["dynamic_id"] == "1224962472871460885"
    assert result.failures[0]["stage"] == "详情"
    assert result.persisted_count == 1
    assert saved[0]["dynamic_id"] == "1224962472871460886"
