"""Structured metadata extraction for anti-fraud case items."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .dataset import CaseItem

_FIELD_NAMES = (
    "案例标题",
    "场景简述",
    "性质判断",
    "判断理由",
    "入口渠道",
    "冒充身份",
    "虚假认知",
    "关键手法",
    "目标资产",
    "诈骗阶段",
    "风险信号",
    "风险等级",
    "受害群体",
    "是否造成损失",
    "损失类型",
    "防范建议",
    "来源名称",
    "涉及平台",
    "城市",
    "地区",
    "省份",
    "标签",
)
_FIELD_STOP_PATTERN = "|".join(re.escape(name) for name in _FIELD_NAMES)
_PROVINCE_PATTERN = re.compile(
    r"("
    r"北京市|天津市|上海市|重庆市|"
    r"香港特别行政区|澳门特别行政区|"
    r"内蒙古自治区|广西壮族自治区|西藏自治区|宁夏回族自治区|新疆维吾尔自治区|"
    r"[一-鿿]{2,7}省"
    r")"
)
@dataclass(frozen=True)
class FieldEvidence:
    """Provenance metadata for a single extracted field."""

    source_text: str = ""
    method: str = ""  # "rule" / "rule_infer" / "llm" / "manual"
    confidence: float = 0.0


def _evidence_dict(
    source_text: str = "",
    method: str = "rule",
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "source_text": source_text,
        "method": method,
        "confidence": confidence,
    }



# ---------------------------------------------------------------------------
# Stable structured metadata (rule-based extraction)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuredMeta:
    """Stable metadata extracted from the source content."""

    level: str = ""
    province: str = ""
    city: str = ""
    district: str = ""
    inheritors: tuple[str, ...] = ()
    coordinates: tuple[float, float] | None = None
    display_forms: tuple[str, ...] = ()
    organization: str = ""
    history: str = ""
    features: str = ""
    cultural_value: str = ""
    _evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Soft labels (AI-assisted, MVP rule-inferred)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoftLabels:
    """AI-assisted soft labels for downstream recommendation tasks."""

    suitable_scenarios: tuple[str, ...] = ()
    target_audience: tuple[str, ...] = ()
    display_difficulty: str = ""
    interaction_potential: str = ""
    creative_product_potential: str = ""
    education_value: str = ""
    cultural_keywords: tuple[str, ...] = ()
    _evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rule-based extraction
# ---------------------------------------------------------------------------


class RuleExtractor:
    """Extract deterministic metadata fields with regex rules."""

    def extract(self, item: CaseItem) -> StructuredMeta:
        fields = _extract_all_fields(item.content)
        raw_province = _province_from_region(_first_value(fields, "场景简述")) or _first_value(
            fields, "省份"
        )
        city_val = _first_value(fields, "城市")
        province = raw_province
        province_method = "rule"

        evidence: dict[str, dict[str, Any]] = {}

        level_val, level_ev = _extract_level(fields)
        evidence["level"] = level_ev

        prov_ev = _evidence_dict(
            source_text=raw_province or city_val,
            method=province_method,
            confidence=0.95 if province else 0.0,
        )
        evidence["province"] = prov_ev

        evidence["city"] = _evidence_dict(
            source_text=city_val,
            method="rule",
            confidence=0.95 if city_val else 0.0,
        )

        district_val = _first_value(fields, "地区")

        features_val = _first_value(fields, "关键手法")
        evidence["features"] = _evidence_dict(
            source_text=features_val,
            method="rule",
            confidence=0.8 if features_val else 0.0,
        )

        cv_val = _first_value(fields, "防范建议")
        evidence["cultural_value"] = _evidence_dict(
            source_text=cv_val,
            method="rule",
            confidence=0.8 if cv_val else 0.0,
        )

        return StructuredMeta(
            level=level_val,
            province=province,
            city=city_val,
            district=district_val,
            inheritors=(),
            coordinates=_extract_coordinates(fields.get("经纬度", ())),
            display_forms=_unique_values(fields.get("关键手法", ())),
            organization=_first_value(fields, "来源名称"),
            history="",
            features=features_val,
            cultural_value=cv_val,
            _evidence=evidence,
        )

    def extract_batch(self, items: list[CaseItem]) -> dict[str, StructuredMeta]:
        return {item.id: self.extract(item) for item in items}


def _extract_level(fields: dict[str, tuple[str, ...]]) -> tuple[str, dict[str, Any]]:
    value = _first_value(fields, "风险等级")
    mapped = _normalize_level(value)
    confidence = 1.0 if mapped else 0.0
    return mapped, _evidence_dict(source_text=value, method="rule", confidence=confidence)


def _normalize_level(raw: str) -> str:
    if not raw:
        return ""
    if "极高" in raw:
        return "极高"
    if "高" in raw and "风险" in raw:
        return "高"
    if "中" in raw and "风险" in raw:
        return "中"
    if raw in ("极高", "高", "中"):
        return raw
    return raw


# ---------------------------------------------------------------------------
# MVP SoftLabels rule inference
# ---------------------------------------------------------------------------


_CATEGORY_SCENARIO_MAP: dict[str, tuple[str, ...]] = {
    "刷单返利": ("校园宣讲", "社区宣传", "新媒体提醒"),
    "冒充客服": ("社区宣传", "新媒体提醒", "以案说法"),
    "冒充公检法": ("社区宣传", "老年防骗", "以案说法"),
    "虚假投资理财": ("社区宣传", "企业培训", "老年防骗"),
    "网络游戏交易": ("校园宣讲", "新媒体提醒"),
    "贷款征信": ("校园宣讲", "社区宣传"),
    "冒充领导熟人": ("企业培训", "以案说法"),
    "养老诈骗": ("老年防骗", "社区宣传"),
}
_DEFAULT_SCENARIOS: tuple[str, ...] = ("社区宣传", "以案说法", "新媒体提醒")

_CATEGORY_CREATIVE_MAP: dict[str, str] = {
    "刷单返利": "高",
    "冒充客服": "高",
    "冒充公检法": "高",
    "虚假投资理财": "高",
    "网络游戏交易": "中",
    "贷款征信": "中",
    "冒充领导熟人": "中",
    "养老诈骗": "高",
}


def _infer_display_difficulty(display_forms: tuple[str, ...]) -> str:
    text = " ".join(display_forms)
    if not text:
        return ""
    if any(t in text for t in ("屏幕共享", "安全账户", "诱导转账", "虚假投资平台")):
        return "高"
    if any(t in text for t in ("电话", "短信", "微信", "不明链接", "二维码")):
        return "中"
    return "低"


def _infer_interaction_potential(display_forms: tuple[str, ...]) -> str:
    text = " ".join(display_forms)
    if not text:
        return ""
    if any(t in text for t in ("电话", "短信", "微信", "QQ", "App", "二维码", "不明链接")):
        return "高"
    if any(t in text for t in ("任务", "小额返利", "虚假客服", "要求转账")):
        return "中"
    return "低"


def _infer_education_value(level: str) -> str:
    if level in ("极高", "高"):
        return "高"
    if level == "中":
        return "中"
    return ""


def _infer_audience_from_scenarios(scenarios: tuple[str, ...]) -> tuple[str, ...]:
    audience: list[str] = []
    for scenario in scenarios:
        if "校园" in scenario:
            audience.append("中小学生")
        if "社区" in scenario:
            audience.append("社区居民")
        if "老年" in scenario:
            audience.append("老年人")
        if "企业" in scenario:
            audience.append("企业员工")
        if "新媒体" in scenario:
            audience.append("普通公众")
    return tuple(dict.fromkeys(audience))


def _extract_cultural_keywords(item: CaseItem, features: str) -> tuple[str, ...]:
    keywords: list[str] = []
    text = f"{item.category} {features} {item.summary[:200]}"
    # extract 2-4 char Chinese nouns as candidate keywords
    candidates = re.findall(r"[一-鿿]{2,6}", text)
    seen: set[str] = set()
    for candidate in candidates:
        if len(candidate) >= 3 and candidate not in seen:
            seen.add(candidate)
            keywords.append(candidate)
        if len(keywords) >= 10:
            break
    return tuple(keywords)


def infer_soft_labels(item: CaseItem, meta: StructuredMeta) -> SoftLabels:
    """Compute soft labels (suitable_scenarios + creative_product_potential only).

    display_difficulty, interaction_potential, education_value, target_audience,
    and cultural_keywords have been removed from CaseItem — use the standalone
    helpers (_infer_* functions) directly if needed for scoring.
    """
    category = item.category
    scenarios = _CATEGORY_SCENARIO_MAP.get(category, _DEFAULT_SCENARIOS)
    creative = _CATEGORY_CREATIVE_MAP.get(category, "")

    evidence: dict[str, dict[str, Any]] = {}
    evidence["suitable_scenarios"] = _evidence_dict(
        source_text=f"category={category}",
        method="rule_infer",
        confidence=0.6 if scenarios else 0.0,
    )

    return SoftLabels(
        suitable_scenarios=scenarios,
        creative_product_potential=creative,
        _evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_all_fields(content: str) -> dict[str, tuple[str, ...]]:
    fields: dict[str, list[str]] = {}
    for field_name in _FIELD_NAMES:
        pattern = re.compile(
            rf"(?:^|[,，]\s*){re.escape(field_name)}\s*[:：]\s*"
            rf"(.*?)(?=(?:[,，]\s*(?:{_FIELD_STOP_PATTERN})\s*[:：])|$)",
            re.S,
        )
        values = [
            _clean_value(match.group(1))
            for match in pattern.finditer(content)
            if _clean_value(match.group(1))
        ]
        if values:
            fields[field_name] = values
    return {key: tuple(value) for key, value in fields.items()}


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n,，")


def _first_value(fields: dict[str, tuple[str, ...]], name: str) -> str:
    values = fields.get(name) or ()
    return values[0] if values else ""


def _province_from_region(region: str) -> str:
    match = _PROVINCE_PATTERN.search(region)
    return match.group(1) if match else ""


def _split_people(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    names = [
        item.strip(" \t\r\n,，、;；")
        for item in re.split(r"[、,，;；\s]+", value)
        if item.strip(" \t\r\n,，、;；")
    ]
    return tuple(dict.fromkeys(names))


def _unique_values(values: tuple[str, ...]) -> tuple[str, ...]:
    parts: list[str] = []
    for value in values:
        parts.extend(
            part.strip(" \t\r\n,，、;；")
            for part in re.split(r"[、;；/]+", value)
            if part.strip(" \t\r\n,，、;；")
        )
    return tuple(dict.fromkeys(parts))


def _extract_coordinates(values: tuple[str, ...]) -> tuple[float, float] | None:
    for value in values:
        match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)",
            value,
        )
        if not match:
            continue
        return (float(match.group(1)), float(match.group(2)))
    return None
