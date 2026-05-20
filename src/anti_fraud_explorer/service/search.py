"""Small dependency-free lexical search for the normalized dataset."""

import logging
import re
from collections.abc import Iterable
from functools import lru_cache

from ..config import settings
from ..domain.dataset import CaseItem, KnowledgeBase
from ..text import normalize_text


LOGGER = logging.getLogger(__name__)
HYBRID_LEXICAL_CANDIDATES = 80
HYBRID_SEMANTIC_CANDIDATES = 80
RRF_K = 60
LEXICAL_RANK_WEIGHT = 1.3
SEMANTIC_RANK_WEIGHT = 1.35
LEXICAL_MIN_SCORE = 10  # minimum score for an item to count as a lexical match
HYBRID_MIN_SCORE = 0.015  # RRF-based scores are small; this keeps weak tail matches out.

# Pinyin fuzzy search constants
_PINYIN_MIN_QUERY_LEN = 2  # minimum query chars to try pinyin matching
_PINYIN_MATCH_BONUS = 0.3  # score for pinyin-exact match
_SEARCH_TRAILING_PUNCTUATION = "？?！!。.，,、 \t\r\n"


@lru_cache(maxsize=1)
def _build_pinyin_index(kb_hash: str) -> dict[str, list[str]]:
    """Build a pinyin-to-item-id index for all anti-fraud case items.

    Converts each item's title and family to pinyin and maps the
    resulting pinyin strings to item IDs for homophone fuzzy matching.
    kb_hash is a cache key derived from the dataset for thread safety.
    """
    try:
        from pypinyin import lazy_pinyin  # noqa: PLC0415 - optional dependency
        # We need kb inside the function but want the signature to accept
        # a cache key string.  Pull the singleton via dataset.
        from ..domain.dataset import load_dataset

        kb = load_dataset()
        index: dict[str, list[str]] = {}
        for item in kb.items:
            texts = [item.title]
            if item.ccl2023_category:
                texts.append(item.ccl2023_category)
            for text in texts:
                py = "".join(lazy_pinyin(text))
                py_compact = py.replace(" ", "")
                if py_compact:
                    index.setdefault(py_compact, []).append(item.id)
        LOGGER.info("Pinyin index built: %d entries", len(index))
        return index
    except ImportError:
        LOGGER.debug("pypinyin not installed, pinyin fuzzy search disabled")
        return {}


def search_items_pinyin(
    kb: KnowledgeBase,
    query: str,
) -> list[CaseItem]:
    """Try pinyin-based homophone matching as a fallback.

    Converts the query characters to pinyin and looks for items whose
    title/family pinyin matches.  Returns [] when pypinyin is unavailable
    or no matches are found.
    """
    if not query or len(query) < _PINYIN_MIN_QUERY_LEN:
        return []

    index = _build_pinyin_index(kb.generated_at or str(len(kb.items)))
    if not index:
        return []

    try:
        from pypinyin import lazy_pinyin  # noqa: PLC0415 - optional dependency

        query_py = "".join(lazy_pinyin(query))
    except ImportError:
        return []

    matched_ids: list[str] = []

    # 1) Exact full-pinyin match
    if query_py in index:
        matched_ids.extend(index[query_py])

    # 2) Partial: query-pinyin and title-pinyin may contain each other.
    for py, ids in index.items():
        if py == query_py:
            continue
        if query_py in py or _is_substantial_pinyin_part(py, query_py):
            matched_ids.extend(ids)

    # Deduplicate and resolve
    seen: set[str] = set()
    result: list[CaseItem] = []
    for item_id in matched_ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        item = kb.get(item_id)
        if item is not None:
            result.append(item)

    return result


def _is_substantial_pinyin_part(candidate_py: str, query_py: str) -> bool:
    """Allow contained pinyin only when it covers a real chunk of the query."""
    if candidate_py not in query_py:
        return False
    if len(candidate_py) < 6:
        return False
    return len(candidate_py) >= len(query_py) * 0.45


