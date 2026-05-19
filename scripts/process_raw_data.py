#!/usr/bin/env python3
"""Process raw anti-fraud case data into a fully normalized dataset using an LLM.

This script replaces the old rule-based build_dataset.py. It reads raw cases
from data/raw/dataset.json, sends each case to an LLM with a detailed system
prompt that encapsulates the project's annotation specification, and writes
validated, structured records to data/processed/case_items.json.

Usage:
    python scripts/process_raw_data.py
    python scripts/process_raw_data.py --source data/raw/dataset.json --output data/processed/case_items.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

# ---------------------------------------------------------------------------
# System prompt – encapsulates the annotation spec
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是反诈案例数据标注专家。你的任务是根据提供的原始信息，生成一份完全符合《反诈智能体数据采集与标注规范》的 JSON 案例记录。

## 字段要求
你必须输出一个 JSON 对象，包含以下所有字段。对于多选字段，请使用中文分号`；`分隔（例如：`电话；短信`）。日期格式统一为`YYYY-MM-DD`。

### 必填字段
| 字段名 | 类型 | 说明 | 要求 |
|--------|------|------|------|
| case_id | 文本 | 案例编号，如 FZ-001 | 非空 |
| title | 文本 | 案例标题，一句话概括 | 非空 |
| summary | 长文本 | 场景简述，100-200字描述发生了什么 | 非空 |
| nature_judgment | 单选枚举 | 性质判断 | 必须从枚举值中选择 |
| judgment_reason | 长文本 | 为什么这样判断，必须说明具体风险信号 | 非空 |
| entry_channels | 多选枚举 | 入口渠道 | 必须使用枚举值 |
| impersonated_identity | 多选枚举 | 冒充身份 | 必须使用枚举值 |
| false_belief | 多选枚举 | 用户被诱导相信什么 | 必须使用枚举值 |
| key_methods | 多选枚举 | 关键手法 | 必须使用枚举值 |
| target_assets | 多选枚举 | 目标资产 | 必须使用枚举值 |
| fraud_stage | 多选枚举 | 诈骗阶段 | 必须使用枚举值 |
| risk_signals | 长文本/多标签 | 本案例触发的危险点 | 非空 |
| risk_level | 单选枚举 | 风险等级 | 必须从枚举值中选择 |
| loss_occurred | 单选枚举 | 是否造成损失 | 枚举值 |
| loss_type | 多选枚举 | 损失类型 | 枚举值 |
| prevention_advice | 长文本 | 防范建议，必须具体可执行 | 非空 |
| source_name | 文本 | 来源名称 | 非空 |
| source_type | 单选枚举 | 来源类型 | 枚举值 |
| collection_date | 日期 | 采集日期 | YYYY-MM-DD |
| is_desensitized | 单选枚举 | 是否脱敏 | 枚举值 |

### 建议字段
| 字段名 | 类型 | 说明 |
|--------|------|------|
| official_category | 多选枚举 | 官方宣传参考类别（2025版手册） |
| ccl2023_category | 单选/多选 | CCL2023 参考类别 |
| custom_subcategory | 文本 | 自定义细分类 |
| tags | 多标签文本 | 标签，分号分隔 |
| involved_platforms | 文本/多选 | 涉及平台 |
| victim_group | 文本/枚举 | 受害群体 |
| emergency_plan_id | 文本 | 应急方案编号 |
| law_basis_ids | 文本 | 法规依据编号，分号分隔 |
| source_links | 文本 | 来源链接，分号分隔 |
| publish_date | 日期 | 发布日期 |
| remark | 长文本 | 备注 |

### 枚举值列表（严格按照以下标准词填写）
- nature_judgment: 确认诈骗；疑似诈骗；诈骗前兆/风险信号；消费欺诈；虚假宣传；骚扰营销；普通消费纠纷；账号安全风险；个人信息泄露风险；无法判断
- entry_channels: 电话；短信；微信；QQ；Telegram；Steam；Discord；搜索引擎；网页广告；邮件；App；小程序；二维码；线下扫码；社交平台私信；游戏平台私信；其他
- impersonated_identity: 无明确冒充；冒充平台官方；冒充客服；冒充电商物流客服；冒充公检法；冒充银行/金融机构；冒充保险客服；冒充领导熟人；冒充亲友；冒充招聘人员；冒充投资导师；冒充游戏管理员；冒充官方网站；冒充商家；冒充快递物流；冒充票务/航空客服；其他
- false_belief: 误以为对方是官方；误以为账号存在风险；误以为有免费福利；误以为投资稳赚不赔；误以为需要配合调查；误以为必须立即操作；误以为网站是正规官网；误以为交易受到平台保护；误以为对方有权威身份；误以为不操作会造成损失；误以为可以轻松赚钱；误以为需要缴费解冻；误以为需要验证身份；其他
- key_methods: 钓鱼链接；仿冒官网；诱导下载陌生App；屏幕共享；索要验证码；小额返利；提现失败；保证金/解冻费；安全账户；虚假客服；虚假交易；虚假验证；AI换脸/变声；搜索引擎引流；电话机器人外呼；私信引流；诱导转账；诱导扫码；诱导开启权限；虚假投资平台；虚假订单/任务；冒充官方通知；其他
- target_assets: 钱款；银行卡信息；身份证信息；手机号；验证码；平台账号；账号密码；游戏饰品；虚拟货币；通讯录；设备权限；支付权限；人脸识别信息；洗钱通道；其他
- fraud_stage: 接触引流；建立信任；制造压力/诱惑；诱导操作；资产获取；二次压榨；拉黑失联；已识别未受损；未知
- risk_level: 低；中；高；极高；无法判断
- loss_occurred: 是；否；未知；未造成但存在风险
- loss_type: 金钱损失；账号被盗；个人信息泄露；银行卡风险；验证码泄露；设备权限泄露；虚拟财产损失；通讯录泄露；未造成损失；未知；其他
- official_category: 刷单返利；虚假网络投资理财；虚假购物服务；冒充电商物流客服；贷款征信；冒充领导熟人；冒充公检法；婚恋交友；网络游戏产品虚假交易；机票退改签；其他/无法对应
- ccl2023_category: 刷单返利类；冒充电商物流客服类；虚假网络投资理财类；贷款、代办信用卡类；虚假征信类；虚假购物、服务类；冒充公检法及政府机关类；冒充领导、熟人类；网络游戏产品虚假交易类；网络婚恋、交友类；冒充军警购物类；网黑案件；无法对应
- source_type: 官方；论文；数据集；媒体；个人经历；其他
- is_desensitized: 是；否；不涉及；待处理

## 处理原则
1. 如果原始信息中缺少某个必填字段，请尝试根据已有信息合理推断，但务必在备注中标明"推断"。
2. 所有多值字段必须使用中文分号`；`分隔。
3. 日期格式严格为 YYYY-MM-DD，如无法确定具体日期，填写年份即可，如"2026"。
4. 防范建议应具体可执行，不写空泛口号。
5. 输出必须是纯 JSON 对象，不要包含 Markdown 代码块标记。
6. 特别注意：`ccl2023_category` 字段应优先参考更精确的12分类标准进行填写。
"""

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG = logging.getLogger(__name__)
MODEL = os.getenv("AI_MODEL", "deepseek-v4-flash")
MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
RETRY_DELAY = 2  # seconds
TEMPERATURE = 0.2  # low temperature for factual extraction

