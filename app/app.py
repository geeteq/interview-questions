from flask import Flask, render_template, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.exceptions import NotFound
import sqlite3
from datetime import datetime
from config import BASE_URL, DB_PATH, TARGET_INTERVIEW_MINUTES
from init_db import init

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Templates still expect `base_path`; keep the name for backward compat.
BASE_PATH = BASE_URL
DB = str(DB_PATH)

@app.context_processor
def _inject_base():
    return {
        "base_path": BASE_PATH,
        "target_interview_minutes": TARGET_INTERVIEW_MINUTES,
    }


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def session_questions(c, sid):
    """Return ordered question rows for a session.
    Uses session_questions if populated, otherwise falls back to all questions
    by global order_index (preserves behavior for sessions created before
    per-session selection existed)."""
    rows = c.execute(
        """SELECT q.* FROM session_questions sq
           JOIN questions q ON q.id = sq.question_id
           WHERE sq.session_id=?
           ORDER BY sq.order_index""",
        (sid,),
    ).fetchall()
    if rows:
        return rows
    return c.execute("SELECT * FROM questions ORDER BY order_index").fetchall()


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route("/")
def candidate_screen():
    return render_template("user.html")


@app.route("/admin")
def admin_screen():
    return render_template("admin.html")


@app.route("/admin/categories")
def admin_categories():
    return render_template("admin_categories.html")


# ── Candidate polling endpoint ─────────────────────────────────────────────────

