import sqlite3

from config import DB_PATH as DB, PROJECT_ROOT, APP_DIR  # noqa: F401

# Make sure the parent dir exists so the first sqlite3.connect doesn't fail
# on a fresh checkout.
DB.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_INTERVIEW_MINUTES = 45  # target slot for one interview

# Per-category time tuning. Drawing-board questions take much longer than a
# quick intro/exit; tech and behavioural fall in the middle.
_TIME_FACTOR_BY_CATEGORY = {
    "Drawing Board":   1.7,
    "Drawing board":   1.7,
    "Tech":            1.0,
    "Behavioural":     1.0,
    "Management":      1.0,
    "HR":              0.8,
    "Interpersonal":   1.0,
    "Adaptability":    1.0,
    "Time Management": 1.0,
    "Ethics & Security": 1.2,
    "Safety":          0.8,
    "Intro":           0.6,
    "Exit":            0.5,
}


def estimate_minutes(category: str, difficulty: int) -> float:
    """Rough estimate in minutes a candidate is expected to spend on this
    question. Used to populate the avg_minutes column when one isn't set."""
    factor = _TIME_FACTOR_BY_CATEGORY.get(category, 1.0)
    return round(1.0 + float(difficulty) * factor, 1)


SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    difficulty   INTEGER NOT NULL,   -- 1 (easy) → 5 (hard)
    weight       REAL    NOT NULL,   -- score multiplier
    avg_minutes  REAL    NOT NULL DEFAULT 0,  -- expected time per question
    order_index  INTEGER NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    diagram_xml  TEXT
);

CREATE TABLE IF NOT EXISTS possible_answers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id   INTEGER NOT NULL,
    text          TEXT    NOT NULL,
    quality_label TEXT    NOT NULL,  -- Excellent / Good / Acceptable / Poor / Dangerous
    score_value   INTEGER NOT NULL,  -- 0–4
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_name  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    archived        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_state (
    session_id              INTEGER PRIMARY KEY,
    current_question_index  INTEGER DEFAULT 0,
    status                  TEXT    DEFAULT 'active',  -- active | complete
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_responses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    question_id         INTEGER NOT NULL,
    selected_answer_id  INTEGER,
    admin_comment       TEXT    DEFAULT '',
    score_awarded       REAL    DEFAULT 0,
    skipped             INTEGER NOT NULL DEFAULT 0,
    evaluated_at        TEXT,
    FOREIGN KEY (session_id)         REFERENCES sessions(id),
    FOREIGN KEY (question_id)        REFERENCES questions(id),
    FOREIGN KEY (selected_answer_id) REFERENCES possible_answers(id)
);

