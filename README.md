# Interview Questions

A self-hosted interview management tool built with Flask and SQLite. Run structured interviews with a live candidate screen, a real-time admin control panel, a question bank manager, full session recording, and an admin chat.

---

## Features

### Candidate screen (`/`)
- Displays one question at a time, full-screen
- Polls every 2 seconds — updates instantly when the admin advances
- Animated question transitions
- Shows progress indicator and candidate name

### Admin interview panel (`/admin`)
- Start or rejoin an active session by candidate name
- See the current question with all possible answers, each labelled with a quality badge (Excellent → Dangerous) and weighted point value
- Select the answer that best matches the candidate's response
- Add free-text interviewer comments per question
- Click **Next Question** to advance — the candidate screen updates in real time
- Click **Finish Interview** on the last question to close the session and view results
- Results summary: score per question, quality, comment, total percentage, and grade

### Question bank (`/admin/questions`)
- Full CRUD for questions: text, category, difficulty (1–5), weight (score multiplier)
- Per-question answer management: add, edit, delete answers with quality/score mapping
- Reorder questions with ↑↓ buttons — interview order updates immediately
- Filter questions by category with a pill bar

### Session records (`/admin/sessions`)
- Stats overview: total sessions, completion rate, average score, top candidate
- Expandable session rows showing full Q&A breakdown, answer quality, scores, and interviewer comments
- Admin chat log recorded alongside each session

### Admin chat
- Fixed bottom-right chat widget on the admin panel
- Scoped per session — all admins viewing the same session share one chat thread
- Messages are saved to the database and appear in the session record
- Unread badge when the panel is collapsed
- Name persisted in `localStorage` — set once, remembered forever

---

## Tech stack

| Layer    | Technology                        |
|----------|-----------------------------------|
| Backend  | Python 3 · Flask                  |
| Database | SQLite (single file, zero config) |
| Frontend | Vanilla HTML / CSS / JS (no build step) |
| Realtime | Client-side polling (2 s interval) |

---

## Project structure

```
interview-questions/
├── app.py                  # Flask application — all routes and API endpoints
├── init_db.py              # Schema creation + sample question seed
├── add_categories.py       # One-time migration: Tech / Management / HR questions
├── requirements.txt
└── templates/
    ├── user.html           # Candidate screen
    ├── admin.html          # Interview control panel
    ├── admin_questions.html# Question bank manager
    └── admin_sessions.html # Session records and results
```

---

## Database schema

| Table               | Purpose                                              |
|---------------------|------------------------------------------------------|
| `questions`         | Question text, category, difficulty, weight, order   |
| `possible_answers`  | Answer options with quality label and score (0–4)    |
| `sessions`          | Candidate name, start/end timestamps                 |
| `session_state`     | Current question index and active/complete status    |
| `session_responses` | Admin-selected answer, comment, and score per question |
| `session_chat`      | Admin chat messages scoped to a session              |

**Scoring:** `score_value (0–4) × question weight = points earned`. Maximum per question = `4 × weight`.

**Grades:** Outstanding ≥ 85% · Strong ≥ 70% · Adequate ≥ 55% · Weak ≥ 35% · Poor < 35%

---

## Sample questions

15 questions across 6 categories, ordered for the interview as:

1. **Management** (3) — team conflict, schedule recovery, goal-setting
2. **Tech** (4) — process vs thread, API debugging, REST design, system design at scale
3. **HR** (3) — handling feedback, 5-year plan, difficult colleagues
4. Safety, Adaptability, Ethics & Security (5 legacy questions)

Each question has 5 possible answers covering the full quality spectrum.