# ---------------------------------------------------------------------------
# Required fields (must be non-empty)
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = [
    "case_id", "title", "summary", "nature_judgment", "judgment_reason",
    "entry_channels", "impersonated_identity", "false_belief", "key_methods",
    "target_assets", "fraud_stage", "risk_signals", "risk_level",
    "loss_occurred", "loss_type", "prevention_advice", "source_name",
    "source_type", "collection_date", "is_desensitized",
]

# ---------------------------------------------------------------------------
# Enum fields and their allowed values (for basic validation)
# ---------------------------------------------------------------------------
ENUM_FIELDS = {
    "nature_judgment": {
        "确认诈骗", "疑似诈骗", "诈骗前兆/风险信号", "消费欺诈",
        "虚假宣传", "骚扰营销", "普通消费纠纷", "账号安全风险",
        "个人信息泄露风险", "无法判断",
    },
    "risk_level": {"低", "中", "高", "极高", "无法判断"},
    "loss_occurred": {"是", "否", "未知", "未造成但存在风险"},
    "source_type": {"官方", "论文", "数据集", "媒体", "个人经历", "其他"},
    "is_desensitized": {"是", "否", "不涉及", "待处理"},
}


def get_client() -> OpenAI:
    """Create an OpenAI-compatible client using environment variables."""
    api_key = os.getenv("AI_API_KEY", "")
    base_url = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError("AI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key, base_url=base_url)


def validate_case(case: dict[str, Any]) -> bool:
    """Check that all required fields are present and enums match."""
    for field in REQUIRED_FIELDS:
        if field not in case or not str(case[field]).strip():
            LOG.warning("Missing required field: %s", field)
            return False
    for field, allowed in ENUM_FIELDS.items():
        if field in case:
            # For single-value enum fields
            value = str(case[field]).strip()
            if value and value not in allowed:
                LOG.warning("Invalid enum value '%s' in field '%s'", value, field)
                # We allow the record to pass but log a warning
    return True


def normalize_case_with_llm(
    client: OpenAI,
    raw_case: dict[str, Any],
    case_index: int,
) -> dict[str, Any] | None:
    """Send a raw case to the LLM and return a normalized dict."""
    user_prompt = json.dumps(raw_case, ensure_ascii=False)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=TEMPERATURE,
            )
            result = json.loads(response.choices[0].message.content)
            # Ensure case_id is present
            if "case_id" not in result or not result["case_id"]:
                result["case_id"] = f"FZ-LLM-{case_index:04d}"
            return result
        except Exception as exc:
            LOG.error(
                "LLM call failed for case %d (attempt %d/%d): %s",
                case_index, attempt, MAX_RETRIES, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


def load_raw_cases(source_path: Path) -> list[dict[str, Any]]:
    """Load raw cases from a JSON file.

    Supports both a plain list and an object with a '案例列表' key.
    """
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "案例列表" in payload:
        return payload["案例列表"]
    if isinstance(payload, list):
        return payload
    raise ValueError("Unsupported raw data format: expected a list or a dict with key '案例列表'")


def process_raw_data(
    source_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main pipeline: raw -> LLM -> validated -> dataset."""
    raw_cases = load_raw_cases(source_path)
    LOG.info("Loaded %d raw cases from %s", len(raw_cases), source_path)

    client = get_client()
    processed: list[dict[str, Any]] = []
    failed_indices: list[int] = []

    for i, raw in enumerate(raw_cases, start=1):
        LOG.info("Processing case %d/%d ...", i, len(raw_cases))
        normalized = normalize_case_with_llm(client, raw, i)
        if normalized is None:
            LOG.error("Case %d could not be normalized after %d retries", i, MAX_RETRIES)
            failed_indices.append(i)
            continue

        if not validate_case(normalized):
            LOG.warning("Case %d failed validation – still included with warnings", i)

        processed.append(normalized)

    # Generate category statistics
    category_counter: dict[str, int] = {}
    for case in processed:
        cat = case.get("ccl2023_category") or case.get("official_category", "未分类")
        # ccl2023_category may be multi-value; take the first one
        if isinstance(cat, str) and "；" in cat:
            cat = cat.split("；")[0]
        category_counter[cat] = category_counter.get(cat, 0) + 1

    categories = sorted(category_counter.items(), key=lambda x: -x[1])
    category_list = [
        {"id": idx + 1, "name": name, "item_count": count}
        for idx, (name, count) in enumerate(categories)
    ]

    dataset = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "anti_fraud_cases",
            "file": str(source_path.name),
            "item_count": len(processed),
        },
        "categories": category_list,
        "items": processed,
    }

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        LOG.info("Wrote %d cases to %s", len(processed), output_path)
    else:
        LOG.info("Dry run – would write %d cases", len(processed))

    if failed_indices:
        LOG.warning("Failed cases (index in raw list): %s", failed_indices)

    return dataset


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Process raw anti-fraud data with an LLM",
    )
    parser.add_argument(
        "--source", type=Path,
        default=root / "data" / "raw" / "dataset.json",
        help="Path to raw dataset (default: data/raw/dataset.json)",
    )
    parser.add_argument(
        "--output", type=Path,
        default=root / "data" / "processed" / "case_items.json",
        help="Path for output normalized dataset (default: data/processed/case_items.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Do not write output, just print summary",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    # Load .env before anything else (required when running Windows Python from WSL)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except Exception:
        pass

    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    process_raw_data(
        source_path=args.source.resolve(),
        output_path=args.output.resolve(),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
