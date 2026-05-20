"""Flask web app for the anti-fraud case knowledge base."""

import json
import re

from flask import Flask, Response, abort, jsonify, render_template, request, send_file, stream_with_context

from .. import __version__
from ..agent import Agent, AgentResult, task_type_label
from ..config import settings
from ..service.conversation import store as conv_store
from ..domain.dataset import get_knowledge_base, item_to_dict, normalize_text
from ..service.scenario_evidence import scenario_is_hard_match, scenario_match_score
from ..service.search import search_items
from ..service.volc_tts import (
    openai_tts_available,
    server_tts_available,
    server_tts_engine,
    stream_speech_audio,
    synthesize_speech_to_file,
    valid_tts_filename,
    volc_tts_available,
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../../../templates",
        static_folder="../../../static",
    )

    app.logger.info(
        "TTS: engine=%s volc=%s openai=%s",
        server_tts_engine(),
        volc_tts_available(),
        openai_tts_available(),
    )

    @app.after_request
    def prevent_dev_cache(response):
        if request.path == "/" or request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/")
    def index():
        response = app.make_response(render_template("index.html"))
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/api/meta")
    def meta():
        kb = get_knowledge_base()
        return jsonify({
            "app_version": __version__,
            "schema_version": kb.schema_version,
            "generated_at": kb.generated_at,
            "source": kb.source,
            "item_count": len(kb.items),
            "category_count": len(kb.categories),
        })

    @app.get("/api/categories")
    def categories():
        kb = get_knowledge_base()
        return jsonify([
            {"id": category.id, "name": category.name, "item_count": category.item_count}
            for category in kb.categories
        ])

    @app.get("/api/items")
    def items():
        kb = get_knowledge_base()
        query = request.args.get("q", "")
        category = request.args.get("category", "")
        risk_level = request.args.get("risk_level", "") or request.args.get("level", "")
        keywords = request.args.get("keywords", "")
        limit = max(int(request.args.get("limit", "30")), 1)
        offset = max(int(request.args.get("offset", "0")), 0)

        if request.args.get("stream") == "1":
            return _stream_items(kb, query, category, risk_level, keywords, limit, offset)

        result, total, _structured = _search_items_for_api(
            kb,
            query=query,
            category=category,
            risk_level=risk_level,
            keywords=keywords,
            limit=limit,
            offset=offset,
        )
        return jsonify({
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_item_payload(item) for item in result],
        })

    @app.get("/api/items/<item_id>")
    def item_detail(item_id: str):
        kb = get_knowledge_base()
        item = kb.get(item_id)
        if item is None:
            abort(404)
        return jsonify(_item_payload(item, include_content=True))

    @app.post("/api/ask")
    def ask():
        kb = get_knowledge_base()
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question") or "")
        category = str(payload.get("category") or "")
        session_id = str(payload.get("session_id") or "")
        voice_enabled = payload.get("voice_enabled", True)
        if isinstance(voice_enabled, str):
            include_speech = voice_enabled.lower() not in {"0", "false", "no", "off"}
        else:
            include_speech = bool(voice_enabled)

        # Auto-generate session_id for new sessions
        import uuid as _uuid
        if not session_id:
            session_id = _uuid.uuid4().hex[:12]
        first_turn = conv_store.is_first_turn(session_id)
        context = conv_store.format_context(session_id) if not first_turn else None
        if context is None and isinstance(payload.get("context"), dict):
            context = payload.get("context")

        def generate():
            agent = Agent(kb)
            for event in agent.dispatch_stream(
                query=question,
                category=category,
                include_speech=include_speech,
                context=context,
            ):
                if isinstance(event, AgentResult):
                    speech_audio = _speech_audio_hint(event.speech) if include_speech else {}
                    # Extract item context for conversation storage.
                    item_titles = []
                    items_full = []
                    seen_item_ids = set()
                    for it in (event.items or []):
                        if not isinstance(it, dict):
                            continue
                        title = str(it.get("title") or "").strip()
                        if title and title not in item_titles:
                            item_titles.append(title)
                        item_id = str(it.get("id") or "").strip()
                        if item_id and item_id not in seen_item_ids:
                            item = kb.get(item_id)
                            if item is not None:
                                items_full.append(item_to_dict(item, include_content=True))
                                seen_item_ids.add(item_id)
                        elif not item_id and title:
                            items_full.append(dict(it))
                    # Save turn
                    conv_store.add_turn(
                        session_id=session_id,
                        query=question,
                        answer=event.answer or "",
                        item_titles=item_titles,
                        items_full=items_full,
                    )
                    result_payload = {
                        'type': 'result',
                        'session_id': session_id,
                        'answer': event.answer,
                        'speech': event.speech,
                        **speech_audio,
                        'mode': event.mode,
                        'task_type': event.task_type.value,
                        'task_label': task_type_label(event.task_type),
                        'confidence': event.confidence,
                        'sources': event.sources,
                        'items': event.items,
                        'evidence': event.evidence,
                        'selection_reason': event.selection_reason,
                        'warnings': event.warnings,
                        'total_count': event.total_count,
                        'decision': event.decision,
                    }
                    yield f"data: {json.dumps(result_payload, ensure_ascii=False)}\n\n"
                elif isinstance(event, dict) and event.get("type") == "speech":
                    speech_text = str(event.get("text") or "")
                    speech_audio = _speech_audio_hint(speech_text) if include_speech else {}
                    speech_payload = {
                        'type': 'speech',
                        'session_id': session_id,
                        'text': speech_text,
                        **speech_audio,
                    }
                    app.logger.info(
                        "Speech event: engine=%s text_len=%d",
                        speech_payload.get("speech_engine", "browser"),
                        len(speech_text),
                    )
                    yield f"data: {json.dumps(speech_payload, ensure_ascii=False)}\n\n"
                else:
                    evt = dict(event)
                    evt['session_id'] = session_id
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream")

    @app.post("/api/tts")
    def create_tts_audio():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return jsonify({"speech_engine": "browser", "error": "empty_text"})
        return jsonify(_speech_audio_payload(text))

    @app.get("/api/tts/stream")
    def stream_tts_audio():
        text = str(request.args.get("text") or "").strip()
        audio_stream = stream_speech_audio(text)
        if audio_stream is None:
            abort(503)
        return Response(
            stream_with_context(audio_stream),
            mimetype=_tts_mime_type(f"audio.{_tts_extension()}"),
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/tts/<filename>")
    def tts_audio(filename: str):
        if not valid_tts_filename(filename):
            abort(404)
        path = settings.tts_cache_dir / filename
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype=_tts_mime_type(filename), conditional=True, max_age=3600)

    return app


