import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable


ATTR_VERBS = [
    "kata", "ujar", "ucap", "tutur", "jelas", "menurut",
    "menyebut", "mengatakan", "menegaskan", "menilai",
    "menambahkan", "tulis", "ungkap", "papar", "tegas",
    "tandas", "nyata", "bilang", "sebut", "imbuh", "tambah",
    "lanjut", "terang", "cerita", "sampaikan", "nyatakan",
    "tegaskan", "jelaskan",
]

NOISE_QUOTES = {
    "global geopark",
    "papua bukan tanah kosong",
    "save raja ampat",
    "#saverajaampat",
}

METADATA_KEYS = {"title:", "author:", "date:", "type:", "link:", "text:", "source:"}

ROLE_TITLES = [
    "Menteri", "Wakil Menteri", "Direktur Jenderal", "Direktur",
    "Ketua", "Wakil Ketua", "Sekretaris Jenderal", "Sekjen",
    "Kepala", "Wakil", "Gubernur", "Bupati", "Walikota",
    "Anggota", "Juru Bicara", "Koordinator", "Presiden",
    "Komisaris", "Ketum", "Bendahara", "Staf Khusus",
    "Deputi", "Inspektur", "Plt", "Pj",
]


@dataclass
class CodingStatement:
    article_index: int = 0
    paragraph_index: int = 0
    quote: str = ""
    actor: str = ""
    organization: str = ""
    role: str = ""
    concept: str = ""
    stance: str = "netral"
    confidence: float = 0.5
    status: str = "review"
    validated: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class NewsArticle:
    title: str = ""
    date: str = ""
    author: str = ""
    source: str = ""
    link: str = ""
    full_text: str = ""
    body_text: str = ""
    paragraphs: list = field(default_factory=list)
    statements: list = field(default_factory=list)


