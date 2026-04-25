"""One-time migration: inserts Tech, Management, and HR question sets."""
import sqlite3

DB = "interview.db"

NEW_QUESTIONS = [
    # ── Tech ──────────────────────────────────────────────────────────────────
    {
        "text":       "What is the difference between a process and a thread, and when would you choose one over the other?",
        "category":   "Tech",
        "difficulty": 3,
        "weight":     2.0,
        "answers": [
            ("They are basically the same thing — just different words",
             "Dangerous",  0),
            ("A process is a running program; a thread is a smaller unit inside it",
             "Acceptable", 2),
            ("A process has its own memory space; threads share memory within a process. Use threads for concurrent tasks, processes for stronger isolation",
             "Good",       3),
            ("A process is an isolated execution unit with its own memory and resources. Threads share the process's memory, making them cheaper to spawn but requiring careful synchronisation. Choose processes for fault isolation or separate programs; threads for in-process concurrency where shared state is useful",
             "Excellent",  4),
            ("I have never heard of threads",
             "Poor",       1),
        ],
    },
    {
        "text":       "Users are reporting that your production API is very slow. Walk me through how you diagnose and fix it.",
        "category":   "Tech",
        "difficulty": 4,
        "weight":     2.5,
        "answers": [
            ("Restart the server and hope it resolves itself",
             "Poor",       1),
            ("Check the logs for errors and maybe restart some services",
             "Acceptable", 2),
            ("Check monitoring tools, look at slow query logs, profile code, check CPU/memory/IO, identify the bottleneck, then fix it",
             "Good",       3),
            ("Start with observability: check APM dashboards and trace slow requests, analyse DB query plans for N+1s or missing indexes, review caching effectiveness, check resource saturation, profile hotspots in code, then fix root cause with a staged rollout and verify with metrics",
             "Excellent",  4),
            ("Tell users the system is under maintenance and wait for it to recover",
             "Dangerous",  0),
        ],
    },
    {
        "text":       "Explain what a REST API is and what you consider to be good API design principles.",
        "category":   "Tech",
        "difficulty": 2,
        "weight":     1.5,
        "answers": [
            ("REST is a type of database",
             "Dangerous",  0),
            ("REST is an API that uses HTTP requests",
             "Acceptable", 2),
            ("REST uses HTTP methods (GET/POST/PUT/DELETE), stateless communication, and standard status codes. Good design means clear resource naming, versioning, and consistent error responses",
             "Good",       3),
            ("REST (Representational State Transfer) is a stateless architectural style over HTTP, identifying resources by URI. Good design includes: consistent noun-based resource paths, correct HTTP verbs, meaningful status codes, versioning, pagination, idempotency where appropriate, and thorough documentation",
             "Excellent",  4),
            ("I only know about SOAP and have not used REST",
             "Poor",       1),
        ],
    },
    {
        "text":       "How would you design a system that needs to handle 10,000 concurrent users reliably?",
        "category":   "Tech",
        "difficulty": 5,
        "weight":     3.0,
        "answers": [
            ("Buy the most powerful single server available",
             "Poor",       1),
            ("Use a load balancer and a few servers",
             "Acceptable", 2),
            ("Horizontal scaling behind a load balancer, stateless services, caching (Redis), CDN for static assets, async queues for heavy tasks, auto-scaling",
             "Good",       3),
            ("Start with requirements (read-heavy vs write-heavy, latency SLA, data consistency). Design stateless services behind an auto-scaling load balancer, multi-layer caching (CDN + Redis), async queues for heavy workloads, DB read replicas or sharding as needed, circuit breakers and retries for resilience, observability from day one",
             "Excellent",  4),
            ("It is impossible to handle that many users on a single system",
             "Dangerous",  0),
        ],
    },

    # ── Management ────────────────────────────────────────────────────────────
    {
        "text":       "Two of your team members are in open conflict and it is affecting the whole team's output. How do you handle it?",
        "category":   "Management",
        "difficulty": 3,
        "weight":     2.0,
        "answers": [
            ("Let them sort it out themselves — adults should handle their own problems",
             "Poor",       1),
            ("Tell both of them to be professional and get along",
             "Acceptable", 2),
            ("Meet with each person separately to understand both perspectives without taking sides, then facilitate a structured conversation to find a resolution",
             "Good",       3),
            ("Hold separate 1-on-1s to understand root causes, facilitate a structured mediation with clear ground rules, set explicit behavioural expectations, follow up regularly, shield the rest of the team during resolution, and escalate to HR if behaviour persists",
             "Excellent",  4),
            ("Remove one of them from the team to solve the problem quickly",
             "Dangerous",  0),
        ],
    },
    {
        "text":       "A key project is three weeks behind schedule with two weeks left. What do you do?",
        "category":   "Management",
        "difficulty": 4,
        "weight":     2.5,
        "answers": [
            ("Push the team to work overtime until the deadline is met",
             "Poor",       1),
            ("Tell stakeholders the deadline cannot be met and move on",
             "Dangerous",  0),
            ("Analyse root cause of the delay, identify critical path, cut scope where possible, and communicate a revised timeline clearly to stakeholders",
             "Good",       3),
            ("Do a rapid root-cause analysis, re-baseline the critical path, identify what can be fast-tracked or descoped without compromising quality, add targeted resources if it helps, communicate proactively to stakeholders with a transparent recovery plan and options, and put early-warning checks in place going forward",
             "Excellent",  4),
            ("Double the team size immediately to speed things up",
             "Acceptable", 2),
        ],
    },
    {
        "text":       "How do you set goals for your team and make sure they are actually met?",
        "category":   "Management",
        "difficulty": 3,
        "weight":     2.0,
        "answers": [
            ("I assign tasks and trust the team to let me know if there are issues",
             "Acceptable", 2),
            ("I set goals based on what I think is achievable and check in monthly",
             "Poor",       1),
            ("I use SMART goals, review them in 1-on-1s, and track progress in regular team meetings with clear milestones",
             "Good",       3),
            ("I co-create goals with each team member aligned to business objectives using SMART criteria, break them into milestones, hold regular 1-on-1s and team reviews to catch blockers early, adjust course proactively, and connect goals to personal growth to maintain motivation",
             "Excellent",  4),
            ("Goals are set by upper management; I just pass them down",
             "Poor",       1),
        ],
    },

    # ── HR ────────────────────────────────────────────────────────────────────
    {
        "text":       "Tell me about a time you received critical feedback. How did you react and what did you do with it?",
        "category":   "HR",
        "difficulty": 2,
        "weight":     1.5,
        "answers": [
            ("I disagreed and pushed back — the feedback was not fair",
             "Poor",       1),
            ("I accepted it and tried to do better going forward",
             "Acceptable", 2),
            ("I listened openly, asked clarifying questions to make sure I understood, thanked the person, and made a concrete plan to address the areas mentioned",
             "Good",       3),
            ("I listened without defensiveness, asked for specific examples to fully understand, reflected on the feedback privately, built an improvement plan with measurable steps, followed up with the person to demonstrate progress, and used it as a catalyst for long-term growth",
             "Excellent",  4),
            ("I reported the person to HR for being too harsh",
             "Dangerous",  0),
        ],
    },
    {
        "text":       "Where do you see yourself professionally in five years?",
        "category":   "HR",
        "difficulty": 1,
        "weight":     1.0,
        "answers": [
            ("Doing exactly the same job I am doing now",
             "Poor",       1),
            ("I have not really thought about it",
             "Poor",       1),
            ("I would like to grow into a more senior role with greater responsibility",
             "Acceptable", 2),
            ("I want to deepen my expertise in my field, take on broader leadership responsibility, and contribute meaningfully to the organisation's growth — ideally in a senior or lead capacity",
             "Good",       3),
            ("I have a clear development plan: build deep expertise in X over the next two years, move into a team lead or principal role by year three, and eventually grow toward a director-level position while actively mentoring others along the way",
             "Excellent",  4),
        ],
    },
    {
        "text":       "Describe a situation where you had to work closely with a very difficult colleague or stakeholder. How did you manage it?",
        "category":   "HR",
        "difficulty": 3,
        "weight":     2.0,
        "answers": [
            ("I avoided them as much as possible and worked around them",
             "Poor",       1),
            ("I asked my manager to handle the situation for me",
             "Acceptable", 2),
            ("I found a way to work around the friction and completed the project successfully despite the difficulty",
             "Acceptable", 2),
            ("I tried to understand their perspective, found common ground, adapted my communication style to reduce friction, and built enough trust to work together productively",
             "Good",       3),
            ("I proactively sought 1-on-1 time to understand their concerns and motivations, identified shared goals to anchor the relationship, adapted my communication style, kept interactions transparent and documented, and ultimately turned the dynamic into a productive working relationship that improved the project outcome",
             "Excellent",  4),
        ],
    },
]


def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    max_order = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM questions").fetchone()[0]
    existing  = {r["text"] for r in conn.execute("SELECT text FROM questions").fetchall()}

    added = 0
    for q in NEW_QUESTIONS:
        if q["text"] in existing:
            print(f"  skip (exists): {q['text'][:60]}…")
            continue
        max_order += 1
        cur = conn.execute(
            "INSERT INTO questions (text, category, difficulty, weight, order_index) VALUES (?,?,?,?,?)",
            (q["text"], q["category"], q["difficulty"], q["weight"], max_order),
        )
        qid = cur.lastrowid
        for text, quality, score in q["answers"]:
            conn.execute(
                "INSERT INTO possible_answers (question_id, text, quality_label, score_value) VALUES (?,?,?,?)",
                (qid, text, quality, score),
            )
        print(f"  added [{q['category']}] {q['text'][:65]}…")
        added += 1

    conn.commit()
    conn.close()
    print(f"\nDone. {added} question(s) added.")


if __name__ == "__main__":
    run()