def tokenize(query: str) -> list[str]:
    query = normalize_search_query(query)
    if not query:
        return []
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query)
    if len(tokens) == 1:
        text = tokens[0]
        if len(text) > 2:
            tokens.extend(text[i : i + 2] for i in range(len(text) - 1))
    return list(dict.fromkeys(tokens))


def normalize_search_query(query: str) -> str:
    """Normalize a raw search string without trying to interpret user intent."""
    text = normalize_text(query).lower().strip(_SEARCH_TRAILING_PUNCTUATION)
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip(_SEARCH_TRAILING_PUNCTUATION)


def search_items(
    kb: KnowledgeBase,
    query: str = "",
    category: str = "",
    risk_level: str = "",
    keywords: str = "",
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[CaseItem], int]:
    query = normalize_text(query)
    category = normalize_text(category)
    risk_level = normalize_text(risk_level)
    keywords = normalize_text(keywords)
    candidates: Iterable[CaseItem] = kb.items

    if category:
        candidates = (item for item in candidates if item.ccl2023_category == category)
    if risk_level:
        candidates = (item for item in candidates if item.risk_level == risk_level)
    if keywords:
        query = f"{keywords} {query}".strip()

    candidates = list(candidates)

    if not query:
        result = sorted(candidates, key=lambda item: (item.ccl2023_category, item.title))
        return result[offset : offset + limit], len(result)

    search_query = normalize_search_query(query)
    tokens = tokenize(search_query)
    lowered_query = search_query or query.lower()
    ranked = rank_lexical(candidates, lowered_query, tokens)

    using_hybrid = False
    if settings.search_use_embedding:
        try:
            ranked = rank_hybrid(kb, candidates, lowered_query, tokens)
            using_hybrid = True
        except Exception:  # noqa: BLE001 - semantic retrieval should degrade to lexical search.
            pass

    min_score = HYBRID_MIN_SCORE if using_hybrid else LEXICAL_MIN_SCORE
    result = [item for score, item in ranked if score >= min_score]
    result = prepend_pinyin_matches(kb, result, search_query or query, candidates)
    return result[offset : offset + limit], len(result)


def prepend_pinyin_matches(
    kb: KnowledgeBase,
    ranked_items: list[CaseItem],
    query: str,
    candidates: list[CaseItem],
) -> list[CaseItem]:
    """Place homophone title matches before normal ranked results.

    Pinyin matching is intentionally a lexical supplement: it helps misspelled
    or same-sound Chinese queries such as "落山" find "罗山", without feeding
    those same-sound tokens into embedding search.
    """
    if not query or len(query) < _PINYIN_MIN_QUERY_LEN:
        return ranked_items
    if has_title_substring_match(ranked_items, query):
        return ranked_items
    if has_location_token_match(ranked_items, query):
        return ranked_items

    candidate_ids = {item.id for item in candidates}
    pinyin_results = [
        item for item in search_items_pinyin(kb, query)
        if item.id in candidate_ids
    ]
    if not pinyin_results:
        return ranked_items

    pinyin_ids = {item.id for item in pinyin_results}
    return pinyin_results + [item for item in ranked_items if item.id not in pinyin_ids]


def has_title_substring_match(items: list[CaseItem], query: str) -> bool:
    lowered_query = query.lower()
    return any(item.title and item.title.lower() in lowered_query for item in items)


def has_location_token_match(items: list[CaseItem], query: str) -> bool:
    # Location fields are no longer extracted in v3 schema
    return False


def rank_lexical(
    candidates: Iterable[CaseItem],
    lowered_query: str,
    tokens: list[str],
) -> list[tuple[float, CaseItem]]:
    ranked: list[tuple[float, CaseItem]] = []

    for item in candidates:
        score = score_item(item, lowered_query, tokens)
        if score > 0:
            ranked.append((score, item))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].title))
    return ranked