def _speech_audio_hint(speech: str) -> dict:
    lang = _speech_language(speech)
    if speech and server_tts_available():
        return {
            "speech_engine": server_tts_engine(),
            "speech_audio_pending": True,
            "speech_lang": lang,
        }
    return {
        "speech_engine": "browser",
        "speech_lang": lang,
    }


def _speech_language(speech: str) -> str:
    text = str(speech or "")
    latin_count = len(re.findall(r"[A-Za-z]", text))
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    if latin_count >= 24 and latin_count > chinese_count * 2:
        return "en-US"
    return "zh-CN"


def _speech_audio_payload(speech: str) -> dict:
    try:
        audio = synthesize_speech_to_file(speech)
    except Exception:
        return {"speech_engine": "browser"}
    if audio is None:
        return {"speech_engine": "browser"}
    return {
        "speech_audio_url": f"/api/tts/{audio.path.name}",
        "speech_mime_type": audio.mime_type,
        "speech_engine": audio.engine,
    }


def _tts_mime_type(filename: str) -> str:
    if filename.endswith(".mp3"):
        return "audio/mpeg"
    if filename.endswith(".ogg") or filename.endswith(".opus"):
        return "audio/ogg"
    if filename.endswith(".wav"):
        return "audio/wav"
    return "application/octet-stream"


def _tts_extension() -> str:
    from ..config import settings

    return settings.volc_tts_encoding.lower()


def _stream_items(
    kb, query: str, category: str, risk_level: str,
    keywords: str, limit: int, offset: int,
):
    """SSE helper: stream unified search results."""

    def generate():
        # Establish SSE connection to force first chunk flush
        yield ":ready\n\n"

        result, total, _structured = _search_items_for_api(
            kb, query=query, category=category,
            risk_level=risk_level, keywords=keywords,
            limit=limit, offset=offset,
        )
        yield _sse_event({
            "phase": "results",
            "total": total,
            "items": [_item_payload(item) for item in result],
        })

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _search_items_for_api(
    kb,
    query: str = "",
    category: str = "",
    risk_level: str = "",
    keywords: str = "",
    limit: int = 30,
    offset: int = 0,
):
    structured = _structured_search_parts(query, risk_level)
    scenario = structured["scenario"]
    derived_level = risk_level or structured["risk_level"]

    if scenario or (derived_level and not risk_level):
        result, total = _search_structured_items(
            kb,
            query=structured["query"],
            category=category,
            risk_level=derived_level,
            keywords=keywords,
            scenario=scenario,
            limit=limit,
            offset=offset,
        )
        return result, total, True

    result, total = search_items(
        kb,
        query=query,
        category=category,
        risk_level=risk_level,
        keywords=keywords,
        limit=limit,
        offset=offset,
    )
    return result, total, False


