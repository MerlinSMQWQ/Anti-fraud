"""Dataset loading and normalized in-memory access — v3 schema (LLM-normalized)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import settings


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    item_count: int


def _parse_multivalue(value: Any) -> tuple[str, ...]:
    """Parse a string like '电话；短信' or a list into a tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if isinstance(value, str) and value.strip():
        return tuple(s.strip() for s in value.split("；") if s.strip())
    return ()


def _first_value(value: Any) -> str:
    """Get the first value from a multi-value field, or the string itself."""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    if isinstance(value, str) and "；" in value:
        return value.split("；")[0].strip()
    return str(value) if value else ""


@dataclass(frozen=True)
class CaseItem:
    """Anti-fraud case item — populated from LLM-normalized dataset (schema v3)."""

    id: str
    title: str
    summary: str

    # ── Primary classification ──
    ccl2023_category: str = ""

    # ── Rich structured fields (directly from dataset) ──
    nature_judgment: str = ""
    judgment_reason: str = ""
    entry_channels: tuple[str, ...] = ()
    impersonated_identity: str = ""
    false_belief: str = ""
    key_methods: tuple[str, ...] = ()
    target_assets: str = ""
    fraud_stage: str = ""
    risk_signals: str = ""
    risk_level: str = ""
    loss_occurred: str = ""
    loss_type: str = ""
    prevention_advice: str = ""
    source_name: str = ""
    source_type: str = ""
    collection_date: str = ""
    is_desensitized: str = ""

    # ── Supplementary ──
    official_category: str = ""
    custom_subcategory: str = ""
    tags: tuple[str, ...] = ()
    involved_platforms: str = ""
    victim_group: str = ""

    # ── Computed fields (for search / display) ──

    @property
    def family(self) -> str:
        """Parent category — the broad CCL2023 class name."""
        return self.ccl2023_category

    @property
    def category(self) -> str:
        """Same as ccl2023_category for backward compat."""
        return self.ccl2023_category

    @property
    def content(self) -> str:
        """Full text payload for embedding / context — built from structured fields."""
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.judgment_reason:
            parts.append(self.judgment_reason)
        if self.risk_signals:
            parts.append(self.risk_signals)
        if self.prevention_advice:
            parts.append(self.prevention_advice)
        return "\n".join(parts)

    @property
    def search_text(self) -> str:
        """Lightweight text for lexical search (title + category + tags + methods + channels)."""
        parts = [self.title, self.ccl2023_category]
        if self.tags:
            parts.extend(self.tags)
        if self.key_methods:
            parts.extend(self.key_methods)
        if self.entry_channels:
            parts.extend(self.entry_channels)
        return " ".join(parts)

    @property
    def level(self) -> str:
        """Backward-compat: risk_level mapped to old level enum."""
        return self.risk_level

    @property
    def province(self) -> str:
        """Province is no longer extracted at build time. Returns empty."""
        return ""

    @property
    def city(self) -> str:
        """City is no longer extracted at build time. Returns empty."""
        return ""

    @property
    def district(self) -> str:
        """District is no longer extracted at build time. Returns empty."""
        return ""

    @property
    def suitable_scenarios(self) -> tuple[str, ...]:
        """Scenarios are no longer pre-computed. Returns empty."""
        return ()


# ── ai_fields are now inline in CaseItem — kept for callers that still import it ──

def get_ai_fields(item_id: str) -> dict[str, str]:
    """Return ai_fields from CaseItem. Deprecated: fields are now inline."""
    kb = get_knowledge_base()
    item = kb.get(item_id)
    if item is None:
        return {"key_methods": "", "history": "", "prevention_advice": ""}
    return {
        "key_methods": "；".join(item.key_methods),
        "history": item.source_name,
        "prevention_advice": item.prevention_advice,
    }


def get_structured_meta(item_id: str) -> dict[str, Any]:
    """Return structured metadata. Deprecated: fields are now inline."""
    kb = get_knowledge_base()
    item = kb.get(item_id)
    if item is None:
        return {"level": "", "entry_channels": ()}
    return {
        "level": item.risk_level,
        "entry_channels": item.entry_channels,
    }


class KnowledgeBase:
    def __init__(self, payload: dict[str, Any]):
        self.schema_version = payload.get("schema_version", 1)
        self.generated_at = payload.get("generated_at", "")
        self.source = payload.get("source", {})
        self.categories = [
            Category(
                id=int(category["id"]),
                name=str(category["name"]),
                item_count=int(category.get("item_count", 0)),
            )
            for category in payload.get("categories", [])
        ]
        self.items = [
            CaseItem(
                id=str(item.get("case_id") or item.get("id") or ""),
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or ""),
                ccl2023_category=str(item.get("ccl2023_category") or ""),
                nature_judgment=str(item.get("nature_judgment") or ""),
                judgment_reason=str(item.get("judgment_reason") or ""),
                entry_channels=_parse_multivalue(item.get("entry_channels")),
                impersonated_identity=str(item.get("impersonated_identity") or ""),
                false_belief=str(item.get("false_belief") or ""),
                key_methods=_parse_multivalue(item.get("key_methods")),
                target_assets=str(item.get("target_assets") or ""),
                fraud_stage=str(item.get("fraud_stage") or ""),
                risk_signals=str(item.get("risk_signals") or ""),
                risk_level=str(item.get("risk_level") or ""),
                loss_occurred=str(item.get("loss_occurred") or ""),
                loss_type=str(item.get("loss_type") or ""),
                prevention_advice=str(item.get("prevention_advice") or ""),
                source_name=str(item.get("source_name") or ""),
                source_type=str(item.get("source_type") or ""),
                collection_date=str(item.get("collection_date") or ""),
                is_desensitized=str(item.get("is_desensitized") or ""),
                official_category=str(item.get("official_category") or ""),
                custom_subcategory=str(item.get("custom_subcategory") or ""),
                tags=_parse_multivalue(item.get("tags")),
                involved_platforms=str(item.get("involved_platforms") or ""),
                victim_group=str(item.get("victim_group") or ""),
            )
            for item in payload.get("items", [])
        ]
        self._by_id = {item.id: item for item in self.items}

    def get(self, item_id: str) -> CaseItem | None:
        return self._by_id.get(item_id)

    def category_names(self) -> list[str]:
        return [category.name for category in self.categories]


def load_dataset(path: Path | None = None) -> KnowledgeBase:
    if path is None:
        path = settings.dataset_path
    with path.open("r", encoding="utf-8") as f:
        return KnowledgeBase(json.load(f))


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return load_dataset()


def item_to_dict(item: CaseItem, include_content: bool = False) -> dict[str, Any]:
    data = {
        "id": item.id,
        "title": item.title,
        "family": item.family,
        "category": item.category,
        "summary": item.summary,
        "level": item.risk_level,
        "province": item.province,
        "city": item.city,
        "district": item.district,
        "entry_channels": list(item.entry_channels),
        "suitable_scenarios": list(item.suitable_scenarios),
        "key_methods": list(item.key_methods),
        "history": item.source_name,
        "prevention_advice": item.prevention_advice,
        # New fields
        "ccl2023_category": item.ccl2023_category,
        "risk_level": item.risk_level,
        "nature_judgment": item.nature_judgment,
        "risk_signals": item.risk_signals,
        "tags": list(item.tags),
    }
    if include_content:
        data["content"] = item.content
    return data
