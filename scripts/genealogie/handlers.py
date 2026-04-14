import json
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from .config import (
    ALLOWED_ORIGINS, CORS_METHODS, CORS_HEADERS_ALLOW,
    MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS, GID_RE,
    HUGO_DIR, PHOTOS_DIR,
)
from .data import load_data, DataTransaction
from .markup import regen_markdown, update_references


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="/tmp/genealogie_api.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter — max 60 write requests per IP per minute
# ---------------------------------------------------------------------------
class _RateLimiter:
    def __init__(self, max_requests: int = 60, window: int = 60):
        self._max = max_requests
        self._window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        self._hits[ip] = [t for t in self._hits[ip] if now - t < self._window]
        if len(self._hits[ip]) >= self._max:
            return False
        self._hits[ip].append(now)
        return True


_rate_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# Image magic-byte validation (imghdr removed in Python 3.13)
# ---------------------------------------------------------------------------
def _is_valid_image(data: bytes) -> bool:
    """Return True only if *data* starts with a known image file signature."""
    if data[:3] == b"\xff\xd8\xff":                                        # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":                                   # PNG
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):                                 # GIF
        return True
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WebP
        return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cors_origin(headers):
    """Return the request Origin if it is in the whitelist, else None."""
    origin = headers.get("Origin", "")
    return origin if origin in ALLOWED_ORIGINS else None


def _send_cors_headers(handler):
    """Append CORS response headers to an in-progress response."""
    handler.send_header("Access-Control-Allow-Methods", CORS_METHODS)
    handler.send_header("Access-Control-Allow-Headers", CORS_HEADERS_ALLOW)
    origin = _cors_origin(handler.headers)
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)


def _safe_unlink_photo(photo_url: str | None) -> None:
    """Delete a photo file only if it is strictly inside PHOTOS_DIR.

    Uses Path.relative_to() — immune to path-traversal payloads that bypass
    startswith() comparisons (e.g. sibling directories with similar names).
    """
    if not photo_url:
        return
    rel = photo_url.removeprefix("/")
    candidate = (HUGO_DIR / "static" / rel).resolve()
    try:
        candidate.relative_to(PHOTOS_DIR.resolve())  # ValueError if outside
    except ValueError:
        _log.warning("Path traversal attempt blocked: %s", photo_url)
        return
    candidate.unlink(missing_ok=True)


