# Note 1: pathlib.Path provides an object-oriented interface to filesystem paths.
# It is preferred over os.path for new code because it handles OS differences
# automatically and supports the / operator for path joining.
from pathlib import Path
# Note 2: re is the standard-library regular-expression module. The GID_RE
# pattern compiled at the bottom of this file validates Gramps person IDs.
import re

# ---------------------------------------------------------------------------
# Paths
# config.py lives at scripts/genealogie/config.py, so .parent x3 = repo root
# ---------------------------------------------------------------------------
# Note 3: __file__ is a special Python variable set to the absolute path of
# the current module at import time. Calling .parent three times walks up:
#   genealogie/ -> scripts/ -> genealogie (repo root).
HUGO_DIR   = Path(__file__).parent.parent.parent
DATA_FILE  = HUGO_DIR / "data" / "famille.json"        # master person database
PPL_DIR    = HUGO_DIR / "content" / "personnes"        # auto-generated Hugo pages
PHOTOS_DIR = HUGO_DIR / "static" / "images" / "personnes"  # uploaded portraits
# Note 4: mkdir(parents=True, exist_ok=True) is idempotent — safe to call on
# every startup. parents=True creates any missing intermediate directories.
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# CORS — the local API runs on 1315; Hugo dev server commonly runs on 1313
# (default) or 1314. Only local development origins are allowed; never widen
# to "*".
# ---------------------------------------------------------------------------
# Note 5: CORS (Cross-Origin Resource Sharing) is a browser security mechanism.
# The API server returns Access-Control-Allow-Origin only for origins in this
# whitelist. A wildcard (*) would allow any page on the internet to call the
# API — never acceptable even for a local-only server.
ALLOWED_ORIGINS    = {
    "http://localhost:1313",
    "http://127.0.0.1:1313",
    "http://localhost:1314",
    "http://127.0.0.1:1314",
}
CORS_METHODS       = "GET, PATCH, POST, DELETE, OPTIONS"
CORS_HEADERS_ALLOW = "Content-Type"

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
# Note 6: Limiting upload size prevents accidental or malicious large uploads
# from exhausting disk space or memory. 10 MB is generous for portrait photos.
MAX_UPLOAD_BYTES   = 10 * 1024 * 1024   # 10 MB hard cap for photo uploads
# Note 7: ALLOWED_EXTENSIONS restricts uploads to known image types.
# Magic-byte validation in handlers.py adds a second layer of defence.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Note 8: re.compile() pre-compiles the regex once at module load time so it
# is not reparsed on every validation call. GID_RE accepts Gramps person IDs
# like "I1", "I351", "0497" — alphanumeric plus _ and -, max 40 characters.
# Gramps person IDs look like "I1", "I351", "0497" — alphanumeric, max 40 chars.
GID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
