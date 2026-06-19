import importlib
import sys
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import time
from pathlib import Path
from datetime import datetime

# Force-reload modules to avoid stale bytecode
for mod_name in ["analyzer", "exporter", "scraper", "dna_writer"]:
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])

from analyzer import NewsAnalyzer, NewsArticle, CodingStatement
from exporter import Exporter, AutoSaver
from scraper import fetch_article, read_docx
from dna_writer import DnaWriter
from preview_utils import build_article_preview_html, build_statement_cards

st.set_page_config(
    page_title="AutoDNA Coder",
    page_icon="\U0001f9ec",
    layout="wide",
    initial_sidebar_state="expanded",
)

SETTINGS_PATH = Path("settings.json")


def load_settings():
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ── Session state ──────────────────────────────────────────────
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
if "articles" not in st.session_state:
    st.session_state.articles = []
if "last_save_time" not in st.session_state:
    st.session_state.last_save_time = 0
if "go_to_export" not in st.session_state:
    st.session_state.go_to_export = False

settings = st.session_state.settings
exporter = Exporter("output")
autosaver = AutoSaver()

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Sidebar: Settings ─────────────────────────────────────────
with st.sidebar:
    st.title("Pengaturan")

    mode_options = ["Otomatis Penuh", "Semi Otomatis", "Manual Review"]
    mode_keys = ["auto", "semi", "manual"]
    current_mode = settings.get("analysis_mode", "auto")
    mode_idx = mode_keys.index(current_mode) if current_mode in mode_keys else 0
    mode = st.selectbox("Mode Analisis", mode_options, index=mode_idx)
    settings["analysis_mode"] = mode_keys[mode_options.index(mode)]

    st.divider()

    with st.expander("Kata Kerja Atribusi"):
        verbs = st.text_area(
            "Satu kata per baris",
            value="\n".join(settings.get("attribution_verbs", [])),
            height=150,
        )
        settings["attribution_verbs"] = [v.strip() for v in verbs.split("\n") if v.strip()]

    settings["min_quote_length"] = st.number_input(
        "Panjang Minimum Kutipan (karakter)",
        min_value=1,
        max_value=100,
        value=settings.get("min_quote_length", 10),
    )

    with st.expander("Daftar Aktor Manual"):
        actors_text = st.text_area(
            "Satu nama per baris",
            value="\n".join(settings.get("manual_actors", [])),
            height=100,
        )
        settings["manual_actors"] = [a.strip() for a in actors_text.split("\n") if a.strip()]

    with st.expander("Daftar Konsep Manual"):
        concepts_text = st.text_area(
            "Satu konsep per baris",
            value="\n".join(settings.get("manual_concepts", [])),
            height=100,
        )
        settings["manual_concepts"] = [c.strip() for c in concepts_text.split("\n") if c.strip()]

    st.divider()
    if st.button("Simpan Pengaturan", use_container_width=True):
        save_settings(settings)
        st.success("Pengaturan disimpan!")

    st.divider()
    st.caption(DnaWriter.get_status_message())


# ── Main ───────────────────────────────────────────────────────
st.title("\U0001f9ec AutoDNA Coder")
st.caption("Analisis otomatis kutipan berita untuk Discourse Network Analyzer")

tab_input, tab_results, tab_export = st.tabs(
    ["Input Berita", "Hasil Analisis", "Export"]
)

if st.session_state.go_to_export:
    st.session_state.go_to_export = False
    components.html(
        """
        <script>
        setTimeout(() => {
            const tabs = Array.from(
                window.parent.document.querySelectorAll('button[role="tab"]')
            );
            const exportTab = tabs.find((tab) => tab.innerText.trim() === "Export");
            if (exportTab) {
                exportTab.click();
            }
        }, 150);
        </script>
        """,
        height=0,
    )


