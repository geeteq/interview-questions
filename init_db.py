import sqlite3

DB = "interview.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    difficulty   INTEGER NOT NULL,   -- 1 (easy) → 5 (hard)
    weight       REAL    NOT NULL,   -- score multiplier
    order_index  INTEGER NOT NULL
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
    completed_at    TEXT
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
    evaluated_at        TEXT,
    FOREIGN KEY (session_id)         REFERENCES sessions(id),
    FOREIGN KEY (question_id)        REFERENCES questions(id),
    FOREIGN KEY (selected_answer_id) REFERENCES possible_answers(id)
);

CREATE TABLE IF NOT EXISTS session_chat (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    author      TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
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

    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count == 0:
        for q in QUESTIONS:
            cur = conn.execute(
                "INSERT INTO questions (text, category, difficulty, weight, order_index) VALUES (?,?,?,?,?)",
                (q["text"], q["category"], q["difficulty"], q["weight"], q["order_index"]),
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
