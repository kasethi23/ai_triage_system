"""Rule-based de-identification (privacy spec P6).

Sits between transcription and classification: `transcribe -> REDACT -> classify`.
The classifier only ever sees redacted text, so identifiers never cross the
boundary to the third-party classification API.

    redact(transcript, known) -> (redacted_text, token_map)

`token_map` maps each stable token back to the original string; it is what the
identifier table (P4) stores and what re-identification (P7) reverses.

Two stages:
  1. Deterministic (primary) — any identifiers passed in `known` (e.g. the room
     from keypad intake, or a patient name captured structurally) are matched
     exactly with high confidence.
  2. Residual heuristic (backstop) — Presidio's local recognizers for person
     names, phone numbers, dates, plus custom MRN / bed-room / age-over-89
     patterns.

**Local only.** Presidio runs a local spaCy model — nothing leaves the machine.
It is NOT an LLM pass (an LLM redactor would transmit the identifiers off-machine
to remove them, defeating the purpose). Recall is imperfect by nature; this is a
defence-in-depth layer for a synthetic-data prototype, not a certified pipeline.

Gated behind the `DEIDENTIFY_TRANSCRIPTS` config flag. Presidio is imported lazily
so the module has no import cost when the flag is off.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Entity type -> token label used in the redacted text.
_LABELS = {
    "PERSON": "PERSON",
    "PHONE_NUMBER": "ID",
    "DATE_TIME": "DATE",
    "MRN": "ID",
    "LOCATION_ROOM": "LOCATION",
    "AGE_OVER_89": "AGE_90+",
}

# Custom pattern recognizers (Presidio) for identifiers its defaults miss.
_MRN_PATTERN = r"\b(?:MRN|mrn|medical record(?: number)?)\s*[:#]?\s*\d{4,}\b|\b\d{6,10}\b"
_ROOM_PATTERN = r"\b(?:bed|room|unit|bay)\s+\w{1,4}\b"
# Ages strictly above 89 are a small-cell re-identification risk (HIPAA-informed).
_AGE_PATTERN = r"\b(9\d|1\d\d)[- ]?(?:years?[- ]old|yo|y/o)\b"


@lru_cache(maxsize=1)
def _engines():
    """Lazily build (and cache) the Presidio analyzer + anonymizer.

    Pinned to spaCy `en_core_web_sm` (~12 MB) rather than Presidio's default
    `en_core_web_lg` (~400 MB). `sm` has lower NER recall — acceptable for a
    synthetic-data prototype; switch to `en_core_web_lg` (or a transformer model)
    for production and document the change in SECURITY.md.
    """
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    for name, pattern, score in (
        ("MRN", _MRN_PATTERN, 0.7),
        ("LOCATION_ROOM", _ROOM_PATTERN, 0.6),
        ("AGE_OVER_89", _AGE_PATTERN, 0.7),
    ):
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity=name,
                patterns=[Pattern(name=name.lower(), regex=pattern, score=score)],
            )
        )
    return analyzer, AnonymizerEngine()


def _known_recognizers(known: dict | None):
    """Deny-list recognizers for identifiers known ahead of time (stage 1)."""
    if not known:
        return []
    from presidio_analyzer import PatternRecognizer

    recognizers = []
    for field, value in known.items():
        value = (value or "").strip()
        if not value or value.lower() in ("unknown", ""):
            continue
        # Split a name into its parts so "John Smith" also catches bare "Smith".
        terms = {value, *value.split()}
        entity = "PERSON" if "name" in field else "LOCATION_ROOM"
        recognizers.append(
            PatternRecognizer(
                supported_entity=entity,
                deny_list=[t for t in terms if len(t) > 1],
                deny_list_score=0.95,
            )
        )
    return recognizers


def redact(transcript: str, known: dict | None = None) -> tuple[str, dict]:
    """Return (redacted_text, token_map). token_map: token -> original string.

    Stable, coreferent tokens within a call: the second mention of the same
    person or place reuses the first token.
    """
    if not transcript:
        return transcript, {}

    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer = _engines()
    entities = list(_LABELS.keys())
    results = analyzer.analyze(
        text=transcript,
        language="en",
        entities=entities,
        ad_hoc_recognizers=_known_recognizers(known) or None,
    )

    token_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}  # (label, normalized original) -> token

    def _operator_for(label: str):
        def _op(text: str, _params=None) -> str:
            key = (label, text.strip().lower())
            if key in seen:
                return seen[key]
            if label == "AGE_90+":
                token = "[AGE_90+]"
            else:
                counters[label] = counters.get(label, 0) + 1
                token = f"[{label}_{counters[label]}]"
            seen[key] = token
            token_map[token] = text
            return token

        return _op

    operators = {
        entity: OperatorConfig("custom", {"lambda": _operator_for(_LABELS[entity])})
        for entity in entities
    }

    redacted = anonymizer.anonymize(
        text=transcript, analyzer_results=results, operators=operators
    ).text
    return redacted, token_map


def reidentify(redacted_text: str, token_map: dict) -> str:
    """Reverse redaction using the token map (used by P7's authorised path)."""
    out = redacted_text
    # Replace longer tokens first so [AGE_90+] etc. don't partially match.
    for token in sorted(token_map, key=len, reverse=True):
        out = out.replace(token, token_map[token])
    return out
