"""
DNA Writer/Reader module.

The .dna format is a SQLite database used by Discourse Network Analyzer (DNA 3.x).
Schema reverse-engineered from sample ACHANK.txt.dna file.

Key relationships:
  DOCUMENTS.Text contains full article text
  STATEMENTS.Start/Stop = character positions in document text marking the quote
  ENTITIES = unique values for person/organization/concept variables
  DATASHORTTEXT links statements to entities (person, org, concept)
  DATABOOLEAN stores agreement (1=agree, 0=disagree)
"""

import base64
import hashlib
import os
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Optional


DEFAULT_CODER_NAME = "Coder 1"
DEFAULT_CODER_PASSWORD = "autodna"
DEFAULT_DATABASE_VERSION = "3.0"
SUPPORTED_DATABASE_VERSIONS = ("3.0", "3.1.0")


def _hash_coder_password(password: str) -> str:
    """Create a Jasypt StrongPasswordEncryptor-compatible password hash."""
    message = unicodedata.normalize("NFKC", password).encode("utf-8")
    salt = os.urandom(16)
    digest = hashlib.sha256(salt + message).digest()
    for _ in range(99999):
        digest = hashlib.sha256(digest).digest()
    return base64.b64encode(salt + digest).decode("ascii")


class DnaWriter:
    DNA_SCHEMA_KNOWN = True

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def get_status_message() -> str:
        return "Export .dna tersedia (DNA 3.x format)"

    @staticmethod
    def write(
        articles: list,
        filepath: str,
        coder_name: str = DEFAULT_CODER_NAME,
        coder_password: str = DEFAULT_CODER_PASSWORD,
        database_version: str = DEFAULT_DATABASE_VERSION,
    ) -> bool:
        conn = sqlite3.connect(filepath)
        _create_schema(conn)
        _write_data(conn, articles, coder_name, coder_password, database_version)
        conn.close()
        return True

    @staticmethod
    def read(filepath: str) -> dict:
        conn = sqlite3.connect(filepath)
        result = _read_data(conn)
        conn.close()
        return result


