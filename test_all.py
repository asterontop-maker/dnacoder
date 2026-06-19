import sys
import json
import os
import sqlite3
import traceback

results = []


def test(name, fn):
    try:
        fn()
        results.append((name, "PASS"))
        print(f"  PASS: {name}")
    except Exception as e:
        results.append((name, f"FAIL: {e}"))
        print(f"  FAIL: {name} -> {e}")
        traceback.print_exc()


with open("settings.json", "r", encoding="utf-8") as f:
    settings = json.load(f)


# ── Analyzer tests ─────────────────────────────────────────────

def t_split_paragraphs():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    paras = a._split_paragraphs("Paragraf satu cukup panjang.\n\nParagraf dua juga panjang.\n\nParagraf tiga juga.")
    assert len(paras) == 3, f"Expected 3, got {len(paras)}"

test("Analyzer: split paragraphs", t_split_paragraphs)


def t_find_quotes():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    quotes = a._find_quotes(
        'Dia berkata "ini adalah kutipan penting untuk dianalisis" kepada wartawan.', 0
    )
    assert len(quotes) == 1, f"Expected 1, got {len(quotes)}"

test("Analyzer: find quotes", t_find_quotes)


def t_smart_quotes():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    quotes = a._find_quotes(
        "“Ini kutipan dengan smart quotes yang panjang sekali” kata dia.", 0
    )
    assert len(quotes) == 1, f"Expected 1, got {len(quotes)}"

test("Analyzer: smart quotes", t_smart_quotes)


def t_actor_verb_name():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    actor, role, org = a._detect_speaker(
        '"Kami siap melaksanakan itu," kata Bahlil Lahadalia, Menteri ESDM.',
        "Kami siap",
    )
    assert actor == "Bahlil Lahadalia", f"Got {actor}"

test("Speaker: verb+Name pattern", t_actor_verb_name)


def t_actor_name_verb():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    actor, role, org = a._detect_speaker(
        "Bahlil mengatakan hal tersebut dalam konferensi pers.", "hal tersebut"
    )
    assert "Bahlil" in actor, f"Got '{actor}'"

test("Speaker: Name+verb pattern", t_actor_name_verb)


def t_actor_menurut():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    actor, role, org = a._detect_speaker(
        'Menurut Arie Sujito, "kebijakan ini harus direvisi untuk kepentingan rakyat."',
        "kebijakan ini harus direvisi",
    )
    assert "Arie" in actor, f"Got '{actor}'"

test("Speaker: Menurut pattern", t_actor_menurut)


def t_detect_org():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    _, _, org = a._detect_speaker(
        '"Kami akan terus berjuang," jelas Bondan dari Greenpeace Indonesia.', "Kami akan terus berjuang"
    )
    assert org == "Greenpeace", f"Got '{org}'"

test("Speaker: detect organization", t_detect_org)


def t_detect_concept():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    concept = a._detect_concept("Deforestasi hutan dan pencemaran lingkungan harus dihentikan")
    assert concept == "Lingkungan", f"Got '{concept}'"

test("Concept detection", t_detect_concept)


def t_stance_pro():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    assert a._detect_stance("Kami mendukung kebijakan ini") == "pro"

test("Stance: pro", t_stance_pro)


def t_stance_kontra():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    assert a._detect_stance("Kami menolak rencana tersebut") == "kontra"

test("Stance: kontra", t_stance_kontra)


# ── Validation tests ───────────────────────────────────────────

def t_reject_short():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    status = a._validate_quote({"quote": "global geopark", "actor": ""})
    assert status == "reject", f"Got '{status}'"

test("Filter: reject short/noise", t_reject_short)


def t_reject_no_actor():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    status = a._validate_quote({
        "quote": "Ini kutipan panjang tapi tidak ada aktor yang mengatakannya di paragraf ini sama sekali",
        "actor": "",
    })
    assert status == "review", f"Got '{status}'"

test("Filter: review if no actor", t_reject_no_actor)


def t_valid_statement():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    status = a._validate_quote({
        "quote": "Pemerintah harus segera mencabut izin tambang di kawasan konservasi",
        "actor": "Fanny",
    })
    assert status == "valid", f"Got '{status}'"

test("Filter: valid statement", t_valid_statement)


# ── Article splitting ──────────────────────────────────────────

def t_split_berita():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    text = """BERITA 1 :

title: Judul Satu
author: Penulis A
date: 1 Juni 2025

text:

Paragraf pertama berita satu cukup panjang.

"Kami harus bertindak segera untuk menyelamatkan lingkungan," kata Budi.

BERITA 2 :

title: Judul Dua
author: Penulis B
date: 2 Juni 2025

text:

Paragraf pertama berita dua yang juga panjang.

"Ekonomi harus tetap tumbuh dengan baik dan kuat," ujar Siti.
"""
    parts = a._split_articles(text)
    assert len(parts) == 2, f"Expected 2 articles, got {len(parts)}"
    assert parts[0][0].get("title") == "Judul Satu"
    assert parts[1][0].get("title") == "Judul Dua"

