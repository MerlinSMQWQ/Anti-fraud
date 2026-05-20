"""Smoke tests for lexical and fallback search behavior."""

import pytest

from anti_fraud_explorer.config import settings
from anti_fraud_explorer.domain.dataset import load_dataset
from anti_fraud_explorer.service import search as search_module
from anti_fraud_explorer.service.search import (
    build_search_text,
    prepend_pinyin_matches,
    search_items,
)


pytestmark = pytest.mark.skipif(
    not settings.dataset_path.exists(),
    reason="Dataset file not found — run scripts/process_raw_data.py first",
)


def test_search_items_returns_brush_order_cases_for_shuadan():
    kb = load_dataset()
    items, total = search_items(kb, query="刷单", limit=5)
    assert total > 0
    assert items
    assert "刷单" in items[0].title


def test_search_items_finds_verification_code_cases():
    kb = load_dataset()
    items, total = search_items(kb, query="验证码", limit=5)
    assert total > 0
    assert any("验证码" in item.content or "验证码" in build_search_text(item) for item in items)


def test_search_items_finds_student_cases():
    kb = load_dataset()
    items, total = search_items(kb, query="大学生", limit=5)
    assert total > 0
    assert any("大学生" in item.title or item.victim_group == "学生" for item in items)


def test_pinyin_fallback_does_not_reorder_clear_title_hits():
    kb = load_dataset()
    ranked_items, _ = search_items(kb, query="刷单", limit=5)
    preserved = prepend_pinyin_matches(kb, ranked_items, "刷单", kb.items)
    assert [item.id for item in preserved[:5]] == [item.id for item in ranked_items[:5]]


def test_empty_query_with_category_browses_without_retrieval(monkeypatch):
    kb = load_dataset()
    category = "刷单返利类"

    def fail_rank(*args, **kwargs):
        raise AssertionError("browse mode should not call lexical ranking")

    def fail_hybrid(*args, **kwargs):
        raise AssertionError("browse mode should not call hybrid ranking")

    def fail_pinyin(*args, **kwargs):
        raise AssertionError("browse mode should not call pinyin fallback")

    monkeypatch.setattr(search_module, "rank_lexical", fail_rank)
    monkeypatch.setattr(search_module, "rank_hybrid", fail_hybrid)
    monkeypatch.setattr(search_module, "prepend_pinyin_matches", fail_pinyin)

    items, total = search_items(kb, query="", category=category, limit=50)

    assert total > 0
    assert items
    assert all(item.ccl2023_category == category for item in items)


def test_empty_query_with_multiple_filters_browses_matching_cases():
    kb = load_dataset()
    items, total = search_items(
        kb,
        query="",
        category="冒充电商物流客服类",
        risk_level="极高",
        entry_channel="短信",
        limit=100,
    )

    assert total > 0
    assert items
    assert all(item.ccl2023_category == "冒充电商物流客服类" for item in items)
    assert all(item.risk_level == "极高" for item in items)
    assert all("短信" in item.entry_channels for item in items)
