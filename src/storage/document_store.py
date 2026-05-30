"""知识库文档与 chunk 的 SQLite 存储"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.models.document import Document
from src.core.models.index_chunk import IndexChunk
from src.infra.logging import get_logger

logger = get_logger("storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,
  file_hash TEXT UNIQUE NOT NULL,
  source_path TEXT NOT NULL,
  title TEXT NOT NULL,
  lang TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  parsed_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  parent_id TEXT,
  level TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  heading_path TEXT,
  lang TEXT,
  char_count INTEGER NOT NULL,
  embedded INTEGER DEFAULT 0,
  embedding_model TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedded ON chunks(doc_id, embedded, level);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentStore:
    """SQLite 文档与层次 chunk 存储"""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def get_by_file_hash(self, file_hash: str) -> Optional[Document]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE file_hash = ?",
                (file_hash,),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def get_document(self, doc_id: str) -> Optional[Document]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def list_documents(
        self, status: Optional[str] = None
    ) -> list[Document]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def upsert_document(self, doc: Document) -> None:
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM documents WHERE file_hash = ?",
                (doc.file_hash,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE documents SET
                      source_path = ?, title = ?, lang = ?, char_count = ?,
                      status = ?, parsed_path = ?, updated_at = ?
                    WHERE file_hash = ?
                    """,
                    (
                        doc.source_path,
                        doc.title,
                        doc.lang,
                        doc.char_count,
                        doc.status,
                        doc.parsed_path,
                        now,
                        doc.file_hash,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO documents (
                      doc_id, file_hash, source_path, title, lang, char_count,
                      status, parsed_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc.doc_id,
                        doc.file_hash,
                        doc.source_path,
                        doc.title,
                        doc.lang,
                        doc.char_count,
                        doc.status,
                        doc.parsed_path,
                        doc.created_at or now,
                        now,
                    ),
                )
            conn.commit()

    def update_status(self, doc_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE doc_id = ?",
                (status, _utc_now(), doc_id),
            )
            conn.commit()

    def replace_chunks(self, doc_id: str, chunks: list[IndexChunk]) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (
                      chunk_id, doc_id, parent_id, level, chunk_index, text,
                      heading_path, lang, char_count, embedded, embedding_model,
                      created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        doc_id,
                        chunk.parent_id,
                        chunk.level,
                        chunk.index,
                        chunk.text,
                        json.dumps(chunk.heading_path, ensure_ascii=False),
                        chunk.lang,
                        chunk.char_count,
                        1 if chunk.embedded else 0,
                        None,
                        now,
                    ),
                )
            conn.commit()
        logger.info("已写入 %d 个 chunks (doc_id=%s)", len(chunks), doc_id)

    def get_chunk_by_id(self, chunk_id: str) -> Optional[IndexChunk]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone()
        return self._row_to_chunk(row) if row else None

    def get_chunks_by_doc(
        self, doc_id: str, level: Optional[str] = None
    ) -> list[IndexChunk]:
        with self._connect() as conn:
            if level:
                rows = conn.execute(
                    """
                    SELECT * FROM chunks
                    WHERE doc_id = ? AND level = ?
                    ORDER BY chunk_index
                    """,
                    (doc_id, level),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM chunks WHERE doc_id = ?
                    ORDER BY chunk_index
                    """,
                    (doc_id,),
                ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def get_unembedded_leaves(self, doc_id: str) -> list[IndexChunk]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chunks
                WHERE doc_id = ? AND level = 'leaf' AND embedded = 0
                ORDER BY chunk_index
                """,
                (doc_id,),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def list_doc_ids_by_status(self, status: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT doc_id FROM documents WHERE status = ?",
                (status,),
            ).fetchall()
        return [r["doc_id"] for r in rows]

    def mark_embedded(
        self, chunk_ids: list[str], embedding_model: str
    ) -> None:
        if not chunk_ids:
            return
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE chunks SET embedded = 1, embedding_model = ?
                WHERE chunk_id IN ({placeholders})
                """,
                [embedding_model, *chunk_ids],
            )
            conn.commit()

    def reset_embedded(self, doc_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chunks SET embedded = 0, embedding_model = NULL
                WHERE doc_id = ? AND level = 'leaf'
                """,
                (doc_id,),
            )
            conn.commit()

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> Document:
        return Document(
            doc_id=row["doc_id"],
            file_hash=row["file_hash"],
            source_path=row["source_path"],
            title=row["title"],
            lang=row["lang"],
            char_count=row["char_count"],
            status=row["status"],
            parsed_path=row["parsed_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> IndexChunk:
        heading_path = row["heading_path"]
        if isinstance(heading_path, str):
            heading_path = json.loads(heading_path) if heading_path else []
        return IndexChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            parent_id=row["parent_id"],
            level=row["level"],
            index=row["chunk_index"],
            text=row["text"],
            heading_path=heading_path or [],
            lang=row["lang"] or "",
            char_count=row["char_count"],
            embedded=bool(row["embedded"]),
        )