def resolve_id(raw_id, persons):
    """Find the canonical key for raw_id in the persons dict.

    Gramps IDs can appear in different cases across old exports (e.g. "i1" vs
    "I1"). Try exact match first, then uppercase, then lowercase, then a
    full case-insensitive scan.  Returns raw_id unchanged if nothing matches
    (the caller will then get a 404).
    """
    if raw_id in persons:
        return raw_id
    upper = raw_id.upper()
    if upper in persons:
        return upper
    lower = raw_id.lower()
    if lower in persons:
        return lower
    raw_lower = raw_id.lower()
    for key in persons:
        if key.lower() == raw_lower:
            return key
    return raw_id  # not found — caller is responsible for returning 404


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class GenealogieHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local genealogy editing API.

    Endpoints
    ---------
    GET    /api/person/{id}   — fetch one person's data as JSON
    PATCH  /api/person/{id}   — update editable fields (nom, genre, dates…)
    POST   /api/photo/{id}    — upload a portrait image (multipart/form-data)
    DELETE /api/photo/{id}    — remove the portrait image
    OPTIONS /api/*            — CORS preflight (browser sends this before PATCH/POST/DELETE)
    """

    def log_message(self, fmt, *args):
        # Prefix each access-log line with the client address for clarity.
        print(f"  {self.address_string()} {fmt % args}")

    def send_json(self, code, obj):
        """Send a JSON response with the given HTTP status code."""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _send_cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------
    # OPTIONS — CORS preflight
    # ------------------------------------------------------------------

    def do_OPTIONS(self):
        origin_hdr = self.headers.get("Origin", "")
        if origin_hdr and origin_hdr not in ALLOWED_ORIGINS:
            # Reject preflight from unknown origins immediately.
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        _send_cors_headers(self)
        self.end_headers()

    # ------------------------------------------------------------------
    # GET /api/person/{id}
    # ------------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "person":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Identifiant invalide"})
                return

            data = load_data()
            gid  = resolve_id(raw_gid, data["personnes"])
            p = data["personnes"].get(gid)
            if p is None:
                self.send_json(404, {"error": "Personne introuvable"})
            else:
                self.send_json(200, {"id": gid, **p})
        else:
            self.send_json(404, {"error": "Route inconnue"})

    # ------------------------------------------------------------------
    # PATCH /api/person/{id}
    # Updates whitelisted fields only; propagates name changes to relatives.
    # ------------------------------------------------------------------

    def do_PATCH(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "person":
            if not _rate_limiter.is_allowed(self.client_address[0]):
                self.send_json(429, {"error": "Trop de requêtes. Réessayez dans une minute."})
                return

            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Identifiant invalide"})
                return

            length = int(self.headers.get("Content-Length", 0))
            if length > 64 * 1024:  # 64 KB is generous for a simple JSON edit form
                self.send_json(413, {"error": "Corps de requête trop volumineux"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, ValueError):
                self.send_json(400, {"error": "JSON invalide"})
                return
            if not isinstance(body, dict):
                self.send_json(400, {"error": "Corps de requête invalide"})
                return

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": "Personne introuvable"})
                    return

                p = persons[gid]
                old_nom = p.get("nom")

                # Only these fields may be edited via the API.
                # Structural data (parents, familles) is managed by parse_gramps.py.
                ALLOWED = ("nom", "genre", "naissance", "deces", "ville", "commentaires")
                for field in ALLOWED:
                    if field not in body:
                        continue
                    value = body[field]
                    if value is not None and not isinstance(value, str):
                        self.send_json(400, {"error": f"Champ '{field}' doit être une chaîne ou null"})
                        return
                    if isinstance(value, str) and len(value) > 1000:
                        self.send_json(400, {"error": f"Champ '{field}' trop long (max 1000 caractères)"})
                        return
                    p[field] = value.strip() if isinstance(value, str) else value

                new_nom = p.get("nom")
                if old_nom != new_nom:
                    # A rename must propagate to all denormalised name copies
                    # stored in other people's parents/conjoint/enfants lists.
                    update_references(persons, gid, old_nom, new_nom)

                regen_markdown(gid, p)
                result = {"id": gid, "ok": True, **p}
                _log.info("PATCH person/%s: %r → %r from %s", gid, old_nom, new_nom, self.client_address[0])
                print(f"  ✓ Updated {gid}: {old_nom!r} → {new_nom!r}")

            self.send_json(200, result)
        else:
            self.send_json(404, {"error": "Route inconnue"})

    # ------------------------------------------------------------------
    # POST /api/photo/{id}
    # Accepts multipart/form-data with a "photo" file field.
    # Saves the file as static/images/personnes/{GID}{ext}.
    # ------------------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            if not _rate_limiter.is_allowed(self.client_address[0]):
                self.send_json(429, {"error": "Trop de requêtes. Réessayez dans une minute."})
                return

            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Identifiant invalide"})
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_json(400, {"error": "Format attendu : multipart/form-data"})
                return

            boundary_match = re.search(r'boundary=([^\s;]+)', content_type)
            if not boundary_match:
                self.send_json(400, {"error": "Boundary multipart manquant"})
                return
            boundary = boundary_match.group(1).encode()

            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD_BYTES:
                self.send_json(413, {"error": f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES // 1024 // 1024} Mo)"})
                return
            raw_body = self.rfile.read(length)

            # Parse the multipart body manually to extract the "photo" part.
            delimiter = b"--" + boundary
            parts_raw = raw_body.split(delimiter)
            file_data = None
            file_ext  = ".jpg"  # default if no filename header is present
            for part in parts_raw:
                if b'name="photo"' not in part:
                    continue
                if b"\r\n\r\n" not in part:
                    continue
                headers_raw, file_body = part.split(b"\r\n\r\n", 1)
                # Strip the trailing CRLF and closing "--" boundary marker
                file_body = file_body.rstrip(b"\r\n")
                if file_body.endswith(b"--"):
                    file_body = file_body[:-2].rstrip(b"\r\n")
                fn_match = re.search(rb'filename="([^"]+)"', headers_raw)
                if fn_match:
                    orig_name = fn_match.group(1).decode(errors="replace")
                    ext = Path(orig_name).suffix.lower()
                    if ext in ALLOWED_EXTENSIONS:
                        file_ext = ext
                file_data = file_body
                break

            if not file_data:
                self.send_json(400, {"error": "Aucune donnée photo trouvée dans la requête"})
                return

            # Validate image file signature (magic bytes) — don't trust the extension alone.
            if not _is_valid_image(file_data):
                self.send_json(400, {"error": "Format d'image invalide. Seuls JPEG, PNG, GIF et WebP sont acceptés."})
                return

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": "Personne introuvable"})
                    return

                # Remove the previous portrait before writing the new one.
                _safe_unlink_photo(persons[gid].get("photo"))

                # Save as {GID}{ext} atomically via temp file + rename.
                dest_filename = f"{gid}{file_ext}"
                dest_path     = PHOTOS_DIR / dest_filename
                tmp_path      = dest_path.with_suffix(".tmp")
                try:
                    with open(tmp_path, "wb") as f:
                        f.write(file_data)
                    tmp_path.replace(dest_path)  # atomic rename
                except Exception:
                    tmp_path.unlink(missing_ok=True)
                    raise

                photo_url = f"/images/personnes/{dest_filename}"
                persons[gid]["photo"] = photo_url
                regen_markdown(gid, persons[gid])
                result = {"id": gid, "ok": True, "photo": photo_url}
                _log.info("POST photo/%s: %s (%d bytes) from %s", gid, dest_filename, len(file_data), self.client_address[0])
                print(f"  📷 Photo uploadée pour {gid}: {dest_filename} ({len(file_data)} bytes)")

            self.send_json(200, result)
        else:
            self.send_json(404, {"error": "Route inconnue"})

    # ------------------------------------------------------------------
    # DELETE /api/photo/{id}
    # Removes the portrait file from disk and clears the photo field.
    # ------------------------------------------------------------------

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            if not _rate_limiter.is_allowed(self.client_address[0]):
                self.send_json(429, {"error": "Trop de requêtes. Réessayez dans une minute."})
                return

            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Identifiant invalide"})
                return

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": "Personne introuvable"})
                    return

                _safe_unlink_photo(persons[gid].get("photo"))
                persons[gid]["photo"] = None
                regen_markdown(gid, persons[gid])
                _log.info("DELETE photo/%s from %s", gid, self.client_address[0])

            self.send_json(200, {"id": gid, "ok": True, "photo": None})
        else:
            self.send_json(404, {"error": "Route inconnue"})