def _create_schema(conn: sqlite3.Connection):
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS SETTINGS")
    c.execute("DROP TABLE IF EXISTS CODERS")
    c.execute("DROP TABLE IF EXISTS CODERRELATIONS")
    c.execute("DROP TABLE IF EXISTS DOCUMENTS")
    c.execute("DROP TABLE IF EXISTS STATEMENTTYPES")
    c.execute("DROP TABLE IF EXISTS VARIABLES")
    c.execute("DROP TABLE IF EXISTS ENTITIES")
    c.execute("DROP TABLE IF EXISTS STATEMENTS")
    c.execute("DROP TABLE IF EXISTS DATASHORTTEXT")
    c.execute("DROP TABLE IF EXISTS DATABOOLEAN")
    c.execute("DROP TABLE IF EXISTS DATAINTEGER")
    c.execute("DROP TABLE IF EXISTS DATALONGTEXT")
    c.execute("DROP TABLE IF EXISTS ATTRIBUTEVARIABLES")
    c.execute("DROP TABLE IF EXISTS ATTRIBUTEVALUES")
    c.execute("DROP TABLE IF EXISTS REGEXES")
    c.execute("DROP TABLE IF EXISTS VARIABLELINKS")

    c.execute("""
        CREATE TABLE SETTINGS (
            Property TEXT,
            Value TEXT NOT NULL DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE CODERS (
            ID INTEGER NOT NULL,
            Name TEXT NOT NULL,
            Red INTEGER NOT NULL DEFAULT 0,
            Green INTEGER NOT NULL DEFAULT 0,
            Blue INTEGER NOT NULL DEFAULT 0,
            Refresh INTEGER NOT NULL DEFAULT 0,
            FontSize INTEGER NOT NULL DEFAULT 14,
            Password TEXT NOT NULL,
            PopupWidth INTEGER DEFAULT 300,
            ColorByCoder INTEGER NOT NULL DEFAULT 0,
            PopupDecoration INTEGER NOT NULL DEFAULT 0,
            PopupAutoComplete INTEGER NOT NULL DEFAULT 1,
            PermissionAddDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionEditDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionDeleteDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionImportDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionAddStatements INTEGER NOT NULL DEFAULT 1,
            PermissionEditStatements INTEGER NOT NULL DEFAULT 1,
            PermissionDeleteStatements INTEGER NOT NULL DEFAULT 1,
            PermissionEditAttributes INTEGER NOT NULL DEFAULT 1,
            PermissionEditRegex INTEGER NOT NULL DEFAULT 1,
            PermissionEditStatementTypes INTEGER NOT NULL DEFAULT 1,
            PermissionEditCoders INTEGER NOT NULL DEFAULT 1,
            PermissionEditCoderRelations INTEGER NOT NULL DEFAULT 1,
            PermissionViewOthersDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionEditOthersDocuments INTEGER NOT NULL DEFAULT 1,
            PermissionViewOthersStatements INTEGER NOT NULL DEFAULT 1,
            PermissionEditOthersStatements INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE CODERRELATIONS (
            ID INTEGER NOT NULL,
            Coder INTEGER,
            OtherCoder INTEGER,
            viewStatements INTEGER NOT NULL DEFAULT 1,
            editStatements INTEGER NOT NULL DEFAULT 1,
            viewDocuments INTEGER NOT NULL DEFAULT 1,
            editDocuments INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE DOCUMENTS (
            ID INTEGER NOT NULL,
            Title TEXT NOT NULL,
            Text TEXT NOT NULL,
            Coder INTEGER,
            Author TEXT NOT NULL DEFAULT '',
            Source TEXT NOT NULL DEFAULT '',
            Section TEXT NOT NULL DEFAULT '',
            Notes TEXT NOT NULL DEFAULT '',
            Type TEXT NOT NULL DEFAULT '',
            Date INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE STATEMENTTYPES (
            ID INTEGER NOT NULL,
            Label TEXT NOT NULL,
            Red INTEGER NOT NULL DEFAULT 0,
            Green INTEGER NOT NULL DEFAULT 0,
            Blue INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE VARIABLES (
            ID INTEGER NOT NULL,
            Variable TEXT NOT NULL,
            DataType TEXT NOT NULL DEFAULT 'short text',
            StatementTypeId INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE ENTITIES (
            ID INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            Value TEXT NOT NULL DEFAULT '',
            Red INTEGER,
            Green INTEGER,
            Blue INTEGER,
            ChildOf INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE STATEMENTS (
            ID INTEGER NOT NULL,
            StatementTypeId INTEGER,
            DocumentId INTEGER,
            Start INTEGER NOT NULL,
            Stop INTEGER NOT NULL,
            Coder INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE DATASHORTTEXT (
            ID INTEGER NOT NULL,
            StatementId INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            Entity INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE DATABOOLEAN (
            ID INTEGER NOT NULL,
            StatementId INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            Value INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE DATAINTEGER (
            ID INTEGER NOT NULL,
            StatementId INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            Value INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE DATALONGTEXT (
            ID INTEGER NOT NULL,
            StatementId INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            Value TEXT DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE ATTRIBUTEVARIABLES (
            ID INTEGER NOT NULL,
            VariableId INTEGER NOT NULL,
            AttributeVariable TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE ATTRIBUTEVALUES (
            ID INTEGER NOT NULL,
            EntityId INTEGER NOT NULL,
            AttributeVariableId INTEGER NOT NULL,
            AttributeValue TEXT NOT NULL DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE REGEXES (
            Label TEXT,
            Red INTEGER NOT NULL DEFAULT 0,
            Green INTEGER NOT NULL DEFAULT 0,
            Blue INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE VARIABLELINKS (
            ID INTEGER NOT NULL,
            SourceVariableId INTEGER,
            TargetVariableId INTEGER
        )
    """)

    conn.commit()


