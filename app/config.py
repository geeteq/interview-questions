"""
Application configuration.

Defaults are defined here. Anything in the environment overrides them — the
deploy script sets INTERVIEW_BASE_PATH and INTERVIEW_DB at runtime so the
same code base can run at the root or behind a reverse-proxy sub-path.
"""

import os
from pathlib import Path

# Base URL the app is served at. Used to build links in templates and to
# strip the prefix from incoming requests behind a reverse proxy.
# Examples: "/interview", "/iq", "" (root).
BASE_URL = os.environ.get("INTERVIEW_BASE_PATH", "/interview").rstrip("/")

# Filesystem path of the active SQLite DB. init_db.py also reads
# INTERVIEW_DB and treats this default as a fallback.
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DB_PATH = Path(os.environ.get("INTERVIEW_DB", PROJECT_ROOT / "db" / "interview.db"))

# Target interview length in minutes. Used by the admin UI to flag when the
# selected question set is over budget.
TARGET_INTERVIEW_MINUTES = int(os.environ.get("INTERVIEW_TARGET_MINUTES", 45))
