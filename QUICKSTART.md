# Quickstart

## Prerequisites

- Python 3.9+
- pip / venv

---

## 1 — Install

```bash
git clone https://github.com/geeteq/interview-questions.git
cd interview-questions

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2 — Initialise the database

The DB lives in `db/interview.db` (created on first run). Pick one seed:

```bash
cd app
python init_db.py          # 5 hard-coded sample questions
python init_db_random.py   # 15 random questions from db/master.sql
python init_db_master.py   # full master bank from db/master.sql
```

For the random/master variants, copy `src/master.sql` to `db/master.sql`
first, or run with `INTERVIEW_MASTER_SQL=src/master.sql`.

---

## 3 — Start the server

```bash
cd app
python app.py
```

The app runs on **http://localhost:5002**. By default `BASE_URL=/interview`
is injected into rendered links — set `INTERVIEW_BASE_PATH=""` to serve at
the root for local development.

---

## 4 — Open the two screens

| Screen | URL | Who sees it |
|--------|-----|-------------|
| Candidate | http://localhost:5001 | The person being interviewed (show on a separate monitor or shared screen) |
| Admin | http://localhost:5001/admin | The interviewer(s) |

---

## 5 — Run an interview

1. Go to **http://localhost:5001/admin**
2. Enter the candidate's name in the **Start new interview** panel (top right) and click **▶ Start Session**
3. The candidate screen updates automatically — show it to the candidate
4. For each question:
   - Select the answer option that best matches what the candidate said
   - Add an optional comment in the text box
   - Click **Next Question →**
5. On the last question, click **Finish Interview ✓**
6. The results page appears immediately with scores, quality ratings, and a grade

---

## 6 — Manage questions

Go to **http://localhost:5001/admin/questions** to:

- Add, edit, or delete questions
- Manage the answer options for each question
- Reorder questions with the ↑↓ arrows (order = interview sequence)
- Filter by category using the pill bar at the top

---

## 7 — Review past sessions

Go to **http://localhost:5001/admin/sessions** to:

- See all sessions with scores and grades at a glance
- Click any completed session to expand the full breakdown
- Review interviewer comments and the admin chat log per session

---

## Admin chat

The **💬 Admin Chat** button is fixed to the bottom-right of the admin panel. It is scoped to the active session — any admin with the same session open can send messages. All messages are saved to the database and visible in the session record.

First time you open the chat, you will be prompted for your name. It is saved in `localStorage` and never asked again.

---

## Rejoin an active session

If you close or refresh the admin tab mid-interview:

- The page **auto-rejoins** the active session on load
- Or click **Rejoin →** next to any active session in the Past sessions sidebar

The candidate screen keeps showing the current question throughout — it is unaffected by admin navigation.

---

## Reset / start fresh

To wipe all session data and start clean (questions are kept):

```bash
python3 -c "
import sqlite3; c = sqlite3.connect('interview.db')
c.execute('DELETE FROM session_chat')
c.execute('DELETE FROM session_responses')
c.execute('DELETE FROM session_state')
c.execute('DELETE FROM sessions')
c.commit()
print('Sessions cleared.')
"
```
