"""验证 SQLite 入库结果"""
import sqlite3
import sys
from pathlib import Path

db = Path("data/doc_translator.db")
if not db.exists():
    print("DB not found")
    sys.exit(1)

conn = sqlite3.connect(db)
doc = conn.execute("SELECT doc_id, status, lang FROM documents").fetchone()
sec = conn.execute(
    "SELECT COUNT(1) FROM chunks WHERE level = 'section'"
).fetchone()[0]
leaf = conn.execute(
    "SELECT COUNT(1) FROM chunks WHERE level = 'leaf'"
).fetchone()[0]
with_parent = conn.execute(
    "SELECT COUNT(1) FROM chunks WHERE level = 'leaf' AND parent_id IS NOT NULL"
).fetchone()[0]
print(f"document: {doc}")
print(f"sections: {sec}, leaves: {leaf}, leaves_with_parent: {with_parent}")
