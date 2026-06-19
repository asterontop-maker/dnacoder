import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class Exporter:
    def __init__(self, export_dir: str = "exports"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)

    COLUMNS = [
        "berita_id", "judul", "paragraf_id", "quote", "speaker",
        "organization", "role", "concept", "stance", "confidence", "status",
    ]

    def statements_to_dataframe(
        self, articles: list, status_filter: str = None
    ) -> pd.DataFrame:
        rows = []
        for article in articles:
            for stmt in article.statements:
                if status_filter and stmt.status != status_filter:
                    continue
                rows.append(
                    {
                        "berita_id": stmt.article_index + 1,
                        "judul": article.title,
                        "paragraf_id": stmt.paragraph_index + 1,
                        "quote": stmt.quote,
                        "speaker": stmt.actor,
                        "organization": stmt.organization,
                        "role": stmt.role,
                        "concept": stmt.concept,
                        "stance": stmt.stance,
                        "confidence": round(stmt.confidence, 2),
                        "status": stmt.status,
                    }
                )
        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame(columns=self.COLUMNS)

    def export_csv(self, articles: list, filename: str = None) -> str:
        if not filename:
            filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = self.export_dir / filename
        df = self.statements_to_dataframe(articles)
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return str(filepath)

    def export_xlsx(self, articles: list, filename: str = None) -> str:
        if not filename:
            filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = self.export_dir / filename
        df = self.statements_to_dataframe(articles)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Coding", index=False)
            ws = writer.sheets["Coding"]
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

        return str(filepath)

    def export_graphml(self, articles: list, filename: str = None) -> str:
        if not HAS_NETWORKX:
            raise ImportError("networkx diperlukan untuk export GraphML")

        if not filename:
            filename = f"network_{datetime.now().strftime('%Y%m%d_%H%M%S')}.graphml"
        filepath = self.export_dir / filename

        G = nx.Graph()

        for article in articles:
            for stmt in article.statements:
                if not stmt.actor or not stmt.concept:
                    continue

                if not G.has_node(stmt.actor):
                    G.add_node(
                        stmt.actor,
                        node_type="actor",
                        organization=stmt.organization,
                    )

                if not G.has_node(stmt.concept):
                    G.add_node(stmt.concept, node_type="concept")

                if G.has_edge(stmt.actor, stmt.concept):
                    G[stmt.actor][stmt.concept]["weight"] += 1
                else:
                    G.add_edge(
                        stmt.actor,
                        stmt.concept,
                        weight=1,
                        agreement=stmt.stance,
                    )

        nx.write_graphml(G, str(filepath))
        return str(filepath)

    def export_json(self, articles: list, filename: str = None) -> str:
        if not filename:
            filename = f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.export_dir / filename

        data = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "articles": [],
        }

        for article in articles:
            art_data = {
                "title": article.title,
                "date": article.date,
                "author": article.author,
                "source": article.source,
                "paragraphs": article.paragraphs,
                "statements": [s.to_dict() for s in article.statements],
            }
            data["articles"].append(art_data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(filepath)


class AutoSaver:
    def __init__(self, autosave_dir: str = "autosave"):
        self.autosave_dir = Path(autosave_dir)
        self.autosave_dir.mkdir(exist_ok=True)
        self.db_path = self.autosave_dir / "project.sqlite"
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_index INTEGER,
                paragraph_index INTEGER,
                quote TEXT,
                actor TEXT,
                organization TEXT,
                concept TEXT,
                agreement TEXT,
                confidence REAL,
                validated INTEGER DEFAULT 0,
                article_title TEXT,
                article_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_index INTEGER,
                title TEXT,
                date TEXT,
                author TEXT,
                source TEXT,
                full_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()
        conn.close()

    def save(self, articles: list):
        self._save_json(articles)
        self._save_csv(articles)
        self._save_sqlite(articles)

    def _save_json(self, articles: list):
        exporter = Exporter(str(self.autosave_dir))
        exporter.export_json(articles, "autosave.json")

    def _save_csv(self, articles: list):
        exporter = Exporter(str(self.autosave_dir))
        exporter.export_csv(articles, "backup.csv")

    def _save_sqlite(self, articles: list):
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("DELETE FROM statements")
            conn.execute("DELETE FROM articles")

            for article in articles:
                conn.execute(
                    "INSERT INTO articles (article_index, title, date, author, source, full_text) VALUES (?, ?, ?, ?, ?, ?)",
                    (0, article.title, article.date, article.author, article.source, article.full_text),
                )

                for stmt in article.statements:
                    conn.execute(
                        "INSERT INTO statements (article_index, paragraph_index, quote, actor, organization, concept, agreement, confidence, validated, article_title, article_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            stmt.article_index, stmt.paragraph_index, stmt.quote,
                            stmt.actor, stmt.organization, stmt.concept,
                            stmt.stance, stmt.confidence,
                            1 if stmt.validated else 0,
                            article.title, article.date,
                        ),
                    )

            conn.commit()
        finally:
            conn.close()

    def load(self) -> Optional[dict]:
        json_path = self.autosave_dir / "autosave.json"
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
