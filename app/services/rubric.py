"""Load the team-written rubric (data/rubric.md) so it directly drives the
classifier prompt.

This is the link that makes the rubric the single source of truth: the classifier
builds its instructions from these functions at call time, so **editing
data/rubric.md changes classification behaviour** — there is no hand-copied
constant to drift out of sync.

Parsing is deliberately tolerant: if the rubric is missing or a section is empty,
the caller falls back to a built-in default, so the app still runs without it.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

RUBRIC_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rubric.md"
TIERS = ("critical", "urgent", "routine", "fyi")


@lru_cache(maxsize=1)
def _raw() -> str:
    try:
        return RUBRIC_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def reload() -> None:
    """Drop the cache so a subsequent read reflects edits to rubric.md."""
    _raw.cache_clear()


def _section(number: str) -> str:
    """Body of the '## {number}. ...' section, up to the next '## ' heading."""
    text = _raw()
    m = re.search(
        rf"^##\s*{re.escape(number)}[.\s].*?$(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _subsections(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"^###\s+(.+?)\s*$(.*?)(?=^###\s|\Z)", body, re.MULTILINE | re.DOTALL):
        out[m.group(1).strip().lower()] = m.group(2).strip()
    return out


def _clean(text: str) -> str:
    """Collapse markdown whitespace/bullets into prose the model reads cleanly."""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tier_definitions() -> dict[str, str]:
    """§1 — {tier: definition}. Empty strings if unfilled."""
    subs = _subsections(_section("1"))
    return {t: _clean(subs.get(t, "")) for t in TIERS}


def boundary_rules() -> str:
    """§2.1 — the critical-vs-urgent and routine-vs-fyi disambiguation rules."""
    subs = _subsections(_section("2.1"))
    parts = [f"{name}: {_clean(body)}" for name, body in subs.items() if body]
    return " ".join(parts)


def signals_not_to_use() -> str:
    """§6 — signals that must not influence severity."""
    return _clean(_section("6"))


def anchor_examples() -> dict[str, list[str]]:
    """§2 — {tier: [verbatim anchor quotes]} for use as few-shot worked examples."""
    subs = _subsections(_section("2"))
    return {t: re.findall(r'"([^"]+)"', subs.get(t, "")) for t in TIERS}


def is_usable() -> bool:
    """True when §1 is filled (not empty, no TODO placeholders)."""
    defs = tier_definitions()
    return all(defs.values()) and not any("TODO" in v for v in defs.values())
