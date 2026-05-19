"""Build the normalized anti-fraud dataset and companion AI fields."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROVINCES = (
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
    "河北省",
    "河南省",
    "山东省",
    "山西省",
    "陕西省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "湖北省",
    "湖南省",
    "广东省",
    "海南省",
    "四川省",
    "贵州省",
    "云南省",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "甘肃省",
    "青海省",
    "台湾省",
    "内蒙古自治区",
    "广西壮族自治区",
    "西藏自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "香港特别行政区",
    "澳门特别行政区",
)
PROVINCE_SHORT_MAP = {
    "北京": "北京市",
    "天津": "天津市",
    "上海": "上海市",
    "重庆": "重庆市",
    "河北": "河北省",
    "河南": "河南省",
    "山东": "山东省",
    "山西": "山西省",
    "陕西": "陕西省",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "安徽": "安徽省",
    "福建": "福建省",
    "江西": "江西省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "广东": "广东省",
    "海南": "海南省",
    "四川": "四川省",
    "贵州": "贵州省",
    "云南": "云南省",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "台湾": "台湾省",
    "内蒙古": "内蒙古自治区",
    "广西": "广西壮族自治区",
    "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
}
CITY_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,8}(?:市|州|地区|盟))")
DISTRICT_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,12}(?:区|县|旗))")
TRAILING_PUNCT_RE = re.compile(r"[。；;，,、\s]+$")
SCENARIO_TERMS = {
    "校园宣讲": ("学生", "校园", "学校", "班会", "宿舍", "求职", "游戏"),
    "社区宣传": ("普通用户", "社区", "居民", "街道", "网购", "兼职", "投资"),
    "老年防骗": ("老人", "养老", "保健品", "补贴", "投资"),
    "企业培训": ("财务", "老板", "领导", "对公", "企业"),
    "新媒体提醒": ("短视频", "社交", "App", "网购", "客服", "投资", "刷单"),
    "以案说法": ("案例", "复盘", "拆解", "风险", "预警"),
}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def clean_label(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    return TRAILING_PUNCT_RE.sub("", text)


def split_multi_value(value: Any) -> list[str]:
    text = clean_label(value)
    if not text or text == "其他":
        return []
    parts = re.split(r"[；;、,/|]|(?:\s*；\s*)", text)
    result: list[str] = []
    for part in parts:
        item = clean_label(part)
        if item and item not in result and item != "其他":
            result.append(item)
    return result


def detect_province(text: str) -> str:
    for province in PROVINCES:
        if province in text:
            return province
    for short, full in PROVINCE_SHORT_MAP.items():
        if short in text:
            return full
    return ""


def detect_city(text: str) -> str:
    match = CITY_PATTERN.search(text)
    return match.group(1) if match else ""


def detect_district(text: str) -> str:
    match = DISTRICT_PATTERN.search(text)
    return match.group(1) if match else ""


def normalize_category(item: dict[str, Any]) -> str:
    primary = clean_label(item.get("官方宣传参考类别"))
    subtype = clean_label(item.get("自定义细分类"))
    if primary and primary != "其他/无法对应":
        return primary
    if subtype:
        return re.sub(r"类诈骗.*$", "类诈骗", subtype)
    return "其他诈骗"


def normalize_family(item: dict[str, Any], category: str) -> str:
    subtype = clean_label(item.get("自定义细分类"))
    if subtype:
        return subtype
    impersonation = clean_label(item.get("冒充身份"))
    if impersonation and impersonation != "无明确冒充":
        return impersonation
    return category


def build_display_forms(item: dict[str, Any]) -> tuple[str, ...]:
    tags: list[str] = []
    for field in ("入口渠道", "关键手法", "风险信号", "涉及平台"):
        for part in split_multi_value(item.get(field)):
            if part not in tags and part != "信息不足":
                tags.append(part)
            if len(tags) >= 6:
                return tuple(tags)
    return tuple(tags)


def build_suitable_scenarios(item: dict[str, Any], category: str) -> tuple[str, ...]:
    text_parts = [
        clean_label(item.get("受害群体")),
        clean_label(item.get("入口渠道")),
        clean_label(item.get("关键手法")),
        clean_label(item.get("案例标题")),
        clean_label(item.get("场景简述")),
        category,
    ]
    text = " ".join(part for part in text_parts if part)
    scenarios: list[str] = []
    for scenario, terms in SCENARIO_TERMS.items():
        if any(term in text for term in terms):
            scenarios.append(scenario)
    if "老人" in text and "老年防骗" not in scenarios:
        scenarios.append("老年防骗")
    if "学生" in text and "校园宣讲" not in scenarios:
        scenarios.append("校园宣讲")
    if "领导" in text or "财务" in text:
        if "企业培训" not in scenarios:
            scenarios.append("企业培训")
    if not scenarios:
        scenarios = ["社区宣传", "以案说法"]
    if "以案说法" not in scenarios:
        scenarios.append("以案说法")
    return tuple(scenarios[:4])


def build_content(item: dict[str, Any]) -> str:
    fields = [
        ("案例标题", item.get("案例标题")),
        ("场景简述", item.get("场景简述")),
        ("性质判断", item.get("性质判断")),
        ("判断理由", item.get("判断理由")),
        ("入口渠道", item.get("入口渠道")),
        ("冒充身份", item.get("冒充身份")),
        ("虚假认知", item.get("虚假认知")),
        ("关键手法", item.get("关键手法")),
        ("目标资产", item.get("目标资产")),
        ("诈骗阶段", item.get("诈骗阶段")),
        ("风险信号", item.get("风险信号")),
        ("风险等级", item.get("风险等级")),
        ("受害群体", item.get("受害群体")),
        ("是否造成损失", item.get("是否造成损失")),
        ("损失类型", item.get("损失类型")),
        ("防范建议", item.get("防范建议")),
        ("来源名称", item.get("来源名称")),
    ]
    lines = [f"{label}：{clean_label(value)}" for label, value in fields if clean_label(value)]
    return "\n".join(lines)


def build_search_text(item: dict[str, Any], category: str, family: str, summary: str, content: str) -> str:
    parts = [
        clean_label(item.get("案例标题")),
        category,
        family,
        summary,
        clean_label(item.get("标签")),
        clean_label(item.get("受害群体")),
        clean_label(item.get("入口渠道")),
        clean_label(item.get("关键手法")),
        clean_label(item.get("风险信号")),
        clean_label(item.get("防范建议")),
        content,
    ]
    return " ".join(part for part in parts if part)


def build_ai_fields(item: dict[str, Any]) -> dict[str, str]:
    features = "；".join(
        part for part in [
            clean_label(item.get("关键手法")),
            clean_label(item.get("风险信号")),
            clean_label(item.get("冒充身份")),
        ]
        if part and part != "信息不足"
    )
    history = clean_label(item.get("来源名称")) or clean_label(item.get("发布日期"))
    cultural_value = clean_label(item.get("防范建议"))
    return {
        "features": features,
        "history": history,
        "cultural_value": cultural_value,
    }


def load_cases(source_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    cases = payload.get("案例列表")
    if not isinstance(cases, list):
        raise ValueError("dataset.json 中缺少 案例列表")
    return [case for case in cases if isinstance(case, dict)]


def build_dataset(source_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    cases = load_cases(source_path)
    items: list[dict[str, Any]] = []
    ai_fields: dict[str, dict[str, str]] = {}
    category_counter: Counter[str] = Counter()

    for case in cases:
        item_id = clean_label(case.get("案例编号"))
        title = clean_label(case.get("案例标题")) or item_id
        summary = clean_label(case.get("场景简述"))
        category = normalize_category(case)
        family = normalize_family(case, category)
        level = clean_label(case.get("风险等级"))
        text_blob = " ".join(
            clean_label(case.get(field))
            for field in ("场景简述", "来源名称", "案例标题")
        )
        province = detect_province(text_blob)
        city = detect_city(text_blob)
        district = detect_district(text_blob)
        display_forms = build_display_forms(case)
        suitable_scenarios = build_suitable_scenarios(case, category)
        content = build_content(case)
        search_text = build_search_text(case, category, family, summary, content)

        items.append({
            "id": item_id,
            "title": title,
            "family": family,
            "category": category,
            "summary": summary,
            "content": content,
            "search_text": search_text,
            "level": level,
            "province": province,
            "city": city,
            "district": district,
            "display_forms": list(display_forms),
            "suitable_scenarios": list(suitable_scenarios),
        })
        ai_fields[item_id] = build_ai_fields(case)
        category_counter[category] += 1

    category_names = sorted(category_counter, key=lambda name: (-category_counter[name], name))
    categories = [
        {"id": index + 1, "name": name, "item_count": int(category_counter[name])}
        for index, name in enumerate(category_names)
    ]
    dataset = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "anti_fraud_cases",
            "file": str(source_path.name),
            "item_count": len(items),
        },
        "categories": categories,
        "items": items,
    }
    return dataset, ai_fields


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=root / "dataset.json")
    parser.add_argument("--output", type=Path, default=root / "data" / "processed" / "case_items.json")
    parser.add_argument("--ai-fields-output", type=Path, default=root / "data" / "processed" / "ai_fields.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset, ai_fields = build_dataset(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.ai_fields_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    args.ai_fields_output.write_text(json.dumps(ai_fields, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(dataset['items'])} cases to {args.output}")
    print(f"Wrote AI fields to {args.ai_fields_output}")


if __name__ == "__main__":
    main()
