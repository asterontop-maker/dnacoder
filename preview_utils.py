from html import escape


def _statement_label(stmt) -> str:
    actor = getattr(stmt, "actor", "") or "Tanpa aktor"
    status = getattr(stmt, "status", "") or "review"
    confidence = getattr(stmt, "confidence", 0)
    try:
        confidence_text = f"{float(confidence):.2f}"
    except (TypeError, ValueError):
        confidence_text = "-"
    return f"{actor} | {status} | confidence {confidence_text}"


def _article_text(article) -> str:
    text = getattr(article, "body_text", "") or getattr(article, "full_text", "")
    if text:
        return text
    paragraphs = getattr(article, "paragraphs", []) or []
    return "\n\n".join(str(p) for p in paragraphs)


def _filtered_statements(article, status_filter: str):
    statements = list(getattr(article, "statements", []) or [])
    if status_filter == "semua":
        return statements
    return [s for s in statements if getattr(s, "status", "") == status_filter]


def build_article_preview_html(article, status_filter: str = "semua") -> tuple[str, int]:
    text = _article_text(article)
    statements = _filtered_statements(article, status_filter)

    ranges = []
    occupied_until = 0
    for idx, stmt in enumerate(statements):
        quote = (getattr(stmt, "quote", "") or "").strip()
        if not quote:
            continue
        start = text.find(quote)
        if start < 0:
            continue
        stop = start + len(quote)
        ranges.append((start, stop, idx, stmt))

    ranges.sort(key=lambda item: (item[0], item[1]))
    parts = []
    cursor = 0
    highlighted = 0
    for start, stop, idx, stmt in ranges:
        if start < cursor or start < occupied_until:
            continue
        parts.append(escape(text[cursor:start]))
        label = escape(_statement_label(stmt), quote=True)
        quote_html = escape(text[start:stop])
        parts.append(
            f'<span class="dna-quote-highlight" title="{label}" data-quote-index="{idx + 1}">'
            f"{quote_html}</span>"
        )
        cursor = stop
        occupied_until = stop
        highlighted += 1

    parts.append(escape(text[cursor:]))
    return "".join(parts), highlighted


def build_statement_cards(article, status_filter: str = "semua") -> list[dict]:
    cards = []
    for stmt in _filtered_statements(article, status_filter):
        cards.append(
            {
                "quote": getattr(stmt, "quote", "") or "",
                "actor": getattr(stmt, "actor", "") or "-",
                "organization": getattr(stmt, "organization", "") or "-",
                "concept": getattr(stmt, "concept", "") or "-",
                "status": getattr(stmt, "status", "") or "-",
                "confidence": getattr(stmt, "confidence", 0),
                "paragraph_index": getattr(stmt, "paragraph_index", 0),
            }
        )
    return cards
