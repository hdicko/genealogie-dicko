import json
import re
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
                self.send_json(400, {"error": "Invalid person ID"})
                return

            data = load_data()
            gid  = resolve_id(raw_gid, data["personnes"])
            p = data["personnes"].get(gid)
            if p is None:
                self.send_json(404, {"error": f"Person {gid} not found"})
            else:
                self.send_json(200, {"id": gid, **p})
        else:
            self.send_json(404, {"error": "Not found"})

    # ------------------------------------------------------------------
    # PATCH /api/person/{id}
    # Updates whitelisted fields only; propagates name changes to relatives.
    # ------------------------------------------------------------------

    def do_PATCH(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "person":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            length = int(self.headers.get("Content-Length", 0))
            if length > 64 * 1024:  # 64 KB is generous for a simple JSON edit form
                self.send_json(413, {"error": "Request body too large"})
                return
            body = json.loads(self.rfile.read(length))

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": f"Person {gid} not found"})
                    return

                p = persons[gid]
                old_nom = p.get("nom")

                # Only these fields may be edited via the API.
                # Structural data (parents, familles) is managed by parse_gramps.py.
                ALLOWED = ("nom", "genre", "naissance", "deces", "ville", "commentaires")
                for field in ALLOWED:
                    if field in body:
                        p[field] = body[field].strip() if isinstance(body[field], str) else body[field]

                new_nom = p.get("nom")
                if old_nom != new_nom:
                    # A rename must propagate to all denormalised name copies
                    # stored in other people's parents/conjoint/enfants lists.
                    update_references(persons, gid, old_nom, new_nom)

                regen_markdown(gid, p)
                result = {"id": gid, "ok": True, **p}
                print(f"  ✓ Updated {gid}: {old_nom!r} → {new_nom!r}")

            self.send_json(200, result)
        else:
            self.send_json(404, {"error": "Not found"})

    # ------------------------------------------------------------------
    # POST /api/photo/{id}
    # Accepts multipart/form-data with a "photo" file field.
    # Saves the file as static/images/personnes/{GID}{ext}.
    # ------------------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_json(400, {"error": "Expected multipart/form-data"})
                return

            boundary_match = re.search(r'boundary=([^\s;]+)', content_type)
            if not boundary_match:
                self.send_json(400, {"error": "Missing multipart boundary"})
                return
            boundary = boundary_match.group(1).encode()

            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD_BYTES:
                self.send_json(413, {"error": f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)"})
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
                self.send_json(400, {"error": "No photo data found in request"})
                return

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": f"Person {gid} not found"})
                    return

                # Remove the previous portrait before writing the new one.
                old_photo = persons[gid].get("photo")
                if old_photo:
                    old_path = (HUGO_DIR / "static" / old_photo.lstrip("/")).resolve()
                    photos_resolved = PHOTOS_DIR.resolve()
                    # Path-traversal guard: only delete files inside PHOTOS_DIR
                    if old_path.exists() and old_path.is_file() and str(old_path).startswith(str(photos_resolved)):
                        old_path.unlink()
                        print(f"  🗑️  Ancienne photo supprimée: {old_path.name}")

                # Save as {GID}{ext} — simple, predictable filename.
                dest_filename = f"{gid}{file_ext}"
                dest_path     = PHOTOS_DIR / dest_filename
                with open(dest_path, "wb") as f:
                    f.write(file_data)

                photo_url = f"/images/personnes/{dest_filename}"
                persons[gid]["photo"] = photo_url
                regen_markdown(gid, persons[gid])
                result = {"id": gid, "ok": True, "photo": photo_url}
                print(f"  📷 Photo uploadée pour {gid}: {dest_filename} ({len(file_data)} bytes)")

            self.send_json(200, result)
        else:
            self.send_json(404, {"error": "Not found"})

    # ------------------------------------------------------------------
    # DELETE /api/photo/{id}
    # Removes the portrait file from disk and clears the photo field.
    # ------------------------------------------------------------------

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            with DataTransaction() as data:
                persons = data["personnes"]
                gid     = resolve_id(raw_gid, persons)
                if gid not in persons:
                    self.send_json(404, {"error": f"Person {gid} not found"})
                    return

                old_photo = persons[gid].get("photo")
                if old_photo:
                    old_path = (HUGO_DIR / "static" / old_photo.lstrip("/")).resolve()
                    photos_resolved = PHOTOS_DIR.resolve()
                    # Path-traversal guard: only delete files inside PHOTOS_DIR
                    if old_path.exists() and old_path.is_file() and str(old_path).startswith(str(photos_resolved)):
                        old_path.unlink()
                        print(f"  🗑️  Photo supprimée: {old_path.name}")

                persons[gid]["photo"] = None
                regen_markdown(gid, persons[gid])

            self.send_json(200, {"id": gid, "ok": True, "photo": None})
        else:
            self.send_json(404, {"error": "Not found"})