@app.route("/api/state")
def state():
    """Polled by the candidate screen every 2 s to get the current question."""
    c = db()
    session = c.execute(
        "SELECT * FROM sessions WHERE completed_at IS NULL AND archived=0 ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    if not session:
        return jsonify({"status": "waiting"})

    st = c.execute(
        "SELECT * FROM session_state WHERE session_id=?", (session["id"],)
    ).fetchone()

    if not st or st["status"] == "complete":
        return jsonify({"status": "complete", "session_id": session["id"],
                        "candidate": session["candidate_name"]})

    questions = session_questions(c, session["id"])
    qi = st["current_question_index"]

    if qi >= len(questions):
        return jsonify({"status": "complete", "session_id": session["id"],
                        "candidate": session["candidate_name"]})

    q = questions[qi]
    sq = c.execute(
        "SELECT published_at FROM session_questions WHERE session_id=? AND question_id=?",
        (session["id"], q["id"]),
    ).fetchone()
    diagram_published = bool(sq and sq["published_at"])
    return jsonify({
        "status":        "active",
        "session_id":    session["id"],
        "candidate":     session["candidate_name"],
        "q_number":      qi + 1,
        "q_total":       len(questions),
        "question": {
            "id":          q["id"],
            "text":        q["text"],
            "category":    q["category"],
            "difficulty":  q["difficulty"],
            # Candidate sees the diagram only after the admin publishes it for this session.
            "has_diagram": bool(q["diagram_xml"]) and diagram_published,
        },
    })


# ── Session management ─────────────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    archived = 1 if request.args.get("archived") == "1" else 0
    c = db()
    rows = c.execute(
        "SELECT * FROM sessions WHERE archived=? ORDER BY started_at DESC",
        (archived,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions/<int:sid>/archive", methods=["POST"])
def archive_session(sid):
    data = request.json or {}
    archived = 1 if data.get("archived", True) else 0
    c = db()
    found = c.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
    if not found:
        return jsonify({"error": "Not found"}), 404
    c.execute("UPDATE sessions SET archived=? WHERE id=?", (archived, sid))
    c.commit()
    return jsonify({"success": True, "archived": bool(archived)})


@app.route("/api/sessions/<int:sid>", methods=["DELETE"])
def delete_session(sid):
    c = db()
    row = c.execute("SELECT archived FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if not row["archived"]:
        return jsonify({"error": "Session must be archived before deletion."}), 400
    c.execute("DELETE FROM session_chat      WHERE session_id=?", (sid,))
    c.execute("DELETE FROM session_responses WHERE session_id=?", (sid,))
    c.execute("DELETE FROM session_state     WHERE session_id=?", (sid,))
    c.execute("DELETE FROM session_questions WHERE session_id=?", (sid,))
    c.execute("DELETE FROM session_diagrams  WHERE session_id=?", (sid,))
    c.execute("DELETE FROM sessions          WHERE id=?",         (sid,))
    c.commit()
    return jsonify({"success": True})


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

    # Resolve which question IDs to include in this session
    qids = data.get("question_ids")
    if qids:
        # Validate that the IDs are real, non-archived questions
        placeholders = ",".join("?" * len(qids))
        valid = c.execute(
            f"SELECT id FROM questions WHERE id IN ({placeholders}) AND archived=0",
            qids,
        ).fetchall()
        valid_ids = {r["id"] for r in valid}
        ordered = [qid for qid in qids if qid in valid_ids]
    else:
        rows = c.execute(
            """SELECT q.id FROM questions q
               LEFT JOIN category_order co ON co.category = q.category
               WHERE q.archived = 0
               ORDER BY COALESCE(co.priority, 100), q.category, q.order_index"""
        ).fetchall()
        ordered = [r["id"] for r in rows]

    if not ordered:
        return jsonify({"error": "No questions selected for the session."}), 400

    cur = c.execute(
        "INSERT INTO sessions (candidate_name, started_at) VALUES (?,?)",
        (data["candidate_name"], datetime.now().isoformat()),
    )
    sid = cur.lastrowid
    c.execute(
        "INSERT INTO session_state (session_id, current_question_index, status) VALUES (?,0,'active')",
        (sid,),
    )
    for i, qid in enumerate(ordered, start=1):
        c.execute(
            "INSERT INTO session_questions (session_id, question_id, order_index) VALUES (?,?,?)",
            (sid, qid, i),
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

    questions = session_questions(c, sid)
    qi = st["current_question_index"]

    if qi >= len(questions):
        return jsonify({"status": "complete"})

    q = questions[qi]
    answers = c.execute(
        "SELECT * FROM possible_answers WHERE question_id=? ORDER BY score_value DESC",
        (q["id"],),
    ).fetchall()

    sq = c.execute(
        "SELECT published_at FROM session_questions WHERE session_id=? AND question_id=?",
        (sid, q["id"]),
    ).fetchone()

    return jsonify({
        "status":         "active",
        "question_index": qi,
        "total":          len(questions),
        "question": {
            "id":          q["id"],
            "text":        q["text"],
            "category":    q["category"],
            "difficulty":  q["difficulty"],
            "weight":      q["weight"],
            "max_points":  round(q["weight"] * 4, 2),
            "has_diagram": bool(q["diagram_xml"]),
            "diagram_published_at": sq["published_at"] if sq else None,
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

@app.route("/api/sessions/<int:sid>/cancel", methods=["POST"])
def cancel_session(sid):
    """End an in-progress session immediately. Already-saved responses stay
    intact so the partial result is preserved on the Sessions page; remaining
    questions are simply not asked. The session is marked complete just like
    a normal finish."""
    c = db()
    st = c.execute(
        "SELECT * FROM session_state WHERE session_id=?", (sid,)
    ).fetchone()
    if not st:
        return jsonify({"error": "Session not found"}), 404

    if st["status"] != "complete":
        c.execute(
            "UPDATE session_state SET status='complete' WHERE session_id=?",
            (sid,),
        )
        c.execute(
            "UPDATE sessions SET completed_at=? WHERE id=?",
            (datetime.now().isoformat(), sid),
        )
        c.commit()
    return jsonify({"success": True})


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
    questions = session_questions(c, sid)

    if qi < len(questions):
        q = questions[qi]
        skipped   = bool(data.get("skip"))
        answer_id = None if skipped else data.get("answer_id")
        comment   = data.get("comment", "")

        if answer_id and not skipped:
            ans   = c.execute("SELECT * FROM possible_answers WHERE id=?", (answer_id,)).fetchone()
            score = round(float(ans["score_value"]) * float(q["weight"]), 2) if ans else 0.0
        else:
            score = 0.0

        c.execute(
            """INSERT INTO session_responses
               (session_id, question_id, selected_answer_id, admin_comment, score_awarded, skipped, evaluated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, q["id"], answer_id, comment, score, 1 if skipped else 0, datetime.now().isoformat()),
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
                  (q.diagram_xml IS NOT NULL AND q.diagram_xml != '') AS q_has_diagram,
                  sd.submitted_at AS sd_submitted_at,
                  pa.text          AS a_text,
                  pa.quality_label AS a_quality,
                  pa.score_value   AS a_score_value
           FROM session_responses sr
           JOIN questions q          ON q.id  = sr.question_id
           LEFT JOIN possible_answers pa ON pa.id = sr.selected_answer_id
           LEFT JOIN session_diagrams sd ON sd.session_id = sr.session_id AND sd.question_id = sr.question_id
           WHERE sr.session_id=?
           ORDER BY sr.id""",
        (sid,),
    ).fetchall()

    scored    = [r for r in responses if not r["skipped"]]
    max_score = sum(float(r["q_weight"]) * 4 for r in scored)
    total     = sum(float(r["score_awarded"]) for r in scored)
    pct       = round(total / max_score * 100, 1) if max_score else 0

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
                "question_id": r["question_id"],
                "question":    r["q_text"],
                "category":    r["q_category"],
                "difficulty":  r["q_difficulty"],
                "weight":      r["q_weight"],
                "max_points":  round(float(r["q_weight"]) * 4, 2),
                "answer":      "— skipped —" if r["skipped"] else (r["a_text"] or "— no answer selected —"),
                "quality":     "Skipped" if r["skipped"] else (r["a_quality"] or "—"),
                "score_raw":   r["a_score_value"],
                "score_earned":round(float(r["score_awarded"]), 2),
                "comment":     r["admin_comment"],
                "skipped":     bool(r["skipped"]),
                "has_diagram": bool(r["q_has_diagram"]),
                "submitted_diagram_at": r["sd_submitted_at"],
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
    """List questions. ?archived=0 (default) | 1 | all"""
    arg = request.args.get("archived", "0")
    c = db()
    if arg == "all":
        where = ""
        params = ()
    else:
        where = "WHERE q.archived=?"
        params = (1 if arg == "1" else 0,)
    rows = c.execute(
        f"""SELECT q.id, q.text, q.category, q.difficulty, q.weight, q.avg_minutes,
                   q.order_index, q.archived,
                   COALESCE(co.priority, 100) AS category_priority,
                   (q.diagram_xml IS NOT NULL AND q.diagram_xml != '') AS has_diagram,
                   COUNT(pa.id) AS answer_count
            FROM questions q
            LEFT JOIN possible_answers pa ON pa.question_id = q.id
            LEFT JOIN category_order  co ON co.category    = q.category
            {where}
            GROUP BY q.id
            ORDER BY category_priority, q.category, q.order_index""",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/questions/<int:qid>/diagram", methods=["GET"])
def get_question_diagram(qid):
    c = db()
    row = c.execute("SELECT diagram_xml FROM questions WHERE id=?", (qid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if not row["diagram_xml"]:
        return jsonify({"error": "No diagram"}), 404
    return jsonify({"xml": row["diagram_xml"]})


@app.route("/api/questions/<int:qid>/diagram", methods=["POST"])
def upload_question_diagram(qid):
    data = request.json or {}
    xml = data.get("xml", "").strip()
    if not xml:
        return jsonify({"error": "XML content required."}), 400
    c = db()
    found = c.execute("SELECT id FROM questions WHERE id=?", (qid,)).fetchone()
    if not found:
        return jsonify({"error": "Not found"}), 404
    c.execute("UPDATE questions SET diagram_xml=? WHERE id=?", (xml, qid))
    c.commit()
    return jsonify({"success": True})


@app.route("/api/questions/<int:qid>/diagram", methods=["DELETE"])
def delete_question_diagram(qid):
    c = db()
    found = c.execute("SELECT id FROM questions WHERE id=?", (qid,)).fetchone()
    if not found:
        return jsonify({"error": "Not found"}), 404
    c.execute("UPDATE questions SET diagram_xml=NULL WHERE id=?", (qid,))
    c.commit()
    return jsonify({"success": True})


@app.route("/api/sessions/<int:sid>/diagram", methods=["GET"])
def get_session_diagram(sid):
    qid = request.args.get("question_id", type=int)
    if not qid:
        return jsonify({"error": "question_id required"}), 400
    c = db()
    row = c.execute(
        "SELECT xml, submitted_at FROM session_diagrams WHERE session_id=? AND question_id=?",
        (sid, qid),
    ).fetchone()
    if not row:
        return jsonify({"error": "No submission"}), 404
    return jsonify({"xml": row["xml"], "submitted_at": row["submitted_at"]})


@app.route("/api/sessions/<int:sid>/submit-diagram", methods=["POST"])
def submit_session_diagram(sid):
    data = request.json or {}
    qid = data.get("question_id")
    xml = (data.get("xml") or "").strip()
    if not qid or not xml:
        return jsonify({"error": "question_id and xml required."}), 400
    c = db()
    sess = c.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        return jsonify({"error": "Session not found"}), 404
    c.execute(
        """INSERT INTO session_diagrams (session_id, question_id, xml, submitted_at)
           VALUES (?,?,?,?)
           ON CONFLICT(session_id, question_id) DO UPDATE SET
             xml=excluded.xml,
             submitted_at=excluded.submitted_at""",
        (sid, qid, xml, datetime.now().isoformat()),
    )
    c.commit()
    return jsonify({"success": True})


@app.route("/api/sessions/<int:sid>/publish-diagram", methods=["POST"])
def publish_session_diagram(sid):
    """Publish (or unpublish) the base diagram for a question to the candidate.

    Body: { "question_id": int, "published": bool (default true) }
    The candidate's poll picks this up via /api/state and reveals the diagram
    on their screen — used by the interviewer to "show the answer" after the
    candidate has had a chance to figure it out themselves.
    """
    data = request.json or {}
    qid = data.get("question_id")
    publish = data.get("published", True)
    if not qid:
        return jsonify({"error": "question_id required"}), 400
    c = db()
    found = c.execute(
        "SELECT 1 FROM session_questions WHERE session_id=? AND question_id=?",
        (sid, qid),
    ).fetchone()
    if not found:
        return jsonify({"error": "Question is not part of this session."}), 400
    ts = datetime.now().isoformat() if publish else None
    c.execute(
        "UPDATE session_questions SET published_at=? WHERE session_id=? AND question_id=?",
        (ts, sid, qid),
    )
    c.commit()
    return jsonify({"success": True, "published_at": ts})


@app.route("/api/questions/<int:qid>/archive", methods=["POST"])
def archive_question(qid):
    data = request.json or {}
    archived = 1 if data.get("archived", True) else 0
    c = db()
    found = c.execute("SELECT id FROM questions WHERE id=?", (qid,)).fetchone()
    if not found:
        return jsonify({"error": "Not found"}), 404
    c.execute("UPDATE questions SET archived=? WHERE id=?", (archived, qid))
    c.commit()
    return jsonify({"success": True, "archived": bool(archived)})


@app.route("/api/questions", methods=["POST"])
def create_question():
    from init_db import estimate_minutes
    data = request.json
    c = db()
    category = data["category"]
    difficulty = int(data["difficulty"])
    avg_minutes = float(data.get("avg_minutes") or estimate_minutes(category, difficulty))
    max_order = c.execute("SELECT COALESCE(MAX(order_index), 0) FROM questions").fetchone()[0]
    cur = c.execute(
        "INSERT INTO questions (text, category, difficulty, weight, avg_minutes, order_index) "
        "VALUES (?,?,?,?,?,?)",
        (data["text"], category, difficulty, float(data["weight"]), avg_minutes, max_order + 1),
    )
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/questions/<int:qid>", methods=["PUT"])
def update_question(qid):
    from init_db import estimate_minutes
    data = request.json
    c = db()
    category = data["category"]
    difficulty = int(data["difficulty"])
    avg_minutes = float(data.get("avg_minutes") or estimate_minutes(category, difficulty))
    c.execute(
        "UPDATE questions SET text=?, category=?, difficulty=?, weight=?, avg_minutes=? WHERE id=?",
        (data["text"], category, difficulty, float(data["weight"]), avg_minutes, qid),
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


# ── Category priority ─────────────────────────────────────────────────────────

@app.route("/api/categories", methods=["GET"])
def list_categories():
    """All categories that exist on at least one question, plus their priority
    and active/archived counts. Sorted by priority then name."""
    c = db()
    rows = c.execute(
        """SELECT q.category,
                  COALESCE(co.priority, 100) AS priority,
                  SUM(CASE WHEN q.archived = 0 THEN 1 ELSE 0 END) AS active_count,
                  SUM(CASE WHEN q.archived = 1 THEN 1 ELSE 0 END) AS archived_count,
                  ROUND(SUM(CASE WHEN q.archived = 0 THEN q.avg_minutes ELSE 0 END), 1) AS active_minutes
           FROM questions q
           LEFT JOIN category_order co ON co.category = q.category
           GROUP BY q.category
           ORDER BY priority, q.category"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories/reorder", methods=["POST"])
def reorder_categories():
    """Bulk update of priorities. Body: [{"category": "...", "priority": 1}, ...]."""
    items = request.json or []
    c = db()
    for item in items:
        c.execute(
            "INSERT INTO category_order (category, priority) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET priority = excluded.priority",
            (item["category"], int(item["priority"])),
        )
    c.commit()
    return jsonify({"success": True})


# Mount the whole app under BASE_URL so that /interview/... reaches the
# Flask routes whether we're running standalone (python app.py), behind
# gunicorn directly, or behind a reverse proxy that preserves the prefix.
if BASE_URL:
    _flask_wsgi = app.wsgi_app
    app.wsgi_app = DispatcherMiddleware(NotFound(), {BASE_URL: _flask_wsgi})


if __name__ == "__main__":
    init()
    app.run(debug=True, port=5002)
