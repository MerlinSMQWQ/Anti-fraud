"""Formatting helpers for LLM contexts, candidate summaries, and keyword extraction."""

from __future__ import annotations

from typing import Any

from ..domain.dataset import normalize_text
from ..prompts import FRAUD_LABEL_MAP


def format_context_item_for_llm(item: Any) -> str:
    """Format a single context item for the LLM prompt."""
    if not isinstance(item, dict):
        return ""
    title = str(item.get("title") or "").strip()
    item_id = str(item.get("id") or "").strip()
    if not title and not item_id:
        return ""

    meta = " | ".join(
        part for part in [
            str(item.get("category") or "").strip(),
            str(item.get("level") or "").strip(),
            str(item.get("province") or "").strip(),
            str(item.get("city") or "").strip(),
            str(item.get("district") or "").strip(),
        ] if part
    )
    label = f"- [{item_id}] {title}" if item_id else f"- {title}"
    lines = [f"{label} | {meta}" if meta else label]

    for key in ("summary", "features", "history", "cultural_value", "content"):
        value = normalize_text(item.get(key) or "")
        if value:
            label_name = FRAUD_LABEL_MAP.get(key, key)
            lines.append(f"  {label_name}：{value[:240]}")

    forms = item.get("entry_channels")
    if isinstance(forms, list) and forms:
        label_name = FRAUD_LABEL_MAP.get("entry_channels", "入口渠道")
        lines.append(f"  {label_name}：{'、'.join(str(form) for form in forms[:6])}")

    return "\n".join(lines)


def items_to_llm_context(items: list[Any], total: int) -> str:
    """Format search results as compact context for the answer LLM."""
    lines = [f"从资料库中检索到 {total} 条相关反诈案例，以下是其中最相关的：\n"]
    for i, item in enumerate(items[:30], 1):
        loc = " · ".join(p for p in [item.province, item.city] if p)
        forms = "、".join(item.entry_channels) if item.entry_channels else ""
        scenarios = "、".join(item.suitable_scenarios) if item.suitable_scenarios else ""
        lines.append(
            f"{i}. [{item.id}] {_title_with_family(item)}\n"
            f"   类别：{item.category} | 级别：{item.level} | 地区：{loc}\n"
            f"   简介：{item.summary[:200]}"
        )
        if forms:
            lines.append(f"   入口渠道：{forms}")
        if scenarios:
            lines.append(f"   适合场景：{scenarios}")
        content_snippet = item.content[:300].replace("\n", " ")
        if content_snippet:
            lines.append(f"   正文：{content_snippet}")
        lines.append("")
    return "\n".join(lines)


def items_to_title_context(items: list[Any], total: int) -> str:
    """Format broad first-round candidates as title-only planning context."""
    lines = [f"第 1 轮候选标题共 {total} 项，以下为标题和基础元数据：\n"]
    for i, item in enumerate(items[:100], 1):  # INITIAL_TITLE_CONTEXT_LIMIT
        loc = " · ".join(part for part in [item.province, item.city, item.district] if part)
        forms = "、".join(item.entry_channels[:4]) if item.entry_channels else ""
        scenarios = "、".join(item.suitable_scenarios[:4]) if item.suitable_scenarios else ""
        meta = " | ".join(part for part in [item.category, item.level, loc] if part)
        extra = "；".join(part for part in [f"入口渠道：{forms}" if forms else "", f"场景：{scenarios}" if scenarios else ""] if part)
        suffix = f" | {extra}" if extra else ""
        lines.append(f"{i}. [{item.id}] {_title_with_family(item)} | {meta}{suffix}")
    return "\n".join(lines)


def context_title_keywords(items: list[Any]) -> list[str]:
    """Extract keywords from context items to expand retrieval."""
    keywords: list[str] = []
    suffixes = ("诈骗", "刷单", "返利", "冒充", "贷款", "游戏", "理财", "养老", "客服", "公检法", "征信", "虚假", "投资")
    for item in items:
        texts = [getattr(item, "family", ""), getattr(item, "title", "")]
        for text in texts:
            text = normalize_text(text)
            if not text:
                continue
            for suffix in suffixes:
                if suffix in text and suffix not in keywords:
                    keywords.append(suffix)
            if len(text) <= 4 and text not in keywords:
                keywords.append(text)
        if len(keywords) >= 6:
            break
    return keywords[:6]


def candidate_summaries_for_llm(items: list[Any], limit: int) -> str:
    """Build item summaries for LLM recommendation selection."""
    lines = []
    for item in items:
        forms = "、".join(item.entry_channels) if item.entry_channels else "无"
        location = " · ".join(p for p in [item.province, item.city] if p)
        lines.append(
            f"[{item.id}] {_title_with_family(item)} | "
            f"{item.category} | {item.level} | "
            f"{location} | 入口渠道：{forms} | "
            f"{item.summary[:80]}"
        )
    return "\n".join(lines)


# helpers from item_cards (keep them here to avoid circular import)
def _title_with_family(item: Any) -> str:
    from ..service.item_cards import _title_with_family as f
    return f(item)


def _enriched_item_card(item: Any) -> dict:
    from ..service.item_cards import _enriched_item_card as f
    return f(item)


def _source_payload(item: Any) -> dict:
    from ..service.item_cards import _source_payload as f
    return f(item)