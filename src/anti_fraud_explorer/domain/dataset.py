"""Dataset loading and normalized in-memory access for the v3 case schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    item_count: int


def _parse_multivalue(value: Any) -> tuple[str, ...]:
    """Parse a string like '电话；短信' or a list into a normalized tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(part for item in value if (part := normalize_text(str(item))))
    if isinstance(value, str) and value.strip():
        return tuple(part for raw in value.split("；") if (part := normalize_text(raw)))
    return ()


def _parse_text(value: Any) -> str:
    return normalize_text(str(value)) if value else ""


@dataclass(frozen=True)
class CaseItem:
    """Anti-fraud case item matching the normalized `case_items.json` schema."""

    id: str
    title: str
    summary: str
    nature_judgment: str
    judgment_reason: str
    entry_channels: tuple[str, ...]
    impersonated_identity: str
    false_belief: tuple[str, ...]
    key_methods: tuple[str, ...]
    target_assets: tuple[str, ...]
    fraud_stage: tuple[str, ...]
    risk_signals: str
    risk_level: str
    loss_occurred: str
    loss_type: tuple[str, ...]
    prevention_advice: str
    source_name: str
    source_type: str
    collection_date: str
    is_desensitized: str
    official_category: tuple[str, ...]
    ccl2023_category: str
    custom_subcategory: str
    tags: tuple[str, ...]
    involved_platforms: tuple[str, ...]
    victim_group: str
    emergency_plan_id: str
    law_basis_ids: tuple[str, ...]
    source_links: tuple[str, ...]
    publish_date: str
    remark: str

    @property
    def content(self) -> str:
        """Canonical text payload used by embedding, retrieval, and answer context."""
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
        """Lightweight text for lexical search."""
        parts = [self.title, self.ccl2023_category, self.custom_subcategory]
        if self.tags:
            parts.extend(self.tags)
        if self.key_methods:
            parts.extend(self.key_methods)
        if self.entry_channels:
            parts.extend(self.entry_channels)
        if self.official_category:
            parts.extend(self.official_category)
        if self.victim_group:
            parts.append(self.victim_group)
        return " ".join(parts)


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
                id=_parse_text(item.get("case_id") or item.get("id")),
                title=_parse_text(item.get("title")),
                summary=_parse_text(item.get("summary")),
                nature_judgment=_parse_text(item.get("nature_judgment")),
                judgment_reason=_parse_text(item.get("judgment_reason")),
                entry_channels=_parse_multivalue(item.get("entry_channels")),
                impersonated_identity=_parse_text(item.get("impersonated_identity")),
                false_belief=_parse_multivalue(item.get("false_belief")),
                key_methods=_parse_multivalue(item.get("key_methods")),
                target_assets=_parse_multivalue(item.get("target_assets")),
                fraud_stage=_parse_multivalue(item.get("fraud_stage")),
                risk_signals=_parse_text(item.get("risk_signals")),
                risk_level=_parse_text(item.get("risk_level")),
                loss_occurred=_parse_text(item.get("loss_occurred")),
                loss_type=_parse_multivalue(item.get("loss_type")),
                prevention_advice=_parse_text(item.get("prevention_advice")),
                source_name=_parse_text(item.get("source_name")),
                source_type=_parse_text(item.get("source_type")),
                collection_date=_parse_text(item.get("collection_date")),
                is_desensitized=_parse_text(item.get("is_desensitized")),
                official_category=_parse_multivalue(item.get("official_category")),
                ccl2023_category=_parse_text(item.get("ccl2023_category")),
                custom_subcategory=_parse_text(item.get("custom_subcategory")),
                tags=_parse_multivalue(item.get("tags")),
                involved_platforms=_parse_multivalue(item.get("involved_platforms")),
                victim_group=_parse_text(item.get("victim_group")),
                emergency_plan_id=_parse_text(item.get("emergency_plan_id")),
                law_basis_ids=_parse_multivalue(item.get("law_basis_ids")),
                source_links=_parse_multivalue(item.get("source_links")),
                publish_date=_parse_text(item.get("publish_date")),
                remark=_parse_text(item.get("remark")),
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
        "summary": item.summary,
        "nature_judgment": item.nature_judgment,
        "judgment_reason": item.judgment_reason,
        "entry_channels": list(item.entry_channels),
        "impersonated_identity": item.impersonated_identity,
        "false_belief": list(item.false_belief),
        "key_methods": list(item.key_methods),
        "target_assets": list(item.target_assets),
        "fraud_stage": list(item.fraud_stage),
        "risk_signals": item.risk_signals,
        "risk_level": item.risk_level,
        "loss_occurred": item.loss_occurred,
        "loss_type": list(item.loss_type),
        "prevention_advice": item.prevention_advice,
        "source_name": item.source_name,
        "source_type": item.source_type,
        "collection_date": item.collection_date,
        "is_desensitized": item.is_desensitized,
        "official_category": list(item.official_category),
        "ccl2023_category": item.ccl2023_category,
        "custom_subcategory": item.custom_subcategory,
        "tags": list(item.tags),
        "involved_platforms": list(item.involved_platforms),
        "victim_group": item.victim_group,
        "emergency_plan_id": item.emergency_plan_id,
        "law_basis_ids": list(item.law_basis_ids),
        "source_links": list(item.source_links),
        "publish_date": item.publish_date,
        "remark": item.remark,
    }
    if include_content:
        data["content"] = item.content
    return data