def _structured_search_parts(query: str, risk_level: str) -> dict[str, str]:
    text = normalize_text(query)
    scenario = _query_scenario(text)
    derived_level = "" if risk_level else _query_level(text)
    cleaned = _clean_structured_query(text, derived_level, scenario)
    return {
        "risk_level": derived_level,
        "scenario": scenario,
        "query": cleaned,
    }


def _search_structured_items(
    kb,
    query: str,
    category: str,
    risk_level: str,
    keywords: str,
    scenario: str,
    limit: int,
    offset: int,
):
    category = normalize_text(category)
    risk_level = normalize_text(risk_level)
    query = " ".join(part for part in [normalize_text(keywords), normalize_text(query)] if part)

    candidates = []
    for item in kb.items:
        if category and item.ccl2023_category != category:
            continue
        if risk_level and item.risk_level != risk_level:
            continue
        if scenario and not _item_matches_scenario(item, scenario):
            continue
        candidates.append(item)

    if query:
        result, _ = search_items(
            _FilteredKnowledgeBase(kb, candidates),
            query=query,
            limit=len(candidates) or limit,
        )
        return result[offset : offset + limit], len(result)

    scored = sorted(
        candidates,
        key=lambda item: (-_structured_item_score(item, scenario), item.ccl2023_category, item.title),
    )
    return scored[offset : offset + limit], len(scored)


class _FilteredKnowledgeBase:
    def __init__(self, kb, items):
        self.items = items
        self.generated_at = kb.generated_at

    def get(self, item_id: str):
        return next((item for item in self.items if item.id == item_id), None)


def _query_level(query: str) -> str:
    if "极高" in query:
        return "极高"
    if "高风险" in query or ("高" in query and "风险" in query):
        return "高"
    if "中风险" in query or ("中" in query and "风险" in query):
        return "中"
    return ""


def _query_scenario(query: str) -> str:
    if "老年" in query or "老人" in query or "养老" in query:
        return "老年防骗"
    if "社区" in query or "居民" in query:
        return "社区宣传"
    if "校园" in query or "学校" in query or "学生" in query or "班会" in query:
        return "校园宣讲"
    if "企业" in query or "财务" in query or "老板" in query or "领导" in query:
        return "企业培训"
    if "短视频" in query or "海报" in query or "推文" in query or "口播" in query:
        return "新媒体提醒"
    if "案例" in query or "复盘" in query or "拆解" in query:
        return "以案说法"
    return ""


def _clean_structured_query(query: str, risk_level: str, scenario: str) -> str:
    cleaned = query
    if risk_level:
        cleaned = cleaned.replace(risk_level, " ")
    scenario_terms = {
        "社区宣传": ("社区宣传", "社区", "居民", "适合"),
        "校园宣讲": ("校园宣讲", "校园", "学校", "学生", "班会", "适合"),
        "老年防骗": ("老年防骗", "老人", "老年", "养老", "适合"),
        "企业培训": ("企业培训", "企业", "财务", "老板", "领导", "适合"),
        "新媒体提醒": ("新媒体提醒", "短视频", "海报", "推文", "口播", "适合"),
        "以案说法": ("以案说法", "案例", "复盘", "拆解", "适合"),
    }
    for term in scenario_terms.get(scenario, ()):
        cleaned = cleaned.replace(term, " ")
    for term in ("反诈", "诈骗", "骗局", "案例", "推荐", "哪些", "有哪些", "几个", "找", "筛选", "适合"):
        cleaned = cleaned.replace(term, " ")
    return normalize_text(cleaned)


def _item_matches_scenario(item, scenario: str) -> bool:
    return scenario_is_hard_match(item, scenario)


def _structured_item_score(item, scenario: str) -> int:
    score = 0
    score += scenario_match_score(item, scenario)
    if item.risk_level == "极高":
        score += 4
    elif item.risk_level == "高":
        score += 3
    elif item.risk_level == "中":
        score += 2
    score += min(len(item.entry_channels), 3)
    return score


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _item_payload(item, include_content: bool = False) -> dict:
    return item_to_dict(item, include_content=include_content)


def main() -> None:
    create_app().run(host=settings.host, port=settings.port, debug=settings.debug, threaded=True)


if __name__ == "__main__":
    main()