test("Split BERITA sections", t_split_berita)


def t_strip_metadata():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    text = """title: Kronologi Tambang
author: Ahmad
date: 9 Juni 2025
type: online news
link: https://example.com

text:

Paragraf pertama berita ini cukup panjang.

"Kutipan penting dalam berita ini," kata Menteri."""
    meta, body = a._strip_metadata(text)
    assert meta["title"] == "Kronologi Tambang"
    assert meta["author"] == "Ahmad"
    assert "title:" not in body
    assert "Paragraf pertama" in body

test("Strip metadata", t_strip_metadata)


# ── Full pipeline ──────────────────────────────────────────────

def t_full_pipeline():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    text = (
        "Berita Uji Coba\n"
        "20 Juni 2026\n\n"
        '"Investasi di sektor energi terbarukan sangat penting untuk Indonesia," kata Menteri Bahlil, Kementerian ESDM.\n\n'
        '"Kami menolak pembangunan PLTU baru di kawasan konservasi yang dilindungi," jelas Wahyu dari Walhi.\n\n'
        '"global geopark"\n\n'
        '"Papua bukan tanah kosong"'
    )
    article = a.analyze(text, article_index=0)
    valid = [s for s in article.statements if s.status == "valid"]
    reject = [s for s in article.statements if s.status == "reject"]
    assert len(valid) == 2, f"Expected 2 valid, got {len(valid)}"
    assert len(reject) >= 1, f"Expected >= 1 reject, got {len(reject)}"

test("Full pipeline: valid vs reject", t_full_pipeline)


def t_bulk_analysis():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    text = """BERITA 1 :

title: Berita Pertama
date: 1 Juni 2025

text:

Pemerintah mengumumkan kebijakan baru untuk sektor pertambangan.

"Kami akan mencabut izin perusahaan yang melanggar aturan lingkungan," kata Prasetyo Hadi, Menteri Sekretaris Negara.

BERITA 2 :

title: Berita Kedua
date: 2 Juni 2025

text:

Reaksi masyarakat terhadap kebijakan pertambangan sangat beragam.

"Pencabutan izin tambang memang langkah baik untuk konservasi," jelas Fanny dari Walhi.
"""
    articles = a.analyze_bulk(text)
    assert len(articles) == 2, f"Expected 2, got {len(articles)}"
    assert articles[0].title == "Berita Pertama"
    total_valid = sum(1 for a in articles for s in a.statements if s.status == "valid")
    assert total_valid == 2, f"Expected 2 valid, got {total_valid}"

test("Bulk analysis (BERITA split)", t_bulk_analysis)


# ── Confidence scoring ─────────────────────────────────────────

def t_confidence_high():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Test\n\n"Pemerintah harus segera mencabut izin tambang di kawasan konservasi yang dilindungi," kata Budi dari Greenpeace Indonesia.',
        0,
    )
    valid = [s for s in article.statements if s.status == "valid"]
    if valid:
        assert valid[0].confidence >= 0.8, f"Got {valid[0].confidence}"

test("Confidence: high for clear attribution", t_confidence_high)


def t_confidence_low():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    score = a._score_confidence({"quote": "pendek", "actor": "", "organization": "", "role": ""}, "review")
    assert score < 0.5, f"Got {score}"

test("Confidence: low for ambiguous", t_confidence_low)


# ── Exporter tests ─────────────────────────────────────────────

def t_export_csv():
    from analyzer import NewsAnalyzer
    from exporter import Exporter
    import pandas as pd
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Test\n\n"Kutipan test yang cukup panjang untuk dianalisis dengan baik," kata Budi.', 0
    )
    exp = Exporter("output")
    path = exp.export_csv([article], "test_auto.csv")
    assert os.path.exists(path)
    df = pd.read_csv(path)
    assert "speaker" in df.columns
    assert "status" in df.columns

test("Exporter: CSV with new columns", t_export_csv)


def t_export_valid_only():
    from analyzer import NewsAnalyzer
    from exporter import Exporter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Test\n\n"Pemerintah harus bertindak segera untuk rakyat," kata Budi.\n\n"slogan"', 0
    )
    exp = Exporter("output")
    df_valid = exp.statements_to_dataframe([article], status_filter="valid")
    df_all = exp.statements_to_dataframe([article])
    assert len(df_valid) <= len(df_all)

test("Exporter: status filter", t_export_valid_only)


# ── DNA tests ──────────────────────────────────────────────────

def t_dna_read():
    from analyzer import NewsAnalyzer
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Read Test\n\n"Pemerintah harus segera bertindak untuk lingkungan," kata Budi.', 0
    )
    DnaWriter.write([article], "output/test_read_fixture.dna")
    data = DnaWriter.read("output/test_read_fixture.dna")
    assert len(data["documents"]) == 1
    assert len(data["statements"]) >= 1
    assert data["statements"][0]["person"] == "Budi"

test("DnaWriter: read .dna", t_dna_read)