def _write_data(
    conn: sqlite3.Connection,
    articles: list,
    coder_name: str = DEFAULT_CODER_NAME,
    coder_password: str = DEFAULT_CODER_PASSWORD,
    database_version: str = DEFAULT_DATABASE_VERSION,
):
    c = conn.cursor()
    coder_name = (coder_name or DEFAULT_CODER_NAME).strip() or DEFAULT_CODER_NAME
    coder_password = coder_password if coder_password is not None else DEFAULT_CODER_PASSWORD
    database_version = (
        database_version
        if database_version in SUPPORTED_DATABASE_VERSIONS
        else DEFAULT_DATABASE_VERSION
    )
    password_hash = _hash_coder_password(coder_password)

    # Settings
    c.execute("INSERT INTO SETTINGS VALUES ('version', ?)", (database_version,))
    c.execute("INSERT INTO SETTINGS VALUES ('date', ?)",
              (time.strftime("%Y-%m-%d"),))

    # Coder account used by DNA's login dialog.
    c.execute(
        "INSERT INTO CODERS (ID, Name, Password) VALUES (1, ?, ?)",
        (coder_name, password_hash),
    )

    # Statement types (matching DNA standard)
    c.execute(
        "INSERT INTO STATEMENTTYPES VALUES (1, 'DNA Statement', 239, 208, 51)"
    )

    # Variables for DNA Statement (StatementTypeId=1)
    # person=1, organization=2, concept=3, agreement=4
    c.execute("INSERT INTO VARIABLES VALUES (1, 'person', 'short text', 1)")
    c.execute("INSERT INTO VARIABLES VALUES (2, 'organization', 'short text', 1)")
    c.execute("INSERT INTO VARIABLES VALUES (3, 'concept', 'short text', 1)")
    c.execute("INSERT INTO VARIABLES VALUES (4, 'agreement', 'boolean', 1)")

    # Attribute variables (Type, Alias, Notes for each variable)
    attr_id = 1
    for var_id in [1, 2, 3]:
        for attr_name in ["Type", "Alias", "Notes"]:
            c.execute(
                "INSERT INTO ATTRIBUTEVARIABLES VALUES (?, ?, ?)",
                (attr_id, var_id, attr_name),
            )
            attr_id += 1

    # Placeholder entities for empty values (ID 1-3)
    for var_id in [1, 2, 3]:
        c.execute(
            "INSERT INTO ENTITIES VALUES (?, ?, '', 0, 0, 0, NULL)",
            (var_id, var_id),
        )

    entity_id = 4
    entity_cache = {}  # (variable_id, value) -> entity_id
    statement_id = 1
    data_short_id = 1
    data_bool_id = 1
    attr_val_id = 1

    # Write attribute values for placeholder entities
    for eid in [1, 2, 3]:
        for a_var_id in range(1, attr_id):
            c.execute(
                "INSERT INTO ATTRIBUTEVALUES VALUES (?, ?, ?, '')",
                (attr_val_id, eid, a_var_id),
            )
            attr_val_id += 1

    for doc_idx, article in enumerate(articles):
        doc_id = doc_idx + 1
        doc_date = int(time.time())

        # Try to parse article date
        if hasattr(article, "date") and article.date:
            import re
            month_map = {
                "januari": 1, "februari": 2, "maret": 3, "april": 4,
                "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
                "september": 9, "oktober": 10, "november": 11, "desember": 12,
            }
            m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", article.date)
            if m:
                day, month_name, year = m.groups()
                month_num = month_map.get(month_name.lower(), 1)
                import datetime
                try:
                    dt = datetime.datetime(int(year), month_num, int(day))
                    doc_date = int(dt.timestamp())
                except ValueError:
                    pass

        doc_text = article.full_text if hasattr(article, "full_text") else ""
        doc_title = article.title if hasattr(article, "title") else f"Document {doc_id}"
        doc_author = article.author if hasattr(article, "author") else ""
        doc_source = article.source if hasattr(article, "source") else ""

        c.execute(
            "INSERT INTO DOCUMENTS VALUES (?, ?, ?, 1, ?, ?, '', '', '', ?)",
            (doc_id, doc_title, doc_text, doc_author, doc_source, doc_date),
        )

        for stmt in article.statements:
            # Only export valid/review statements to DNA
            stmt_status = getattr(stmt, "status", "valid")
            if stmt_status == "reject":
                continue

            # Find quote position in document text
            start = doc_text.find(stmt.quote)
            if start == -1:
                # Try partial match (first 50 chars)
                partial = stmt.quote[:50]
                start = doc_text.find(partial)
            if start == -1:
                continue

            stop = start + len(stmt.quote)

            # Create/reuse entities
            def get_or_create_entity(var_id, value):
                nonlocal entity_id, attr_val_id
                if not value:
                    return var_id  # placeholder empty entity

                key = (var_id, value)
                if key in entity_cache:
                    return entity_cache[key]

                eid = entity_id
                entity_id += 1
                entity_cache[key] = eid

                c.execute(
                    "INSERT INTO ENTITIES VALUES (?, ?, ?, 0, 0, 0, NULL)",
                    (eid, var_id, value),
                )

                # Add attribute values for this entity
                for a_var_id in range(1, attr_id):
                    c.execute(
                        "INSERT INTO ATTRIBUTEVALUES VALUES (?, ?, ?, '')",
                        (attr_val_id, eid, a_var_id),
                    )
                    attr_val_id += 1

                return eid

            person_eid = get_or_create_entity(1, stmt.actor)
            org_eid = get_or_create_entity(2, stmt.organization)
            concept_eid = get_or_create_entity(3, stmt.concept)

            # Statement
            c.execute(
                "INSERT INTO STATEMENTS VALUES (?, 1, ?, ?, ?, 1)",
                (statement_id, doc_id, start, stop),
            )

            # Data short text (person, org, concept)
            c.execute(
                "INSERT INTO DATASHORTTEXT VALUES (?, ?, 1, ?)",
                (data_short_id, statement_id, person_eid),
            )
            data_short_id += 1

            c.execute(
                "INSERT INTO DATASHORTTEXT VALUES (?, ?, 2, ?)",
                (data_short_id, statement_id, org_eid),
            )
            data_short_id += 1

            c.execute(
                "INSERT INTO DATASHORTTEXT VALUES (?, ?, 3, ?)",
                (data_short_id, statement_id, concept_eid),
            )
            data_short_id += 1

            # Data boolean (agreement): pro/netral -> 1, kontra -> 0
            stance = getattr(stmt, "stance", None) or getattr(stmt, "agreement", "pro")
            agreement_val = 0 if stance in ("kontra", "Disagreement") else 1
            c.execute(
                "INSERT INTO DATABOOLEAN VALUES (?, ?, 4, ?)",
                (data_bool_id, statement_id, agreement_val),
            )
            data_bool_id += 1

            statement_id += 1

    conn.commit()