class NewsAnalyzer:
    def __init__(self, settings: dict):
        self.settings = settings
        self.attribution_verbs = settings.get("attribution_verbs", ATTR_VERBS)
        self.min_quote_length = settings.get("min_quote_length", 20)
        self.concept_keywords = settings.get("concept_keywords", {})
        self.negative_indicators = settings.get("negative_indicators", [])
        self.positive_indicators = settings.get("positive_indicators", [])
        self.known_organizations = settings.get("known_organizations", {})
        self.manual_actors = settings.get("manual_actors", [])
        self.manual_concepts = settings.get("manual_concepts", [])
        self._affixed_verbs = None

    # ── public API ─────────────────────────────────────────────

    def analyze_bulk(
        self,
        text: str,
        progress_callback: Optional[Callable] = None,
    ) -> list:
        """Split text into BERITA sections and analyze each."""
        raw_articles = self._split_articles(text)
        results = []
        total = len(raw_articles)

        for i, (meta, body) in enumerate(raw_articles):
            def _cb(pct, msg, _i=i, _t=total):
                if progress_callback:
                    overall = (_i / _t + pct / 100 / _t) * 100
                    progress_callback(overall, f"Berita {_i+1}/{_t}: {msg}")

            article = self.analyze(
                body, article_index=i, metadata=meta, progress_callback=_cb
            )
            results.append(article)

        return results

    def analyze(
        self,
        text: str,
        article_index: int = 0,
        metadata: Optional[dict] = None,
        progress_callback: Optional[Callable] = None,
    ) -> NewsArticle:
        article = NewsArticle(full_text=text)

        # Step 1: preprocess (0%)
        if progress_callback:
            progress_callback(0, "Membaca teks...")

        if metadata:
            article.title = metadata.get("title", "")
            article.date = metadata.get("date", "")
            article.author = metadata.get("author", "")
            article.link = metadata.get("link", "")
            article.source = metadata.get("source", "")
            article.body_text = metadata.get("body", text)
        else:
            extracted_meta, body = self._strip_metadata(text)
            article.title = extracted_meta.get("title", "")
            article.date = extracted_meta.get("date", "")
            article.author = extracted_meta.get("author", "")
            article.link = extracted_meta.get("link", "")
            article.body_text = body
            if not article.title:
                self._extract_title_fallback(article)
            if not article.date:
                self._extract_date_fallback(article)

        # Step 2: split paragraphs (20%)
        if progress_callback:
            progress_callback(20, "Memecah paragraf...")
        article.paragraphs = self._split_paragraphs(article.body_text)

        # Step 3: find all quotes (40%)
        if progress_callback:
            progress_callback(40, "Mencari kutipan...")
        raw_quotes = []
        for i, para in enumerate(article.paragraphs):
            raw_quotes.extend(self._find_quotes(para, i))

        # Step 4: detect speakers (60%)
        if progress_callback:
            progress_callback(60, "Mendeteksi aktor...")
        for q in raw_quotes:
            para = article.paragraphs[q["paragraph_index"]]
            actor, role, org = self._detect_speaker(para, q["quote"])
            q["actor"] = actor
            q["role"] = role
            q["organization"] = org

        # Step 5: validate + build statements (80%)
        if progress_callback:
            progress_callback(80, "Memfilter & membuat coding statement...")
        for q in raw_quotes:
            status = self._validate_quote(q)
            concept = self._detect_concept(q["quote"])
            stance = self._detect_stance(q["quote"])
            confidence = self._score_confidence(q, status)

            stmt = CodingStatement(
                article_index=article_index,
                paragraph_index=q["paragraph_index"],
                quote=q["quote"],
                actor=self._clean_actor_name(q["actor"]),
                organization=q["organization"],
                role=q["role"],
                concept=concept,
                stance=stance,
                confidence=confidence,
                status=status,
            )
            article.statements.append(stmt)

        # Step 6: done (100%)
        if progress_callback:
            progress_callback(100, "Analisis selesai!")

        return article

    # ── Step 1: article splitting ──────────────────────────────

    def _split_articles(self, text: str) -> list:
        """Split bulk text by 'BERITA N' markers. Returns [(metadata, body), ...]."""
        pattern = r"(?:^|\n)\s*BERITA\s+(\d+)\s*:?\s*\n"
        parts = re.split(pattern, text, flags=re.IGNORECASE)

        if len(parts) <= 1:
            meta, body = self._strip_metadata(text)
            return [(meta, body)]

        results = []
        # parts[0] = text before first BERITA marker (usually empty)
        # parts[1] = "1", parts[2] = content of BERITA 1
        # parts[3] = "2", parts[4] = content of BERITA 2, etc.
        i = 1
        while i < len(parts) - 1:
            content = parts[i + 1]
            meta, body = self._strip_metadata(content)
            results.append((meta, body))
            i += 2

        return results if results else [(self._strip_metadata(text))]

    def _strip_metadata(self, text: str) -> tuple:
        """Extract metadata lines and return (metadata_dict, clean_body)."""
        meta = {}
        body_lines = []
        in_body = False
        lines = text.split("\n")

        for line in lines:
            stripped = line.strip().lower()

            if stripped == "text:" or stripped == "text :" or stripped.startswith("text:"):
                in_body = True
                # If "text: some content", grab the rest
                rest = line.split(":", 1)[1].strip() if ":" in line else ""
                if rest:
                    body_lines.append(rest)
                continue

            if not in_body:
                matched_key = False
                for key in METADATA_KEYS:
                    if stripped.startswith(key) and key != "text:":
                        k = key.rstrip(":")
                        v = line.split(":", 1)[1].strip() if ":" in line else ""
                        meta[k] = v
                        matched_key = True
                        break
                if not matched_key:
                    body_lines.append(line)
            else:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()
        meta["body"] = body
        return meta, body

    def _extract_title_fallback(self, article: NewsArticle):
        """Fallback: first non-empty substantial line as title."""
        for line in article.full_text.strip().split("\n"):
            line = line.strip()
            if line and len(line) > 5 and not any(
                line.lower().startswith(k) for k in METADATA_KEYS
            ):
                article.title = line
                break

    def _extract_date_fallback(self, article: NewsArticle):
        date_patterns = [
            r"(\d{1,2}\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{4})",
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, article.full_text, re.IGNORECASE)
            if match:
                article.date = match.group(1)
                break

    # ── Step 2: paragraphs ─────────────────────────────────────

    def _split_paragraphs(self, text: str) -> list:
        paragraphs = []
        for para in re.split(r"\n\s*\n|\n", text):
            para = para.strip()
            if para and len(para) > 10:
                paragraphs.append(para)
        return paragraphs

    # ── Step 3: quote detection ────────────────────────────────

    def _find_quotes(self, paragraph: str, paragraph_index: int) -> list:
        quotes = []
        patterns = [
            r"“([^”]+)”",  # smart double ""
            r'"([^"]+)"',                  # straight double ""
            r"‘([^’]+)’",  # smart single ''
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, paragraph):
                quote_text = match.group(1).strip()
                if len(quote_text) < 5:
                    continue
                if any(q["quote"] == quote_text for q in quotes):
                    continue
                quotes.append({
                    "quote": quote_text,
                    "paragraph_index": paragraph_index,
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "actor": "",
                    "role": "",
                    "organization": "",
                })

        return quotes

    # ── Step 4: speaker detection ──────────────────────────────

    def _get_affixed_verbs(self) -> list:
        if self._affixed_verbs is not None:
            return self._affixed_verbs

        affixed = set()
        suffixes = ["", "kan", "i", "nya", "lah"]
        nasal_map = {
            "k": "meng", "g": "meng", "h": "meng",
            "t": "men", "d": "men", "c": "men", "j": "men",
            "s": "meny", "p": "mem", "b": "mem",
        }

        for verb in self.attribution_verbs:
            affixed.add(verb)
            for suffix in suffixes:
                affixed.add(verb + suffix)
                for prefix in ["me", "men", "meng", "meny", "mem", "ber", "di", "ter"]:
                    affixed.add(prefix + verb + suffix)
                if verb and verb[0].lower() in nasal_map:
                    nasal_prefix = nasal_map[verb[0].lower()]
                    stem = verb[1:]
                    affixed.add(nasal_prefix + stem + suffix)
                    affixed.add(nasal_prefix + "a" + stem + suffix)

        self._affixed_verbs = sorted(affixed, key=len, reverse=True)
        return self._affixed_verbs

    def _detect_speaker(self, paragraph: str, quote: str) -> tuple:
        """Detect speaker, role, and organization from paragraph context.

        Returns (actor, role, organization).
        Handles patterns:
          - "quote," kata Bahlil.
          - Menurut Arie, "quote"
          - Fanny menjelaskan, "quote"
        """
        actor = ""
        role = ""
        organization = ""

        verbs_pattern = "|".join(re.escape(v) for v in self.attribution_verbs)

        # Pattern A: "quote," verb Name
        # Look for attribution verb + capitalized name AFTER the quote
        pat_a = rf"(?<!\w)(?:{verbs_pattern})\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"
        for match in re.finditer(pat_a, paragraph, re.IGNORECASE):
            name = match.group(1).strip()
            if self._is_valid_name(name):
                actor = name
                break

        # Pattern B: Menurut Name, "quote"
        pat_b = rf"[Mm]enurut\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*,"
        if not actor:
            for match in re.finditer(pat_b, paragraph):
                name = match.group(1).strip()
                if self._is_valid_name(name):
                    actor = name
                    break

        # Pattern C: Name + affixed verb, "quote"
        if not actor:
            affixed = self._get_affixed_verbs()
            affixed_pattern = "|".join(re.escape(v) for v in affixed)
            pat_c = (
                rf"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"
                rf"\s+(?:{affixed_pattern})(?!\w)"
            )
            for match in re.finditer(pat_c, paragraph):
                name = match.group(1).strip()
                if self._is_valid_name(name):
                    actor = name
                    break

        # Fallback: manual actors list
        if not actor:
            for manual_actor in self.manual_actors:
                if manual_actor in paragraph:
                    actor = manual_actor
                    break

        # Detect role + organization
        if actor:
            role = self._detect_role(paragraph, actor)
            organization = self._detect_organization(paragraph, actor)

        return actor, role, organization

    def _is_valid_name(self, name: str) -> bool:
        noise = {
            "yang", "dan", "atau", "ini", "itu", "dari", "untuk",
            "dengan", "pada", "ke", "di", "se", "hal", "pihak",
            "kami", "kita", "mereka", "saya", "anda",
            "bahwa", "akan", "sudah", "telah", "bisa",
            "dalam", "antara", "oleh", "namun", "tetapi",
        }
        if name.lower() in noise:
            return False
        if len(name) < 2:
            return False
        if not name[0].isupper():
            return False
        return True

    def _clean_actor_name(self, name: str) -> str:
        if not name:
            return name
        name = name.strip()
        # Remove trailing context phrases
        name = re.sub(
            r"\s+(?:dari|di|yang|untuk|dalam|kepada|melalui|saat|ketika|pada|dengan)\s+.*$",
            "", name, flags=re.IGNORECASE,
        )
        # Remove trailing prepositions left over
        name = re.sub(
            r"\s+(?:dari|di|yang|untuk|dalam|kepada)\s*$", "", name,
            flags=re.IGNORECASE,
        )
        # Remove parenthetical like "()" or "(123)"
        name = re.sub(r"\s*\([^)]*\)\s*", "", name)
        # Remove trailing punctuation
        name = re.sub(r"[,\.\;:]+$", "", name)
        return name.strip()

    def _detect_role(self, paragraph: str, actor: str) -> str:
        """Detect role/title like 'Kepala Divisi Kampanye'."""
        titles_pattern = "|".join(re.escape(t) for t in ROLE_TITLES)
        patterns = [
            rf"{re.escape(actor)}\s*,?\s*({titles_pattern}(?:\s+[A-Za-z]+){{0,5}})",
            rf"({titles_pattern}(?:\s+[A-Za-z]+){{0,5}})\s*,?\s*{re.escape(actor)}",
        ]
        for pat in patterns:
            match = re.search(pat, paragraph)
            if match:
                role = match.group(1).strip()
                role = re.sub(r"[,\.]$", "", role).strip()
                if len(role) > 3:
                    return role
        return ""

    def _detect_organization(self, paragraph: str, actor: str) -> str:
        for org_key, org_name in self.known_organizations.items():
            if org_key.lower() in paragraph.lower():
                return org_name

        # "dari Organization" pattern
        pat = rf"(?:{re.escape(actor)}|dia|ia)\s+dari\s+([A-Z][^\.,;]+)"
        match = re.search(pat, paragraph)
        if match:
            return match.group(1).strip()

        return ""

    # ── Step 5: validation & filtering ─────────────────────────

    def _validate_quote(self, quote_info: dict) -> str:
        """Assign status: valid, review, reject."""
        quote = quote_info["quote"]
        actor = quote_info["actor"]
        q_lower = quote.lower().strip()

        # REJECT: known noise
        if q_lower in NOISE_QUOTES:
            return "reject"

        # REJECT: too short (slogans, terms, labels)
        if len(quote) < self.min_quote_length:
            return "reject"

        # REJECT: looks like a hashtag or all caps slogan
        if quote.startswith("#") or (quote.isupper() and len(quote) < 50):
            return "reject"

        # REJECT: no words, just numbers or symbols
        word_count = len(re.findall(r"[a-zA-Z]{2,}", quote))
        if word_count < 3:
            return "reject"

        # REJECT: looks like a title/banner (no verb, no clause structure)
        if len(quote) < 40 and not re.search(r"[a-z]", quote):
            return "reject"

        # No actor → review
        if not actor:
            return "review"

        # Actor found but no clear opinion/claim → review
        if not self._has_opinion_content(quote):
            return "review"

        return "valid"

    def _has_opinion_content(self, quote: str) -> bool:
        """Check if quote contains opinion, position, or claim language."""
        q = quote.lower()
        opinion_markers = [
            "harus", "perlu", "penting", "seharusnya", "sebaiknya",
            "kami", "kita", "saya", "kami akan", "pemerintah",
            "menolak", "mendukung", "setuju", "tidak setuju",
            "sangat", "terlalu", "justru", "memang", "tetapi",
            "akan", "sudah", "belum", "bisa", "tidak",
            "kebijakan", "program", "rencana",
            "masalah", "solusi", "dampak", "risiko",
            "bertentangan", "melanggar", "sesuai",
        ]
        return any(m in q for m in opinion_markers)

    def _score_confidence(self, quote_info: dict, status: str) -> float:
        """Score confidence based on clarity of attribution."""
        if status == "reject":
            return 0.1

        score = 0.0
        quote = quote_info["quote"]
        actor = quote_info["actor"]

        # Has clear actor name
        if actor and len(actor) > 2:
            score += 0.4
        elif actor:
            score += 0.2

        # Has organization
        if quote_info.get("organization"):
            score += 0.1

        # Has role
        if quote_info.get("role"):
            score += 0.1

        # Quote length (longer = more likely real statement)
        if len(quote) > 80:
            score += 0.2
        elif len(quote) > 40:
            score += 0.1

        # Has opinion content
        if self._has_opinion_content(quote):
            score += 0.2

        return min(round(score, 2), 1.0)

    # ── Step 6: concept & stance ───────────────────────────────

    def _detect_concept(self, quote: str) -> str:
        q = quote.lower()
        scores = {}
        for concept, keywords in self.concept_keywords.items():
            score = sum(1 for kw in keywords if kw.lower() in q)
            if score > 0:
                scores[concept] = score
        for concept in self.manual_concepts:
            if concept.lower() in q:
                scores[concept] = scores.get(concept, 0) + 2
        if scores:
            return max(scores, key=scores.get)
        return "Umum"

    def _detect_stance(self, quote: str) -> str:
        q = quote.lower()
        neg = sum(1 for w in self.negative_indicators if w in q)
        pos = sum(1 for w in self.positive_indicators if w in q)
        if neg > pos:
            return "kontra"
        if pos > neg:
            return "pro"
        return "netral"