def t_dna_write():
    from analyzer import NewsAnalyzer
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'DNA Test\n\n"Pemerintah harus segera mencabut izin tambang yang merusak lingkungan," kata Budi dari Walhi.', 0
    )
    ok = DnaWriter.write([article], "output/test_write.dna")
    assert ok
    with sqlite3.connect("output/test_write.dna") as conn:
        password = conn.execute("SELECT Password FROM CODERS WHERE ID = 1").fetchone()[0]
        version = conn.execute("SELECT Value FROM SETTINGS WHERE Property = 'version'").fetchone()[0]
    assert len(password) > 40, "Coder password must be a Jasypt hash, not empty/plaintext"
    assert version == "3.0"

test("DnaWriter: write .dna", t_dna_write)


def t_dna_write_custom_coder():
    from analyzer import NewsAnalyzer
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'DNA Test\n\n"Kutipan untuk memastikan akun coder bisa diganti dari panel export," kata Rina.', 0
    )
    ok = DnaWriter.write(
        [article],
        "output/test_custom_coder.dna",
        coder_name="Rina Coder",
        coder_password="rahasia123",
    )
    assert ok
    with sqlite3.connect("output/test_custom_coder.dna") as conn:
        name, password = conn.execute("SELECT Name, Password FROM CODERS WHERE ID = 1").fetchone()
    assert name == "Rina Coder"
    assert password != "rahasia123"
    assert len(password) > 40

test("DnaWriter: custom coder account", t_dna_write_custom_coder)


def t_dna_write_custom_database_version():
    from analyzer import NewsAnalyzer
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'DNA Test\n\n"Kutipan untuk memastikan versi database bisa dipilih saat export," kata Rina.', 0
    )
    ok = DnaWriter.write(
        [article],
        "output/test_custom_version.dna",
        database_version="3.1.0",
    )
    assert ok
    with sqlite3.connect("output/test_custom_version.dna") as conn:
        version = conn.execute("SELECT Value FROM SETTINGS WHERE Property = 'version'").fetchone()[0]
    assert version == "3.1.0"

test("DnaWriter: custom database version", t_dna_write_custom_database_version)


def t_dna_roundtrip():
    from analyzer import NewsAnalyzer
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Roundtrip\n\n"Kutipan roundtrip harus sama setelah baca tulis untuk validasi," jelas Andi.', 0
    )
    DnaWriter.write([article], "output/test_roundtrip.dna")
    data = DnaWriter.read("output/test_roundtrip.dna")
    assert len(data["statements"]) >= 1
    assert "roundtrip" in data["statements"][0]["quote"].lower()

test("DnaWriter: roundtrip", t_dna_roundtrip)


def t_dna_skip_reject():
    from analyzer import NewsAnalyzer, CodingStatement
    from dna_writer import DnaWriter
    a = NewsAnalyzer(settings)
    article = a.analyze(
        'Test\n\n"Pemerintah harus segera bertindak untuk lingkungan," kata Budi.\n\n"slogan pendek"', 0
    )
    DnaWriter.write([article], "output/test_skip_reject.dna")
    data = DnaWriter.read("output/test_skip_reject.dna")
    for s in data["statements"]:
        assert len(s["quote"]) > 15, f"Reject quote leaked: {s['quote']}"

test("DnaWriter: skip rejected", t_dna_skip_reject)


# Quote preview tests

def t_quote_preview_highlights_quotes():
    from analyzer import NewsArticle, CodingStatement
    from preview_utils import build_article_preview_html

    article = NewsArticle(
        title="Preview",
        full_text='Pembuka.\n"Kutipan penting untuk dilihat," kata Budi.\nPenutup.',
    )
    article.statements.append(
        CodingStatement(
            quote="Kutipan penting untuk dilihat,",
            actor="Budi",
            status="valid",
            confidence=0.91,
        )
    )

    html_text, count = build_article_preview_html(article, "valid")
    assert count == 1
    assert "dna-quote-highlight" in html_text
    assert "Kutipan penting untuk dilihat," in html_text
    assert "Budi" in html_text

test("Quote preview: highlights quotes", t_quote_preview_highlights_quotes)


# ── Clean actor name ───────────────────────────────────────────

def t_clean_actor():
    from analyzer import NewsAnalyzer
    a = NewsAnalyzer(settings)
    assert a._clean_actor_name("Bondan Andriyanu dari Greenpeace Indonesia") == "Bondan Andriyanu"
    assert a._clean_actor_name("Wahyu Perdana") == "Wahyu Perdana"

test("Clean actor name", t_clean_actor)


# ── Summary ────────────────────────────────────────────────────
print()
print("=" * 50)
passed = sum(1 for _, r in results if r == "PASS")
failed = sum(1 for _, r in results if r != "PASS")
print(f"RESULTS: {passed} passed, {failed} failed out of {len(results)}")
if failed:
    print()
    for name, r in results:
        if r != "PASS":
            print(f"  FAIL: {name} -> {r}")
    sys.exit(1)
print("ALL TESTS PASSED")