def rank_hybrid(
    kb: KnowledgeBase,
    candidates: list[CaseItem],
    lowered_query: str,
    tokens: list[str],
) -> list[tuple[float, CaseItem]]:
    from .embeddings import embedding_scores

    semantic_scores = embedding_scores(kb, lowered_query, candidates, min_score=0.0)
    lexical_ranked = rank_lexical(candidates, lowered_query, tokens)
    lexical_scores = {item.id: score for score, item in lexical_ranked}
    items_by_id = {item.id: item for item in candidates}
    candidate_ids: set[str] = set()
    rank_scores: dict[str, float] = {}

    add_rank_signal(
        rank_scores,
        lexical_ranked[:HYBRID_LEXICAL_CANDIDATES],
        LEXICAL_RANK_WEIGHT,
    )
    candidate_ids.update(item.id for _, item in lexical_ranked[:HYBRID_LEXICAL_CANDIDATES])

    semantic_ranked = [
        (score, item)
        for item_id, score in semantic_scores.items()
        if (item := items_by_id.get(item_id)) is not None
    ]
    semantic_ranked.sort(key=lambda pair: (-pair[0], pair[1].title))
    add_rank_signal(
        rank_scores,
        semantic_ranked[:HYBRID_SEMANTIC_CANDIDATES],
        SEMANTIC_RANK_WEIGHT,
    )
    candidate_ids.update(item.id for _, item in semantic_ranked[:HYBRID_SEMANTIC_CANDIDATES])

    for item in candidates:
        if strong_match_bonus(item, lowered_query, tokens) > 0:
            candidate_ids.add(item.id)

    ranked: list[tuple[float, CaseItem]] = []
    for item_id in candidate_ids:
        item = items_by_id[item_id]
        score = rank_scores.get(item_id, 0.0)
        score += strong_match_bonus(item, lowered_query, tokens)
        score += lexical_tiebreak(lexical_scores.get(item_id, 0.0))
        ranked.append((score, item))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].title))
    return ranked


def add_rank_signal(
    rank_scores: dict[str, float],
    ranked: list[tuple[float, CaseItem]],
    weight: float,
) -> None:
    for rank, (_, item) in enumerate(ranked, start=1):
        rank_scores[item.id] = rank_scores.get(item.id, 0.0) + weight / (RRF_K + rank)


def strong_match_bonus(item: CaseItem, query: str, tokens: list[str]) -> float:
    if not query:
        return 0.0

    title = item.title.lower()
    family_cat = item.ccl2023_category.lower()
    bonus = 0.0

    if query == title:
        bonus += 0.7
    elif query in title:
        bonus += 0.35

    if query == family_cat:
        bonus += 0.4
    elif family_cat and query in family_cat:
        bonus += 0.15

    for token in tokens:
        if not token:
            continue
        if token == title:
            bonus += 0.06
        elif token in title:
            bonus += 0.004
        if token == family_cat:
            bonus += 0.10
        elif family_cat and token in family_cat:
            bonus += 0.005

    return bonus


def lexical_tiebreak(score: float) -> float:
    if score <= 0:
        return 0.0
    return min(score, 100.0) / 10000.0


def score_item(item: CaseItem, query: str, tokens: list[str]) -> float:
    title = item.title.lower()
    family_cat = item.ccl2023_category.lower()
    summary = item.summary.lower()
    content = item.content.lower()
    search_text = item.search_text.lower()

    score = 0.0
    if query == title:
        score += 100
    if query and query in title:
        score += 40
    if query and query in family_cat:
        score += 30
    if query and query in summary:
        score += 10
    if query and query in content:
        score += 12

    for token in tokens:
        if token in title:
            score += 12
        if token in family_cat:
            score += 10
        if token in summary:
            score += 3
        if token in search_text:
            score += 1

    return score