CREATE TABLE IF NOT EXISTS session_questions (
    session_id    INTEGER NOT NULL,
    question_id   INTEGER NOT NULL,
    order_index   INTEGER NOT NULL,
    published_at  TEXT,
    PRIMARY KEY (session_id, question_id),
    FOREIGN KEY (session_id)  REFERENCES sessions(id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS session_diagrams (
    session_id   INTEGER NOT NULL,
    question_id  INTEGER NOT NULL,
    xml          TEXT    NOT NULL,
    submitted_at TEXT    NOT NULL,
    PRIMARY KEY (session_id, question_id),
    FOREIGN KEY (session_id)  REFERENCES sessions(id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS session_chat (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    author      TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Lower priority = earlier in the interview. New categories default to 100
-- so admins can sort the important ones explicitly without re-numbering all.
CREATE TABLE IF NOT EXISTS category_order (
    category  TEXT PRIMARY KEY,
    priority  INTEGER NOT NULL DEFAULT 100
);
"""

# weight = how many points each score unit is worth
# score_value 0–4 × weight = weighted points earned
# max per question = 4 × weight
QUESTIONS = [
    {
        "text": "You are alone in the office and you notice a small fire starting in a corner. What do you do?",
        "category": "Safety",
        "difficulty": 2,
        "weight": 1.5,
        "order_index": 1,
        "answers": [
            ("Look at the fire and do nothing",                                                                                   "Poor",       1),
            ("Assess whether the fire is dangerous",                                                                              "Acceptable", 2),
            ("Call the fire department and panic, running around the office",                                                     "Poor",       1),
            ("Look at the fire, assess its impact, evacuate the area, and make a plan to prevent further spread",                 "Excellent",  4),
            ("Put fireworks in the fire to see what happens",                                                                     "Dangerous",  0),
        ],
    },
    {
        "text": "You are working on a project with a tight deadline and you realise you cannot finish on time. What do you do?",
        "category": "Time Management",
        "difficulty": 3,
        "weight": 2.0,
        "order_index": 2,
        "answers": [
            ("Work overtime in secret without informing your manager",                                                            "Acceptable", 2),
            ("Tell your manager it cannot be done and give up",                                                                   "Poor",       1),
            ("Prioritise tasks, communicate risks early to your manager, and ask for help if needed",                             "Excellent",  4),
            ("Cut quality corners to meet the deadline without telling anyone",                                                   "Poor",       1),
            ("Request a deadline extension with a clear updated plan and full justification",                                     "Good",       3),
        ],
    },
    {
        "text": "A colleague approaches you visibly upset, claiming a mistake you made damaged their work. How do you handle it?",
        "category": "Interpersonal",
        "difficulty": 3,
        "weight": 2.0,
        "order_index": 3,
        "answers": [
            ("Ignore them and hope the situation resolves itself",                                                                "Poor",       1),
            ("Immediately escalate to HR without attempting to resolve it first",                                                 "Poor",       1),
            ("Have a direct, calm conversation to understand their concern",                                                      "Good",       3),
            ("Become defensive and deny any wrongdoing",                                                                         "Dangerous",  0),
            ("Listen carefully, acknowledge their perspective, investigate the issue, and work toward a mutually agreeable fix",  "Excellent",  4),
        ],
    },
    {
        "text": "Your team must adopt a technology none of you have used before, with a project kicking off in two weeks. What is your approach?",
        "category": "Adaptability",
        "difficulty": 4,
        "weight": 2.5,
        "order_index": 4,
        "answers": [
            ("Wait for someone else to learn it first and follow their lead",                                                     "Poor",       1),
            ("Tell management you already know it without actually learning it",                                                  "Dangerous",  0),
            ("Read the official documentation and build small proof-of-concept examples",                                        "Good",       3),
            ("Identify resources, do hands-on practice, connect with knowledgeable peers, and share learnings with the team",    "Excellent",  4),
            ("Start guessing your way through and fix mistakes as they surface in production",                                   "Acceptable", 2),
        ],
    },
    {
        "text": "While reviewing code you discover a serious security vulnerability in a live production system. What do you do?",
        "category": "Ethics & Security",
        "difficulty": 5,
        "weight": 3.0,
        "order_index": 5,
        "answers": [
            ("Ignore it — it is not your responsibility",                                                                        "Dangerous",  0),
            ("Fix it quietly in a commit without telling anyone",                                                                "Poor",       1),
            ("Report it immediately to your team lead and document it",                                                          "Good",       3),
            ("Post about it publicly on social media to raise awareness",                                                        "Dangerous",  0),
            ("Report to the security team, document the vulnerability, follow the incident-response procedure, ensure a reviewed fix before deployment", "Excellent", 4),
        ],
    },
]


def init():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    if "archived" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

    qcols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    if "archived" not in qcols:
        conn.execute("ALTER TABLE questions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    if "diagram_xml" not in qcols:
        conn.execute("ALTER TABLE questions ADD COLUMN diagram_xml TEXT")
    if "avg_minutes" not in qcols:
        conn.execute("ALTER TABLE questions ADD COLUMN avg_minutes REAL NOT NULL DEFAULT 0")

    # Backfill avg_minutes for any rows that still sit at 0 — safe to re-run
    # because it only touches rows the operator hasn't tuned yet.
    todo = conn.execute(
        "SELECT id, category, difficulty FROM questions WHERE avg_minutes <= 0"
    ).fetchall()
    for row in todo:
        mins = estimate_minutes(row[1], row[2])
        conn.execute("UPDATE questions SET avg_minutes=? WHERE id=?", (mins, row[0]))

    # Make sure every category used by a question has a priority row. INSERT OR
    # IGNORE leaves any priorities the admin already set untouched.
    conn.executemany(
        "INSERT OR IGNORE INTO category_order (category, priority) VALUES (?, 100)",
        [(r[0],) for r in conn.execute(
            "SELECT DISTINCT category FROM questions"
        ).fetchall()],
    )

    rcols = [r[1] for r in conn.execute("PRAGMA table_info(session_responses)").fetchall()]
    if "skipped" not in rcols:
        conn.execute("ALTER TABLE session_responses ADD COLUMN skipped INTEGER NOT NULL DEFAULT 0")

    sqcols = [r[1] for r in conn.execute("PRAGMA table_info(session_questions)").fetchall()]
    if sqcols and "published_at" not in sqcols:
        conn.execute("ALTER TABLE session_questions ADD COLUMN published_at TEXT")

    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count == 0:
        for q in QUESTIONS:
            cur = conn.execute(
                "INSERT INTO questions (text, category, difficulty, weight, avg_minutes, order_index) "
                "VALUES (?,?,?,?,?,?)",
                (q["text"], q["category"], q["difficulty"], q["weight"],
                 estimate_minutes(q["category"], q["difficulty"]), q["order_index"]),
            )
            qid = cur.lastrowid
            for text, quality, score in q["answers"]:
                conn.execute(
                    "INSERT INTO possible_answers (question_id, text, quality_label, score_value) VALUES (?,?,?,?)",
                    (qid, text, quality, score),
                )
        print(f"Seeded {len(QUESTIONS)} questions.")
    else:
        print(f"DB already has {count} questions — skipping seed.")

    conn.commit()
    conn.close()
    print("Database ready.")


if __name__ == "__main__":
    init()
