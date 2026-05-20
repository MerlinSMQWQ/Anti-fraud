"""Presentation helpers for turning dataset items into UI cards."""

from typing import Any

from ..domain.dataset import item_to_dict


def enriched_item_card(item: Any) -> dict[str, Any]:
    """Return a frontend-ready item card based on the current dataset schema."""
    return item_to_dict(item)


def title_with_family(item: Any) -> str:
    title = item.title
    category = item.ccl2023_category
    if category and category not in title:
        return f"{title}（{category}）"
    return title


def source_payload(item: Any) -> dict[str, str]:
    return {
        "id": item.id,
        "title": item.title,
        "ccl2023_category": item.ccl2023_category,
        "custom_subcategory": item.custom_subcategory,
    }


# Backward-compatible aliases used while agent modules are being split.
_enriched_item_card = enriched_item_card
_title_with_family = title_with_family
_source_payload = source_payload
