from pathlib import Path
import re

# ---------------------------------------------------------------------------
# Paths
# config.py lives at scripts/genealogie/config.py, so .parent x3 = repo root
# ---------------------------------------------------------------------------
HUGO_DIR   = Path(__file__).parent.parent.parent
DATA_FILE  = HUGO_DIR / "data" / "famille.json"        # master person database
PPL_DIR    = HUGO_DIR / "content" / "personnes"        # auto-generated Hugo pages
PHOTOS_DIR = HUGO_DIR / "static" / "images" / "personnes"  # uploaded portraits
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# CORS — the local API runs on 1315; Hugo dev server runs on 1314.
# Only requests from the Hugo dev server are allowed; never widen to "*".
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS    = {"http://localhost:1314", "http://127.0.0.1:1314"}
CORS_METHODS       = "GET, PATCH, POST, DELETE, OPTIONS"
CORS_HEADERS_ALLOW = "Content-Type"

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES   = 10 * 1024 * 1024   # 10 MB hard cap for photo uploads
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Gramps person IDs look like "I1", "I351", "0497" — alphanumeric, max 40 chars.
GID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