# ── helpers ────────────────────────────────────────────────────
def _run_analysis(texts: list[str], sources: list[str] | None = None):
    """Analyze a list of raw texts and store results."""
    analyzer = NewsAnalyzer(settings)
    articles = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, text in enumerate(texts):
        status_text.text(f"Menganalisis berita {i + 1}/{len(texts)}...")

        def _cb(pct, msg, _i=i, _n=len(texts)):
            progress_bar.progress(min((_i + pct / 100) / _n, 1.0))
            status_text.text(f"Berita {_i + 1}: {msg}")

        article = analyzer.analyze(text, article_index=i, progress_callback=_cb)
        if sources and i < len(sources):
            article.source = sources[i]
        articles.append(article)

    st.session_state.articles = articles
    autosaver.save(articles)
    st.session_state.last_save_time = time.time()

    # Automatic export to output folder
    try:
        exporter.export_csv(articles)
        exporter.export_json(articles)
        try:
            exporter.export_graphml(articles)
        except ImportError:
            pass  # Skip GraphML if networkx not available
    except Exception as e:
        st.warning(f"Error saving to output: {e}")

    valid = sum(1 for a in articles for s in a.statements if s.status == "valid")
    review = sum(1 for a in articles for s in a.statements if s.status == "review")
    reject = sum(1 for a in articles for s in a.statements if s.status == "reject")
    progress_bar.progress(1.0)
    status_text.text(
        f"Selesai! Valid: {valid} | Review: {review} | Reject: {reject} | Tersimpan di output/"
    )
    time.sleep(0.5)
    st.session_state.go_to_export = True
    st.rerun()


def _run_bulk_analysis(text: str):
    """Analyze text that may contain BERITA 1, BERITA 2, etc."""
    analyzer = NewsAnalyzer(settings)
    progress_bar = st.progress(0)
    status_text = st.empty()

    def _cb(pct, msg):
        progress_bar.progress(min(pct / 100, 1.0))
        status_text.text(msg)

    articles = analyzer.analyze_bulk(text, progress_callback=_cb)

    st.session_state.articles = articles
    autosaver.save(articles)
    st.session_state.last_save_time = time.time()

    # Automatic export to output folder
    try:
        exporter.export_csv(articles)
        exporter.export_json(articles)
        try:
            exporter.export_graphml(articles)
        except ImportError:
            pass  # Skip GraphML if networkx not available
    except Exception as e:
        st.warning(f"Error saving to output: {e}")

    valid = sum(1 for a in articles for s in a.statements if s.status == "valid")
    review = sum(1 for a in articles for s in a.statements if s.status == "review")
    reject = sum(1 for a in articles for s in a.statements if s.status == "reject")
    progress_bar.progress(1.0)
    status_text.text(
        f"Selesai! Valid: {valid} | Review: {review} | Reject: {reject} | Tersimpan di output/"
    )
    time.sleep(0.5)
    st.session_state.go_to_export = True
    st.rerun()


def _render_quote_preview(
    articles: list[NewsArticle],
    status_filter: str,
    key_prefix: str = "results",
):
    article_options = [
        f"{i + 1}. {article.title or '(Tanpa Judul)'}" for i, article in enumerate(articles)
    ]
    article_index = st.selectbox(
        "Artikel",
        range(len(article_options)),
        format_func=lambda idx: article_options[idx],
        key=f"{key_prefix}_quote_preview_article",
    )
    article = articles[article_index]
    preview_html, highlighted = build_article_preview_html(article, status_filter)
    cards = build_statement_cards(article, status_filter)

    left, right = st.columns([2.4, 1])
    with left:
        st.caption(f"Highlight: {highlighted} kutipan")
        components.html(
            f"""
            <style>
                .dna-preview-shell {{
                    height: 520px;
                    overflow: auto;
                    border: 1px solid #8d8d8d;
                    background: #f7f7f3;
                    color: #111;
                    padding: 10px 12px;
                    font-family: "Courier New", monospace;
                    font-size: 14px;
                    line-height: 1.45;
                    white-space: pre-wrap;
                }}
                .dna-quote-highlight {{
                    background: #ffe24a;
                    box-decoration-break: clone;
                    -webkit-box-decoration-break: clone;
                    padding: 0 2px;
                }}
            </style>
            <div class="dna-preview-shell">{preview_html}</div>
            """,
            height=550,
            scrolling=False,
        )

    with right:
        st.caption(f"Daftar kutipan: {len(cards)}")
        if not cards:
            st.info("Belum ada kutipan untuk filter ini.")
        for idx, card in enumerate(cards, 1):
            with st.expander(f"{idx}. {card['actor']} | {card['status']}", expanded=idx == 1):
                st.write(card["quote"])
                st.caption(
                    f"Org: {card['organization']} | Konsep: {card['concept']} | "
                    f"Confidence: {card['confidence']:.2f} | Paragraf: {card['paragraph_index'] + 1}"
                )


