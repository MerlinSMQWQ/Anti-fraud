"""Speech processing and message building for the anti-fraud AI."""

from __future__ import annotations

import logging
import re

from ..config import settings
from ..dataset import CaseItem, normalize_text
from ..ai.context import build_context, extract_structured_field, clean_knowledge_text
from ..ai.prompts import get_emoji_re, qa_system_prompt, speech_system_prompt


LOGGER = logging.getLogger(__name__)


def build_messages(question: str, sources: list[CaseItem]) -> list[dict[str, str]]:
    context = build_context(sources, settings.ai_max_context_chars)
    return [
        {
            "role": "system",
            "content": qa_system_prompt(),
        },
        {
            "role": "user",
            "content": f"问题：{question}\n\n资料：\n{context}",
        },
    ]


def build_speech_messages(
    answer: str,
    question: str = "",
    sources: list[CaseItem] | None = None,
    max_chars: int = 1800,
) -> list[dict[str, str]]:
    source_titles = "、".join(item.title for item in (sources or [])[:3]) or "无"
    return [
        {
            "role": "system",
            "content": speech_system_prompt(),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{question or '未提供'}\n"
                f"相关资料标题：{source_titles}\n"
                f"展示版回答：\n{answer}\n\n"
                f"如果它无需修改，请直接输出原文；如果需要修改，请输出润色后的文本。"
                f"最终文本应尽量接近展示版回答的内容和长度；只有超过 {max_chars} 字时才适度压缩。"
            ),
        },
    ]


def build_spoken_answer(
    answer: str,
    question: str = "",
    sources: list[CaseItem] | None = None,
    prefer_model: bool = True,
    max_chars: int = 1800,
) -> str:
    from ..ai.client import call_speech_model, describe_model_error

    if prefer_model and settings.ai_api_key:
        try:
            spoken = call_speech_model(answer, question=question, sources=sources or [], max_chars=max_chars)
            spoken = clean_spoken_output(spoken, max_chars=max_chars)
            if spoken:
                return spoken
        except Exception as exc:  # noqa: BLE001 - speech rewrite should never break the main answer path.
            LOGGER.warning("Speech rewrite unavailable: %s", describe_model_error(exc))

    return clean_spoken_output(
        build_speech_text(answer, question=question, sources=sources or [], max_chars=max_chars),
        max_chars=max_chars,
    )


def build_speech_text(
    answer: str,
    question: str = "",
    sources: list[CaseItem] | None = None,
    max_chars: int = 1800,
) -> str:
    spoken = build_answer_speech(answer, max_chars=max_chars)
    if spoken:
        return spoken

    return build_source_speech(question, sources or [], max_chars=max_chars)


