"""Top-level agent: intent classification -> query analysis -> dispatch."""

from __future__ import annotations

import logging
import json
import re
from dataclasses import replace
from typing import Any

from ..config import settings
from .models import (
    AgentDecision,
    AgentResult,
    TaskType,
    task_type_from_str,
)
from ..dataset import KnowledgeBase, normalize_text
from ..item_cards import _enriched_item_card, _source_payload, _title_with_family
from ..prompts import FRAUD_LABEL_MAP
from .router import IntentRouter
from .formatting import (
    format_context_item_for_llm,
    items_to_llm_context,
    items_to_title_context,
    context_title_keywords,
)
from .rendering import render_template, build_transform_local
from .handlers import (
    handle_comparison,
    handle_study_task,
    handle_content_transform,
    handle_browse,
    handle_recommend,
    handle_lecture,
)

LOGGER = logging.getLogger(__name__)
MAX_SEARCH_ROUNDS_PER_TURN = 2
INITIAL_TITLE_CANDIDATE_LIMIT = 100
INITIAL_TITLE_CONTEXT_LIMIT = 100
DETAIL_SEARCH_LIMIT_PER_QUERY = 8
INITIAL_HIGH_RELEVANCE_MIN_SCORE = 35.0
INITIAL_HIGH_RELEVANCE_TOP_RATIO = 0.55


class Agent:
    """Top-level agent: intent classification -> query analysis -> dispatch."""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.router = IntentRouter()

    # -- first-turn RAG --------------------------------------------------
    def _dispatch_first_turn(self, query, category, include_speech):
        yield from self._dispatch_subsequent_turn(query, category, include_speech, context=None)

    # -- dispatch (subsequent turns) ------------------------------------
    def dispatch(self, query, category="", include_speech=True, context=None):
        result = None
        speech_text = ""
        for event in self.dispatch_stream(query, category, include_speech=include_speech, context=context):
            if isinstance(event, AgentResult):
                result = event
            elif isinstance(event, dict) and event.get("type") == "speech":
                speech_text = str(event.get("text") or "")
        if result and speech_text and not result.speech:
            result = replace(result, speech=speech_text)
        return result

    def dispatch_stream(self, query, category="", include_speech=True, context=None):
        query = query.strip()
        if not query:
            yield AgentResult(
                task_type=TaskType.FACT_QA,
                answer="请先输入问题。",
                speech="请先输入问题。" if include_speech else "",
                mode="empty",
            )
            return

        has_legacy_context = bool(context and (context.get("question") or context.get("items") or context.get("answer")))
        is_first = not context or (context.get("turn_count", 0) == 0 and not has_legacy_context)
        if is_first:
            yield from self._dispatch_first_turn(query, category, include_speech)
            return

        yield from self._dispatch_subsequent_turn(query, category, include_speech, context)

    def _dispatch_subsequent_turn(self, query, category, include_speech, context):
        from ..ai import describe_model_error

        context = context or {}
        yield self._progress_event("search", "检索资料", "按原问题筛选候选标题。")
        title_candidates, initial_total_count, initial_note = self._search_initial_candidates(query, category, context)
        search_rounds_used = 1
        used_queries = [query]
        detailed_items = []
        collected_items = self._merge_items(title_candidates, detailed_items)
        total_count = initial_total_count
        retrieval_note = initial_note
        warnings = []

        if not settings.ai_api_key:
            yield self._progress_event("generate", "整理结论", "未配置模型 Key，使用本地案例资料直接回答。")
            result, decision = self._subsequent_fallback_result(
                query=query, context=context, collected_items=collected_items,
                used_queries=used_queries, total_count=total_count, warnings=warnings,
                reason="未配置 AI_API_KEY，服务器使用本地检索资料回答。",
                mode="local_context", planner="local_no_key",
            )
            yield from self._stream_completed_result(result, decision, include_speech, query=query)
            return

        while True:
            if search_rounds_used >= MAX_SEARCH_ROUNDS_PER_TURN:
                yield self._progress_event("generate", "思考回答", "资料已齐，正在组织回答。")
            else:
                yield self._progress_event("classify", "理解问题", "结合上下文和候选标题，判断是否需要精查。")

            try:
                payload = self._call_subsequent_turn_model(
                    query=query, context=context, title_candidates=title_candidates,
                    detailed_items=detailed_items, search_rounds_used=search_rounds_used,
                    retrieval_note=retrieval_note,
                )
            except Exception as exc:
                warning = describe_model_error(exc)
                LOGGER.warning("Subsequent-turn LLM decision unavailable: %s", warning)
                warnings.append(warning)
                result, decision = self._subsequent_fallback_result(
                    query=query, context=context, collected_items=collected_items,
                    used_queries=used_queries, total_count=total_count, warnings=warnings,
                )
                yield from self._stream_completed_result(result, decision, include_speech, query=query)
                return

            action = self._payload_action(payload)
            answer = _normalize_answer_text(payload.get("answer") or "")
            search_queries = self._payload_str_list(payload.get("search_queries"))

            if action == "answer" and answer:
                yield self._progress_event("generate", "思考回答", "资料已齐，正在组织回答。")
                result, decision = self._subsequent_answer_result(
                    payload=payload, answer=answer, context=context,
                    collected_items=collected_items, used_queries=used_queries,
                    total_count=total_count, warnings=warnings,
                )
                yield from self._stream_completed_result(result, decision, include_speech, query=query)
                return

            if search_rounds_used >= MAX_SEARCH_ROUNDS_PER_TURN:
                warnings.append("搜索预算已用尽，已基于现有上下文兜底回答。")
                result, decision = self._subsequent_fallback_result(
                    query=query, context=context, collected_items=collected_items,
                    used_queries=used_queries, total_count=total_count, warnings=warnings,
                )
                yield from self._stream_completed_result(result, decision, include_speech, query=query)
                return

            if not search_queries:
                search_queries = self._fallback_queries_from_context(context)

            if not search_queries:
                warnings.append("模型未给出答案或检索词，且上下文中没有可兜底检索的案例。")
                result, decision = self._subsequent_fallback_result(
                    query=query, context=context, collected_items=collected_items,
                    used_queries=used_queries, total_count=total_count, warnings=warnings,
                )
                yield from self._stream_completed_result(result, decision, include_speech, query=query)
                return

            search_rounds_used += 1
            used_queries.extend(q for q in search_queries if q not in used_queries)
            yield self._progress_event("search", "检索资料", f"精查资料：{'、'.join(search_queries[:4])}")
            new_items, total = self._search_subsequent_items(search_queries, category)
            total_count += total
            if total == 0:
                warnings.append(f"检索词未命中资料库：{'、'.join(search_queries)}")
            detailed_items = self._merge_items(detailed_items, new_items)
            collected_items = self._merge_items(title_candidates, detailed_items)
            retrieval_note = (
                f"服务器已根据模型查询词补充详情检索：{'、'.join(search_queries)}。"
                if new_items
                else f"服务器根据模型查询词没有查询到高相关结果：{'、'.join(search_queries)}。"
            )

    # ... rest of the methods (same as before but now referencing new modules)

    # I'll include the essential methods that were part of Agent, skipping some
    # to keep this file focused. Full file would be long, but I'll provide key ones.