def _read_data(conn: sqlite3.Connection) -> dict:
    c = conn.cursor()

    # Read documents
    c.execute("SELECT ID, Title, Text, Author, Source, Date FROM DOCUMENTS")
    documents = {}
    for row in c.fetchall():
        documents[row[0]] = {
            "id": row[0],
            "title": row[1],
            "text": row[2],
            "author": row[3],
            "source": row[4],
            "date": row[5],
        }

    # Read entities
    c.execute("SELECT ID, VariableId, Value FROM ENTITIES")
    entities = {}
    for row in c.fetchall():
        entities[row[0]] = {"variable_id": row[1], "value": row[2]}

    # Read statements with their data
    c.execute(
        "SELECT ID, StatementTypeId, DocumentId, Start, Stop FROM STATEMENTS"
    )
    statements = []
    for row in c.fetchall():
        stmt_id, type_id, doc_id, start, stop = row

        doc = documents.get(doc_id, {})
        doc_text = doc.get("text", "")
        quote = doc_text[start:stop] if doc_text else ""

        # Get short text data
        c2 = conn.cursor()
        c2.execute(
            "SELECT VariableId, Entity FROM DATASHORTTEXT WHERE StatementId=?",
            (stmt_id,),
        )
        person = ""
        organization = ""
        concept = ""
        for var_id, entity_id in c2.fetchall():
            entity = entities.get(entity_id, {})
            val = entity.get("value", "")
            if var_id == 1:
                person = val
            elif var_id == 2:
                organization = val
            elif var_id == 3:
                concept = val

        # Get agreement
        c2.execute(
            "SELECT Value FROM DATABOOLEAN WHERE StatementId=? AND VariableId=4",
            (stmt_id,),
        )
        bool_row = c2.fetchone()
        agreement = "Agreement" if (bool_row and bool_row[0] == 1) else "Disagreement"

        statements.append(
            {
                "document_id": doc_id,
                "document_title": doc.get("title", ""),
                "quote": quote,
                "start": start,
                "stop": stop,
                "person": person,
                "organization": organization,
                "concept": concept,
                "agreement": agreement,
            }
        )

    return {"documents": documents, "statements": statements}
