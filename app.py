from flask import Flask, render_template, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import sqlite3
from datetime import datetime
from init_db import init

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
DB = "interview.db"


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route("/")
def candidate_screen():
    return render_template("user.html")


@app.route("/admin")
def admin_screen():
    return render_template("admin.html")


# ── Candidate polling endpoint ─────────────────────────────────────────────────

@app.route("/api/state")
def state():
    """Polled by the candidate screen every 2 s to get the current question."""
    c = db()
    session = c.execute(
        "SELECT * FROM sessions WHERE completed_at IS NULL ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    if not session:
        return jsonify({"status": "waiting"})

    st = c.execute(
        "SELECT * FROM session_state WHERE session_id=?", (session["id"],)
    ).fetchone()

    if not st or st["status"] == "complete":
        return jsonify({"status": "complete", "session_id": session["id"],
                        "candidate": session["candidate_name"]})

    questions = c.execute("SELECT * FROM questions ORDER BY order_index").fetchall()
    qi = st["current_question_index"]

    if qi >= len(questions):
        return jsonify({"status": "complete", "session_id": session["id"],
                        "candidate": session["candidate_name"]})

    q = questions[qi]
    return jsonify({
        "status":        "active",
        "session_id":    session["id"],
        "candidate":     session["candidate_name"],
        "q_number":      qi + 1,
        "q_total":       len(questions),
        "question": {
            "id":         q["id"],
            "text":       q["text"],
            "category":   q["category"],
            "difficulty": q["difficulty"],
        },
    })


# ── Session management ─────────────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    c = db()
    rows = c.execute(
        "SELECT * FROM sessions ORDER BY started_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.json
    c = db()
    # Close any previously active session
    active = c.execute(
        "SELECT id FROM sessions WHERE completed_at IS NULL"
    ).fetchall()
    for row in active:
        c.execute("UPDATE session_state SET status='complete' WHERE session_id=?", (row["id"],))
        c.execute("UPDATE sessions SET completed_at=? WHERE id=?",
                  (datetime.now().isoformat(), row["id"]))

    cur = c.execute(
        "INSERT INTO sessions (candidate_name, started_at) VALUES (?,?)",
        (data["candidate_name"], datetime.now().isoformat()),
    )
    sid = cur.lastrowid
    c.execute(
        "INSERT INTO session_state (session_id, current_question_index, status) VALUES (?,0,'active')",
        (sid,),
    )
    c.commit()
    return jsonify({"session_id": sid})


# ── Admin question view ────────────────────────────────────────────────────────

@app.route("/api/sessions/<int:sid>/question")
def admin_question(sid):
    """Returns the current question for a session including all possible answers."""
    c = db()
    st = c.execute(
        "SELECT * FROM session_state WHERE session_id=?", (sid,)
    ).fetchone()
    if not st:
        return jsonify({"error": "Session not found"}), 404

    if st["status"] == "complete":
        return jsonify({"status": "complete"})

    questions = c.execute("SELECT * FROM questions ORDER BY order_index").fetchall()
    qi = st["current_question_index"]

    if qi >= len(questions):
        return jsonify({"status": "complete"})

    q = questions[qi]
    answers = c.execute(
        "SELECT * FROM possible_answers WHERE question_id=? ORDER BY score_value DESC",
        (q["id"],),
    ).fetchall()

    return jsonify({
        "status":         "active",
        "question_index": qi,
        "total":          len(questions),
        "question": {
            "id":         q["id"],
            "text":       q["text"],
            "category":   q["category"],
            "difficulty": q["difficulty"],
            "weight":     q["weight"],
            "max_points": round(q["weight"] * 4, 2),
        },
        "answers": [
            {
                "id":      a["id"],
                "text":    a["text"],
                "quality": a["quality_label"],
                "score":   a["score_value"],
                "points":  round(a["score_value"] * q["weight"], 2),
            }
            for a in answers
        ],
    })


# ── Advance to next question ───────────────────────────────────────────────────

@app.route("/api/sessions/<int:sid>/next", methods=["POST"])
def next_question(sid):
    """Save the admin's selected answer + comment, then advance the question index."""
    data = request.json or {}
    c = db()

    st = c.execute(
        "SELECT * FROM session_state WHERE session_id=?", (sid,)
    ).fetchone()
    if not st:
        return jsonify({"error": "Session not found"}), 404

    qi = st["current_question_index"]
    questions = c.execute("SELECT * FROM questions ORDER BY order_index").fetchall()

    if qi < len(questions):
        q = questions[qi]
        answer_id = data.get("answer_id")
        comment   = data.get("comment", "")

        if answer_id:
            ans   = c.execute("SELECT * FROM possible_answers WHERE id=?", (answer_id,)).fetchone()
            score = round(float(ans["score_value"]) * float(q["weight"]), 2) if ans else 0.0
        else:
            score = 0.0

        c.execute(
            """INSERT INTO session_responses
               (session_id, question_id, selected_answer_id, admin_comment, score_awarded, evaluated_at)
               VALUES (?,?,?,?,?,?)""",
            (sid, q["id"], answer_id, comment, score, datetime.now().isoformat()),
        )

    next_i = qi + 1
    if next_i >= len(questions):
        c.execute(
            "UPDATE session_state SET status='complete', current_question_index=? WHERE session_id=?",
            (next_i, sid),
        )
        c.execute(
            "UPDATE sessions SET completed_at=? WHERE id=?",
            (datetime.now().isoformat(), sid),
        )
        complete = True
    else:
        c.execute(
            "UPDATE session_state SET current_question_index=? WHERE session_id=?",
            (next_i, sid),
        )
        complete = False

    c.commit()
    return jsonify({"success": True, "next_index": next_i, "complete": complete})


# ── Results ────────────────────────────────────────────────────────────────────

@app.route("/api/sessions/<int:sid>/results")
def results(sid):
    c = db()
    session = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session:
        return jsonify({"error": "Not found"}), 404

    responses = c.execute(
        """SELECT sr.*,
                  q.text       AS q_text,
                  q.weight     AS q_weight,
                  q.difficulty AS q_difficulty,
                  q.category   AS q_category,
                  pa.text          AS a_text,
                  pa.quality_label AS a_quality,
                  pa.score_value   AS a_score_value
           FROM session_responses sr
           JOIN questions q          ON q.id  = sr.question_id
           LEFT JOIN possible_answers pa ON pa.id = sr.selected_answer_id
           WHERE sr.session_id=?
           ORDER BY sr.id""",
        (sid,),
    ).fetchall()

    questions  = c.execute("SELECT * FROM questions").fetchall()
    max_score  = sum(float(q["weight"]) * 4 for q in questions)
    total      = sum(float(r["score_awarded"]) for r in responses)
    pct        = round(total / max_score * 100, 1) if max_score else 0

    chat = c.execute(
        "SELECT * FROM session_chat WHERE session_id=? ORDER BY id", (sid,)
    ).fetchall()

    return jsonify({
        "candidate":   session["candidate_name"],
        "started":     session["started_at"],
        "completed":   session["completed_at"],
        "total_score": round(total, 2),
        "max_score":   round(max_score, 2),
        "percentage":  pct,
        "grade":       _grade(pct),
        "responses": [
            {
                "question":    r["q_text"],
                "category":    r["q_category"],
                "difficulty":  r["q_difficulty"],
                "weight":      r["q_weight"],
                "max_points":  round(float(r["q_weight"]) * 4, 2),
                "answer":      r["a_text"] or "— no answer selected —",
                "quality":     r["a_quality"] or "—",
                "score_raw":   r["a_score_value"],
                "score_earned":round(float(r["score_awarded"]), 2),
                "comment":     r["admin_comment"],
            }
            for r in responses
        ],
        "chat": [dict(m) for m in chat],
    })


# ── Admin chat ─────────────────────────────────────────────────────────────────

@app.route("/api/sessions/<int:sid>/chat")
def get_chat(sid):
    since = request.args.get("since", 0, type=int)
    c = db()
    rows = c.execute(
        "SELECT * FROM session_chat WHERE session_id=? AND id>? ORDER BY id",
        (sid, since),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions/<int:sid>/chat", methods=["POST"])
def post_chat(sid):
    data = request.json
    c = db()
    cur = c.execute(
        "INSERT INTO session_chat (session_id, author, message, sent_at) VALUES (?,?,?,?)",
        (sid, data["author"], data["message"], datetime.now().isoformat()),
    )
    c.commit()
    row = c.execute("SELECT * FROM session_chat WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row))


def _grade(pct):
    if pct >= 85: return "Outstanding"
    if pct >= 70: return "Strong"
    if pct >= 55: return "Adequate"
    if pct >= 35: return "Weak"
    return "Poor"


# ── Admin sub-pages ────────────────────────────────────────────────────────────

@app.route("/admin/questions")
def admin_questions_page():
    return render_template("admin_questions.html")


@app.route("/admin/sessions")
def admin_sessions_page():
    return render_template("admin_sessions.html")


# ── Question CRUD ──────────────────────────────────────────────────────────────

@app.route("/api/questions")
def get_questions():
    c = db()
    rows = c.execute(
        """SELECT q.*, COUNT(pa.id) AS answer_count
           FROM questions q
           LEFT JOIN possible_answers pa ON pa.question_id = q.id
           GROUP BY q.id ORDER BY q.order_index"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/questions", methods=["POST"])
def create_question():
    data = request.json
    c = db()
    max_order = c.execute("SELECT COALESCE(MAX(order_index), 0) FROM questions").fetchone()[0]
    cur = c.execute(
        "INSERT INTO questions (text, category, difficulty, weight, order_index) VALUES (?,?,?,?,?)",
        (data["text"], data["category"], int(data["difficulty"]), float(data["weight"]), max_order + 1),
    )
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/questions/<int:qid>", methods=["PUT"])
def update_question(qid):
    data = request.json
    c = db()
    c.execute(
        "UPDATE questions SET text=?, category=?, difficulty=?, weight=? WHERE id=?",
        (data["text"], data["category"], int(data["difficulty"]), float(data["weight"]), qid),
    )
    c.commit()
    return jsonify({"success": True})


@app.route("/api/questions/<int:qid>", methods=["DELETE"])
def delete_question(qid):
    c = db()
    used = c.execute(
        "SELECT COUNT(*) FROM session_responses WHERE question_id=?", (qid,)
    ).fetchone()[0]
    if used:
        return jsonify({"error": f"Cannot delete — used in {used} session response(s)."}), 400
    c.execute("DELETE FROM possible_answers WHERE question_id=?", (qid,))
    c.execute("DELETE FROM questions WHERE id=?", (qid,))
    c.commit()
    return jsonify({"success": True})


# ── Answer CRUD ────────────────────────────────────────────────────────────────

@app.route("/api/questions/<int:qid>/answers")
def get_answers(qid):
    c = db()
    rows = c.execute(
        "SELECT * FROM possible_answers WHERE question_id=? ORDER BY score_value DESC", (qid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/questions/<int:qid>/answers", methods=["POST"])
def add_answer(qid):
    data = request.json
    c = db()
    cur = c.execute(
        "INSERT INTO possible_answers (question_id, text, quality_label, score_value) VALUES (?,?,?,?)",
        (qid, data["text"], data["quality_label"], int(data["score_value"])),
    )
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/answers/<int:aid>", methods=["PUT"])
def update_answer(aid):
    data = request.json
    c = db()
    c.execute(
        "UPDATE possible_answers SET text=?, quality_label=?, score_value=? WHERE id=?",
        (data["text"], data["quality_label"], int(data["score_value"]), aid),
    )
    c.commit()
    return jsonify({"success": True})


@app.route("/api/answers/<int:aid>", methods=["DELETE"])
def delete_answer(aid):
    c = db()
    used = c.execute(
        "SELECT COUNT(*) FROM session_responses WHERE selected_answer_id=?", (aid,)
    ).fetchone()[0]
    if used:
        return jsonify({"error": f"Cannot delete — selected in {used} session(s)."}), 400
    c.execute("DELETE FROM possible_answers WHERE id=?", (aid,))
    c.commit()
    return jsonify({"success": True})


@app.route("/api/questions/reorder", methods=["POST"])
def reorder_questions():
    items = request.json   # [{"id": 1, "order_index": 2}, ...]
    c = db()
    for item in items:
        c.execute("UPDATE questions SET order_index=? WHERE id=?", (item["order_index"], item["id"]))
    c.commit()
    return jsonify({"success": True})


if __name__ == "__main__":
    init()
    app.run(debug=True, port=5001)
