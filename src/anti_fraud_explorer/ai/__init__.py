"""Retrieval-augmented question answering over the anti-fraud dataset."""

from ..ai.client import (
    build_messages,
    call_chat_model,
    call_model_with_messages,
    call_spoken_model,
    describe_model_error,
)
from ..ai.context import (
    build_context,
    clean_knowledge_text,
    extract_structured_field,
    item_context_text,
)
from ..ai.qa import (
    Answer,
    answer_question,
    build_local_answer,
    direct_item_matches,
    fact_question_sources,
    source_payload,
    summarize_snippet,
)
from ..ai.spoken import (
    build_spoken_prompt,
    build_spoken_answer,
)

__all__ = [
    "Answer",
    "answer_question",
    "build_context",
    "build_local_answer",
    "build_messages",
    "build_spoken_prompt",
    "build_spoken_answer",
    "call_chat_model",
    "call_model_with_messages",
    "call_spoken_model",
    "clean_knowledge_text",
    "describe_model_error",
    "direct_item_matches",
    "extract_structured_field",
    "fact_question_sources",
    "item_context_text",
    "source_payload",
    "summarize_snippet",
]
