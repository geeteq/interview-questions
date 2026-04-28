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
├── app/                    # Application code — Flask app, init scripts, templates
│   ├── app.py              # Flask routes and API endpoints
│   ├── config.py           # BASE_URL (default /interview) + DB_PATH defaults
│   ├── init_db.py          # Schema + 5 hard-coded sample questions
│   ├── init_db_random.py   # Seed db/interview.db with 15 random questions
│   ├── init_db_master.py   # Seed db/interview.db with the full master bank
│   ├── add_categories.py   # One-time migration: Tech / Management / HR
│   ├── requirements.txt
│   └── templates/
│       ├── user.html
│       ├── admin.html
│       ├── admin_questions.html
│       └── admin_sessions.html
├── db/                     # Runtime state lives here — gitignored
│   ├── interview.db        # Active SQLite DB
│   └── master.sql          # (only on hosts deployed with --master/--init-random)
├── src/                    # Master question bank — gitignored, never deployed wholesale
│   ├── Book1.xlsx          # Source of truth for question text + ideal answers
│   ├── import_questions.py # xlsx → master.db with generated distractor answers
│   ├── export_master_sql.py# master.db → master.sql for shipping to a host
│   ├── backup_master.sh    # Tarball + checksum the master bank
│   ├── master.db           # Local master SQLite (regenerated from xlsx)
│   └── master.sql          # Portable export consumed by the deploy script
└── deploy.sh               # RHEL/CentOS deploy with --init / --init-random / --master
```

`db/` and `src/` are both gitignored. The active DB never lives next to the
code, and the master bank never leaves the maintainer's machine through git.

### Configuration

`app/config.py` defines two settings, both overridable by env vars:

| Setting   | Default                              | Env var                |
|-----------|--------------------------------------|------------------------|
| BASE_URL  | `/interview`                         | `INTERVIEW_BASE_PATH`  |
| DB_PATH   | `<project-root>/db/interview.db`     | `INTERVIEW_DB`         |

The deploy script sets both at runtime via `systemd` so the same code can
serve at the root or behind a reverse-proxy sub-path.

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

`init_db.py` ships 5 hard-coded sample questions covering Safety, Time
Management, Interpersonal, Adaptability, and Ethics & Security. They are
safe to commit and demonstrate the schema + scoring rubric.

Each question has 5 possible answers covering the full quality spectrum
(Excellent / Good / Acceptable / Poor / Dangerous mapped to score 4-0).

---

## Master question bank (maintainer workflow)

The real interview questions live in `src/Book1.xlsx`. Three small scripts
turn the xlsx into something the deploy script can ship:

```bash
# 1. Pull questions out of the xlsx, generate distractor answers,
#    write them to src/master.db
python src/import_questions.py

# 2. Dump master.db to a portable SQL file
python src/export_master_sql.py
```

`src/master.sql` is what `deploy.sh --master` and `deploy.sh --init-random`
consume on the target host. Everything in `src/` is gitignored.

### Backups (do this often)

The master bank is the most valuable artifact in this project — losing it
means rebuilding every question and ideal answer by hand.

```bash
bash src/backup_master.sh
# or to a removable drive:
BACKUP_DIR=/Volumes/USB/iq-backups bash src/backup_master.sh
```

The script verifies `master.db`'s integrity, refreshes `master.sql`, and
writes a timestamped, gzipped tarball (`master.db` + `master.sql` +
`Book1.xlsx`) plus a SHA-256 checksum into `~/.interview-questions-backups/`
(or wherever `BACKUP_DIR` points). Old backups are pruned after
`RETENTION_DAYS` (default 90) but the most recent `KEEP_MIN` (default 5)
are always retained.

**Treat each archive like a credential** — copy it off-machine, never to
git or a ticket.

---

## Deploying to a host

```bash
sudo bash deploy.sh                 # update code, keep existing DB
sudo bash deploy.sh --init          # 5 hard-coded sample questions
sudo bash deploy.sh --init-random   # 15 random picks from master.sql
sudo bash deploy.sh --master        # full master bank from master.sql
```

Init flags only fire when `interview.db` does not yet exist on the
target — existing candidate data is never overwritten.
