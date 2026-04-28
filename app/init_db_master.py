"""
Seed db/interview.db with the full master question bank from a SQL dump.

Used by `deploy.sh --master`. Expects the dump path in INTERVIEW_MASTER_SQL,
or <project-root>/db/master.sql by default. Refuses to clobber an existing
DB that already has questions — wipe it first if you really mean it.
"""

import os
import sqlite3
from pathlib import Path

from init_db import SCHEMA, DB, PROJECT_ROOT

MASTER_SQL = Path(os.environ.get("INTERVIEW_MASTER_SQL", PROJECT_ROOT / "db" / "master.sql"))


def main():
    if not MASTER_SQL.exists():
        raise SystemExit(f"Master SQL not found at {MASTER_SQL}")

    if DB.exists():
        existing = sqlite3.connect(DB).execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='questions'"
        ).fetchone()[0]
        if existing:
            count = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            if count:
                print(f"interview.db already has {count} questions — refusing to overwrite. "
                      "Delete the file first if you want a fresh master load.")
                return

    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    conn.executescript(MASTER_SQL.read_text())
    qcount = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    acount = conn.execute("SELECT COUNT(*) FROM possible_answers").fetchone()[0]
    conn.commit()
    conn.close()
    print(f"Loaded master bank: {qcount} questions, {acount} answers.")


if __name__ == "__main__":
    main()
