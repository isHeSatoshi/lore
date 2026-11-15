import json
import unicodedata


def entity_label(text, limit):
    """SelfGraph names/titles are single-line labels, not verbatim documents."""
    clean = "".join(" " if unicodedata.category(c) in ("Cc", "Cs") else c for c in text)
    return " ".join(clean.split())[:limit]


def trace_summary(sql):
    # Escape rather than change whitespace inside SQL string literals.
    return json.dumps(sql, ensure_ascii=True)[1:-1][:4000]