# ── Tab: Input ─────────────────────────────────────────────────
with tab_input:
    input_method = st.radio(
        "Metode Input",
        ["Teks Langsung", "Upload File", "Link Berita", "Import .dna"],
        horizontal=True,
    )

    if input_method == "Teks Langsung":
        news_text = st.text_area(
            "Masukkan teks berita (pisahkan beberapa berita dengan '===')",
            height=300,
            placeholder="Tempel teks berita di sini...\n\n===\n\nBerita kedua...",
        )
        if st.button("Analisis", type="primary", use_container_width=True):
            if news_text.strip():
                texts = [t.strip() for t in news_text.split("===") if t.strip()]
                _run_analysis(texts)
            else:
                st.warning("Masukkan teks berita terlebih dahulu.")

        if st.session_state.articles:
            st.divider()
            st.markdown("**Preview Kutipan**")
            input_preview_filter = st.selectbox(
                "Status preview",
                ["valid", "review", "reject", "semua"],
                index=0,
                key="input_quote_preview_status",
            )
            _render_quote_preview(
                st.session_state.articles,
                input_preview_filter,
                key_prefix="input",
            )

    elif input_method == "Upload File":
        uploaded = st.file_uploader(
            "Upload file berita",
            type=["txt", "docx", "csv", "dna"],
            accept_multiple_files=True,
        )
        if uploaded and st.button("Analisis File", type="primary", use_container_width=True):
            texts = []
            sources = []
            for file in uploaded:
                if file.name.endswith(".txt"):
                    texts.append(file.read().decode("utf-8", errors="ignore"))
                    sources.append(file.name)
                elif file.name.endswith(".csv"):
                    df = pd.read_csv(file)
                    text_col = None
                    for col in df.columns:
                        if any(k in col.lower() for k in ["text", "teks", "berita", "content", "isi"]):
                            text_col = col
                            break
                    if not text_col:
                        text_col = df.columns[0]
                    for _, row in df.iterrows():
                        texts.append(str(row[text_col]))
                        sources.append(file.name)
                elif file.name.endswith(".docx"):
                    import tempfile
                    import os

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                        tmp.write(file.read())
                        tmp_path = tmp.name
                    content = read_docx(tmp_path)
                    os.unlink(tmp_path)
                    if content:
                        texts.append(content)
                        sources.append(file.name)
                    else:
                        st.error(f"Gagal membaca {file.name}")
                elif file.name.endswith(".dna"):
                    import tempfile
                    import os

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".dna") as tmp:
                        tmp.write(file.read())
                        tmp_path = tmp.name
                    try:
                        data = DnaWriter.read(tmp_path)
                        for doc_id, doc in data["documents"].items():
                            texts.append(doc["text"])
                            sources.append(f"{file.name}:{doc['title']}")
                    except Exception as e:
                        st.error(f"Gagal membaca {file.name}: {e}")
                    os.unlink(tmp_path)
            if texts:
                _run_analysis(texts, sources)

    elif input_method == "Link Berita":
        urls_text = st.text_area(
            "Masukkan URL berita (satu per baris)",
            height=150,
            placeholder="https://example.com/berita-1\nhttps://example.com/berita-2",
        )
        if st.button("Ambil & Analisis", type="primary", use_container_width=True):
            urls = [u.strip() for u in urls_text.split("\n") if u.strip()]
            if urls:
                texts = []
                sources = []
                fetch_progress = st.progress(0)
                for i, url in enumerate(urls):
                    fetch_progress.progress((i + 1) / len(urls))
                    text = fetch_article(url)
                    if text:
                        texts.append(text)
                        sources.append(url)
                    else:
                        st.warning(f"Gagal mengambil: {url}")
                fetch_progress.empty()
                if texts:
                    _run_analysis(texts, sources)
                else:
                    st.error("Tidak ada berita yang berhasil diambil.")
            else:
                st.warning("Masukkan URL terlebih dahulu.")

    elif input_method == "Import .dna":
        st.markdown("**Import dari file .dna (DNA 3.x SQLite)**")

        # Option 1: Upload file
        dna_upload = st.file_uploader(
            "Upload file .dna", type=["dna"], accept_multiple_files=False
        )

        # Option 2: Pick from input/ folder
        dna_files_in_input = sorted(INPUT_DIR.glob("*.dna"))
        dna_choice = None
        if dna_files_in_input:
            st.markdown("**Atau pilih dari folder `input/`:**")
            dna_choice = st.selectbox(
                "File .dna tersedia",
                [None] + dna_files_in_input,
                format_func=lambda x: "-- pilih --" if x is None else x.name,
            )

        if st.button("Import .dna", type="primary", use_container_width=True):
            dna_path = None

            if dna_upload:
                import tempfile, os
                with tempfile.NamedTemporaryFile(delete=False, suffix=".dna") as tmp:
                    tmp.write(dna_upload.read())
                    dna_path = tmp.name

            elif dna_choice:
                dna_path = str(dna_choice)

            if dna_path:
                try:
                    data = DnaWriter.read(dna_path)
                    loaded_articles = []
                    for doc_id, doc in data["documents"].items():
                        article = NewsArticle(
                            title=doc["title"],
                            date="",
                            author=doc["author"],
                            source=doc["source"],
                            full_text=doc["text"],
                        )
                        article.paragraphs = [
                            p.strip()
                            for p in doc["text"].split("\n")
                            if p.strip() and len(p.strip()) > 5
                        ]
                        for s in data["statements"]:
                            if s["document_id"] == doc_id:
                                agr = s.get("agreement", "Agreement")
                                stance = "kontra" if agr == "Disagreement" else "pro"
                                article.statements.append(
                                    CodingStatement(
                                        article_index=len(loaded_articles),
                                        paragraph_index=0,
                                        quote=s["quote"],
                                        actor=s["person"],
                                        organization=s["organization"],
                                        concept=s["concept"],
                                        stance=stance,
                                        confidence=1.0,
                                        status="valid",
                                        validated=True,
                                    )
                                )
                        loaded_articles.append(article)

                    st.session_state.articles = loaded_articles
                    autosaver.save(loaded_articles)
                    st.session_state.last_save_time = time.time()
                    total = sum(len(a.statements) for a in loaded_articles)
                    st.success(
                        f"Berhasil import {len(loaded_articles)} dokumen, {total} statement."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal membaca .dna: {e}")

                if dna_upload and dna_path:
                    os.unlink(dna_path)
            else:
                st.warning("Pilih atau upload file .dna terlebih dahulu.")


# ── Tab: Results ───────────────────────────────────────────────
with tab_results:
    articles = st.session_state.articles

    if articles:
        all_stmts = [s for a in articles for s in a.statements]
        n_valid = sum(1 for s in all_stmts if s.status == "valid")
        n_review = sum(1 for s in all_stmts if s.status == "review")
        n_reject = sum(1 for s in all_stmts if s.status == "reject")
        unique_actors = {s.actor for s in all_stmts if s.actor and s.status == "valid"}

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Berita", len(articles))
        c2.metric("Valid", n_valid)
        c3.metric("Review", n_review)
        c4.metric("Reject", n_reject)
        c5.metric("Aktor Unik", len(unique_actors))

        st.divider()

        sub_preview, sub_valid, sub_review, sub_reject, sub_all = st.tabs(
            [
                "Preview Kutipan",
                f"Valid ({n_valid})",
                f"Need Review ({n_review})",
                f"Rejected ({n_reject})",
                f"Semua ({len(all_stmts)})",
            ]
        )

        with sub_preview:
            preview_filter = st.selectbox(
                "Status preview",
                ["valid", "review", "reject", "semua"],
                index=0,
                key="quote_preview_status",
            )
            _render_quote_preview(articles, preview_filter, key_prefix="results")

        with sub_valid:
            df_valid = exporter.statements_to_dataframe(articles, status_filter="valid")
            if not df_valid.empty:
                st.dataframe(df_valid, use_container_width=True)
            else:
                st.info("Tidak ada kutipan valid.")

        with sub_review:
            df_review = exporter.statements_to_dataframe(articles, status_filter="review")
            if not df_review.empty:
                st.warning("Kutipan ini perlu review manual — speaker tidak jelas atau kutipan ambigu.")
                st.data_editor(df_review, use_container_width=True, num_rows="fixed", key="review_editor")
            else:
                st.info("Tidak ada kutipan yang perlu review.")

        with sub_reject:
            df_reject = exporter.statements_to_dataframe(articles, status_filter="reject")
            if not df_reject.empty:
                st.caption("Kutipan dibuang: terlalu pendek, slogan, banner, atau tanpa aktor.")
                st.dataframe(df_reject, use_container_width=True)
            else:
                st.info("Tidak ada kutipan yang dibuang.")

        with sub_all:
            df_all = exporter.statements_to_dataframe(articles)
            st.dataframe(df_all, use_container_width=True)

        with st.expander("Detail per Berita"):
            for i, article in enumerate(articles):
                a_valid = sum(1 for s in article.statements if s.status == "valid")
                a_review = sum(1 for s in article.statements if s.status == "review")
                st.subheader(f"Berita {i + 1}: {article.title or '(Tanpa Judul)'}")
                st.text(
                    f"Tanggal: {article.date or '-'} | Penulis: {article.author or '-'}"
                )
                st.text(
                    f"Paragraf: {len(article.paragraphs)} | Valid: {a_valid} | Review: {a_review}"
                )
                st.divider()
    else:
        st.info("Belum ada data. Masukkan berita di tab Input untuk memulai analisis.")
        saved = autosaver.load()
        if saved:
            st.warning("Ditemukan data autosave sebelumnya.")
            if st.button("Muat Autosave"):
                loaded_articles = []
                for art_data in saved.get("articles", []):
                    article = NewsArticle(
                        title=art_data.get("title", ""),
                        date=art_data.get("date", ""),
                        author=art_data.get("author", ""),
                        source=art_data.get("source", ""),
                        paragraphs=art_data.get("paragraphs", []),
                    )
                    for s in art_data.get("statements", []):
                        fields = {
                            k: v
                            for k, v in s.items()
                            if k in CodingStatement.__dataclass_fields__
                        }
                        article.statements.append(CodingStatement(**fields))
                    loaded_articles.append(article)
                st.session_state.articles = loaded_articles
                st.rerun()


# ── Tab: Export ────────────────────────────────────────────────
with tab_export:
    articles = st.session_state.articles

    if articles:
        st.subheader("Export DNA")

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**File .dna**")
            st.caption("Format utama untuk dibuka langsung di Discourse Network Analyzer.")

            export_filter = st.selectbox(
                "Export status",
                ["valid", "valid + review", "semua"],
                index=0,
                key="export_status_filter",
            )

            def _get_export_articles():
                """Filter articles for export based on selected status."""
                if export_filter == "semua":
                    return articles
                # Build filtered copies
                filtered = []
                for a in articles:
                    import copy
                    fa = copy.copy(a)
                    if export_filter == "valid":
                        fa.statements = [s for s in a.statements if s.status == "valid"]
                    else:
                        fa.statements = [s for s in a.statements if s.status != "reject"]
                    if fa.statements:
                        filtered.append(fa)
                return filtered

            dna_filename = st.text_input(
                "Nama file .dna",
                value="autodna_export.dna",
            )
            dna_version_options = ["3.0", "3.1.0"]
            dna_saved_version = settings.get("dna_database_version", "3.0")
            dna_version = st.selectbox(
                "Versi database DNA",
                dna_version_options,
                index=dna_version_options.index(dna_saved_version)
                if dna_saved_version in dna_version_options
                else 0,
                help="Pakai 3.0 untuk DNA yang menolak database 3.1.0.",
            )
            dna_coder_name = st.text_input(
                "Nama coder di DNA",
                value=settings.get("dna_coder_name", "Coder 1"),
                help="Nama ini yang muncul di dialog Coder verification DNA.",
            )
            dna_coder_password = st.text_input(
                "Password coder DNA",
                value=settings.get("dna_coder_password", "autodna"),
                type="password",
                help="Password ini dipakai saat membuka file .dna di aplikasi DNA.",
            )
            if st.button("Export .dna", type="primary", use_container_width=True):
                exp_articles = _get_export_articles()
                dna_path = OUTPUT_DIR / dna_filename
                settings["dna_database_version"] = dna_version
                settings["dna_coder_name"] = dna_coder_name.strip() or "Coder 1"
                settings["dna_coder_password"] = dna_coder_password
                save_settings(settings)
                ok = DnaWriter.write(
                    exp_articles,
                    str(dna_path),
                    coder_name=settings["dna_coder_name"],
                    coder_password=settings["dna_coder_password"],
                    database_version=settings["dna_database_version"],
                )
                if ok:
                    st.success(f"Tersimpan: {dna_path}")
                    with open(dna_path, "rb") as f:
                        st.download_button(
                            "Download .dna",
                            f.read(),
                            dna_filename,
                            "application/octet-stream",
                        )
                else:
                    st.error("Gagal menulis file .dna")

        with col_right:
            st.markdown("**Status**")
            st.text(f"Berita: {len(articles)}")
            st.text(f"Kutipan: {sum(len(a.statements) for a in articles)}")

            last_save = st.session_state.last_save_time
            if last_save:
                st.text(
                    f"Autosave terakhir: {datetime.fromtimestamp(last_save).strftime('%H:%M:%S')}"
                )

            st.divider()
            st.markdown("**DNA Format**")
            st.caption(DnaWriter.get_status_message())
    else:
        st.info("Belum ada data untuk di-export.")


# ── Auto-save check ───────────────────────────────────────────
if st.session_state.articles:
    now = time.time()
    interval = settings.get("autosave_interval", 10)
    if now - st.session_state.last_save_time >= interval:
        autosaver.save(st.session_state.articles)
        st.session_state.last_save_time = now
