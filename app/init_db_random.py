"""
Seed db/interview.db with 15 random questions drawn from a master SQL dump.

Used by `deploy.sh --init-random`. Expects the dump at INTERVIEW_MASTER_SQL,
or <project-root>/db/master.sql by default. If the master dump is missing,
falls back to init_db.py's hard-coded seed so deploys never break.
"""

import os
import random
import sqlite3
from pathlib import Path

from init_db import SCHEMA, DB, PROJECT_ROOT

SAMPLE_SIZE = 15
MASTER_SQL = Path(os.environ.get("INTERVIEW_MASTER_SQL", PROJECT_ROOT / "db" / "master.sql"))


def load_master_into_temp(sql_path: Path) -> sqlite3.Connection:
    """Apply schema + master dump into an in-memory DB and return the connection."""
    mem = sqlite3.connect(":memory:")
    mem.executescript(SCHEMA)
    mem.executescript(sql_path.read_text())
    return mem


def main():
    if DB.exists() and sqlite3.connect(DB).execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='questions'"
    ).fetchone()[0]:
        existing = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if existing:
            print(f"interview.db already has {existing} questions — leaving it alone.")
            return

    if not MASTER_SQL.exists():
        print(f"Master SQL not found at {MASTER_SQL} — falling back to init_db.py seed.")
        import init_db
        init_db.init()
        return

    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    master = load_master_into_temp(MASTER_SQL)
    all_ids = [r[0] for r in master.execute("SELECT id FROM questions WHERE archived = 0")]
    if not all_ids:
        raise SystemExit("Master dump has no questions.")

    sample = random.sample(all_ids, min(SAMPLE_SIZE, len(all_ids)))

    inserted = 0
    for order_idx, qid in enumerate(sample, start=1):
        q = master.execute(
            "SELECT text, category, difficulty, weight, avg_minutes FROM questions WHERE id = ?", (qid,)
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO questions (text, category, difficulty, weight, avg_minutes, order_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (*q, order_idx),
        )
        new_qid = cur.lastrowid
        answers = master.execute(
            "SELECT text, quality_label, score_value FROM possible_answers WHERE question_id = ?",
            (qid,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO possible_answers (question_id, text, quality_label, score_value) "
            "VALUES (?, ?, ?, ?)",
            [(new_qid, *a) for a in answers],
        )
        inserted += 1

    conn.commit()
    conn.close()
    master.close()
    print(f"Seeded interview.db with {inserted} random questions from {MASTER_SQL.name}.")


if __name__ == "__main__":
    main()
