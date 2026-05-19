"""Smoke tests for dataset loading."""
import pytest
from anti_fraud_explorer.config import settings
from anti_fraud_explorer.dataset import (
    load_dataset,
    get_knowledge_base,
    KnowledgeBase,
    normalize_text,
)


pytestmark = pytest.mark.skipif(
    not settings.dataset_path.exists(),
    reason="Dataset file not found — run scripts/build_dataset.py first",
)


def test_normalize_text_whitespace():
    assert normalize_text("  你好  世界  ") == "你好 世界"


def test_normalize_text_nbsp():
    assert normalize_text("hello\u00a0world") == "hello world"


def test_load_dataset_returns_knowledge_base():
    kb = load_dataset()
    assert isinstance(kb, KnowledgeBase)
    assert len(kb.items) > 0


def test_knowledge_base_categories():
    kb = load_dataset()
    assert len(kb.categories) > 0
    for cat in kb.categories:
        assert cat.name
        assert cat.item_count > 0


def test_dataset_items_have_required_fields():
    kb = load_dataset()
    item = kb.items[0]
    assert item.id
    assert item.title
    assert item.category
    assert item.content


def test_get_knowledge_base_caches():
    kb1 = get_knowledge_base()
    kb2 = get_knowledge_base()
    assert kb1 is kb2