def build_answer_speech(answer: str, max_chars: int = 1800) -> str:
    text = str(answer or "")
    text = remove_speech_symbols(text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    spoken_lines = []
    active_section = ""
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        section = speech_section_heading(line)
        if section:
            active_section = section
            continue

        converted = speech_line(line, active_section)
        if converted:
            spoken_lines.append(converted)
            active_section = ""

    text = "。".join(spoken_lines)
    text = re.sub(r"[>#*_~|]+", " ", text)
    text = remove_speech_symbols(text)
    text = re.sub(r"[，、；：]\s*([。！？])", r"\1", text)
    text = re.sub(r"。{2,}", "。", text)
    text = normalize_text(text)
    text = text.replace("。。", "。").strip(" 。")
    if len(text) > max_chars:
        boundary = max(text.rfind(mark, 0, max_chars) for mark in "。！？")
        if boundary < max_chars // 2:
            boundary = max_chars
        text = text[: boundary + 1].rstrip("，、；： ")
        if text and text[-1] not in "。！？":
            text += "。"
    return text


def clean_spoken_output(text: str, max_chars: int = 1800) -> str:
    text = remove_speech_symbols(text)
    text = re.sub(r"^\s*(?:无需修改|需要修改|润色后|播报稿|最终播报文本)\s*[:：]\s*", "", text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[>#*_~|]+", " ", text)
    text = normalize_text(text)
    text = re.sub(r"[，、；：]\s*([。！？])", r"\1", text)
    text = re.sub(r"。{2,}", "。", text).strip()
    if len(text) > max_chars:
        boundary = max(text.rfind(mark, 0, max_chars) for mark in "。！？")
        if boundary < max_chars // 2:
            boundary = max_chars
        text = text[: boundary + 1].rstrip("，、；： ")
        if text and text[-1] not in "。！？":
            text += "。"
    return text


def remove_speech_symbols(text: str) -> str:
    _EMOJI_RE = get_emoji_re()
    text = _EMOJI_RE.sub(" ", str(text or ""))
    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def speech_section_heading(line: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip()
    text = re.sub(r"^\s*[-*+]\s+", "", text).strip()
    text = text.strip(" ：:。；;")
    headings = {
        "场景简述",
        "诈骗手法",
        "关键手法",
        "风险信号",
        "风险等级",
        "防范建议",
        "受害群体",
    }
    return text if text in headings else ""


def speech_line(line: str, section: str = "") -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip()
    line = re.sub(r"^\s*[-*+]\s+", "", line).strip()
    line = re.sub(r"^\s*(\d+)[.)、]\s+", r"第\1点，", line).strip()
    line = re.sub(r"^\s*([一二三四五六七八九十]+)、\s*", r"第\1部分，", line).strip()
    line = line.strip("。；; ")
    if not line:
        return ""

    if line in {"基本信息", "相关信息", "关键信息", "总结"}:
        return ""
    if is_admin_sentence(line):
        return ""

    label_match = re.match(r"^([^：:]{2,12})[：:]\\s*(.+)$", line)
    if label_match:
        label = label_match.group(1).strip()
        body = clean_speech_body(label_match.group(2).strip())
        transitions = {
            "场景简述": "案情是这样的，{body}",
            "诈骗手法": "在诈骗手法上，{body}",
            "关键手法": "在关键手法上，{body}",
            "风险信号": "从风险信号看，{body}",
            "风险等级": "风险等级属于{body}",
            "防范建议": "在防范建议上，{body}",
            "受害群体": "受害群体主要是{body}",
            "类别": "它属于{body}",
        }
        template = transitions.get(label)
        if template:
            line = template.format(body=body)
        else:
            line = f"{label}，{body}"
    else:
        line = clean_speech_body(line)

    if section:
        line = apply_section_intro(section, line)

    line = re.sub(r"[，、；：]\s*([。！？])", r"\1", line)
    return line.strip(" 。")


def apply_section_intro(section: str, line: str) -> str:
    intros = {
        "场景简述": "案情是这样的",
        "诈骗手法": "在诈骗手法上",
        "关键手法": "在关键手法上",
        "风险信号": "从风险信号看",
        "风险等级": "风险等级属于",
        "防范建议": "在防范建议上",
        "受害群体": "受害群体主要是",
    }
    intro = intros.get(section)
    if not intro or line.startswith(intro):
        return line
    return f"{intro}，{line}"


def clean_speech_body(text: str) -> str:
    text = text.replace("：", "，")
    text = text.replace('"', "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ，、；：。")


def clean_representative_body(text: str) -> str:
    text = re.sub(
        r"(.+?)是[^。；，,]*?代表作[，,]\s*(还有.+)",
        r"\1，\2",
        text,
    )
    text = re.sub(
        r"(.+?)是[^。；，,]*?代表作$",
        r"\1",
        text,
    )
    return text.strip(" ，、；：。")


def build_source_speech(
    question: str,
    sources: list[CaseItem],
    max_chars: int = 760,
) -> str:
    if not sources:
        return ""

    item = sources[0]
    title = item.title
    intro = item.summary
    feature = extract_structured_field(item.content, "关键手法")
    risk_signal = extract_structured_field(item.content, "风险信号")
    value = extract_structured_field(item.content, "防范建议")
    level = item.level
    city = item.city
    district = item.district

    location = city
    if district and district != city:
        location = f"{city}{district}" if city else district
    risk_level = f"{level}风险" if level and level not in {"未分类", "无"} else "反诈"
    category = f"{item.category}类" if item.category else ""

    sentences = []
    if normalize_text(question) == title:
        opening = f"{title}是{location + '的' if location else ''}{category}{risk_level}案例。"
    else:
        opening = (
            f"关于{normalize_text(question) or title}，资料里最相关的是{title}。"
            f"它是{location + '的' if location else ''}{category}{risk_level}案例。"
        )
    sentences.append(opening)

    intro_text = spoken_sentences(intro, max_chars=150, count=2)
    if intro_text:
        sentences.append(intro_text)

    feature_text = spoken_sentences(feature or risk_signal, max_chars=190, count=2)
    if feature_text and feature_text not in intro_text:
        sentences.append(f"关键风险信号是，{feature_text}")

    value_text = spoken_sentences(value, max_chars=150, count=1)
    if value_text:
        sentences.append(f"防范建议是，{value_text}")

    speech = normalize_text("".join(sentences))
    speech = re.sub(r"[，、；：]\s*([。！？])", r"\1", speech)
    speech = re.sub(r"。{2,}", "。", speech).strip(" 。")
    if not speech:
        return ""
    if len(speech) > max_chars:
        boundary = max(speech.rfind(mark, 0, max_chars) for mark in "。！？")
        if boundary < max_chars // 2:
            boundary = max_chars
        speech = speech[: boundary + 1].rstrip("，、；： ")
        if speech and speech[-1] not in "。！？":
            speech += "。"
    return speech


def spoken_sentences(text: str, max_chars: int, count: int) -> str:
    text = clean_spoken_source_text(text)
    if not text:
        return ""
    parts = [
        part.strip(" ，,；;")
        for part in re.split(r"[。！？]", text)
        if part.strip(" ，,；;")
    ]
    selected = []
    total = 0
    for part in parts:
        if not part:
            continue
        if is_admin_sentence(part):
            continue
        next_len = len(part) + 1
        if selected and (len(selected) >= count or total + next_len > max_chars):
            break
        selected.append(part)
        total += next_len
    return "。".join(selected).strip(" 。") + ("。" if selected else "")


def is_admin_sentence(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "党和政府",
            "市委",
            "市政府",
            "战略部署",
            "从业人员",
            "销售额",
            "就业",
            "地址",
            "电话",
            "面积",
            "经度",
            "纬度",
            "经纬度",
        )
    )


def clean_spoken_source_text(text: str) -> str:
    text = clean_knowledge_text(text)
    text = re.sub(r"根据提供的信息[^：:]*[:：]?", " ", text)
    text = re.sub(r"经度[:：]?\s*[-\d.]+", " ", text)
    text = re.sub(r"纬度[:：]?\s*[-\d.]+", " ", text)
    text = re.sub(r"地理位置[:：][^。；;]+[。；;]?", " ", text)
    text = re.sub(r"地址[:：][^。；;]+[。；;]?", " ", text)
    text = re.sub(r"面积[:：][^。；;]+[。；;]?", " ", text)
    text = re.sub(r"从业人员[:：][^。；;]+[。；;]?", " ", text)
    text = re.sub(r"年销售额[:：][^。；;]+[。；;]?", " ", text)
    text = re.sub(r"\d+[、.)]\s*", "", text)
    text = text.replace("：", "，")
    return normalize_text(text)
