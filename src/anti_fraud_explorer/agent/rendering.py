"""Jinja2 template rendering helpers."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,
)


def render_template(name: str, **kwargs) -> str:
    return _JINJA_ENV.get_template(name).render(**kwargs)


def build_transform_local(transform_type: str, target_item) -> str:
    """Build a template-based local answer for content transformation."""
    from ..item_cards import _title_with_family
    from ..dataset import get_ai_fields

    title = _title_with_family(target_item)
    category = target_item.category
    summary = target_item.summary
    ai = get_ai_fields(target_item.id)
    features = ai.get("key_methods", "") or summary
    level = target_item.level or ""

    return render_template(
        "transform_local.md.j2",
        transform_type=transform_type,
        title=title,
        category=category,
        summary=summary,
        features=features,
        level=level,
    ).strip()