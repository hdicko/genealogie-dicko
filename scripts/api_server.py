#!/usr/bin/env python3
"""
Serveur API local pour éditer les personnes de l'arbre généalogique.
Port 1315 — modifie data/famille.json + content/personnes/*.md
Hugo server (port 1314) détecte les changements et recharge automatiquement.

Usage : python3 scripts/api_server.py
"""

import json
import re
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

HUGO_DIR    = Path(__file__).parent.parent
DATA_FILE   = HUGO_DIR / "data" / "famille.json"
PPL_DIR     = HUGO_DIR / "content" / "personnes"
PHOTOS_DIR  = HUGO_DIR / "static" / "images" / "personnes"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# Only allow requests from the local Hugo dev server
ALLOWED_ORIGINS = {
    "http://localhost:1314",
    "http://127.0.0.1:1314",
}

CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, PATCH, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB max photo size
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
GID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')  # safe GID pattern


# ── helpers ──────────────────────────────────────────────────────────────────

def load_data():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def toml_str(s):
    if s is None:
        return '""'
    s = str(s)
    if '\n' in s:
        # Use TOML multi-line basic string; escape backslashes and triple-quotes
        s = s.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        return '"""\n' + s + '"""'
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def regen_markdown(gid, p):
    """Rewrite the markdown frontmatter for one person."""
    slug = gid.lower()
    md_path = PPL_DIR / f"{slug}.md"

    lines = [
        "+++",
        f"title = {toml_str(p.get('nom') or gid)}",
        f"gramps_id = {toml_str(gid)}",
        f"genre = {toml_str(p.get('genre'))}",
        f"naissance = {toml_str(p.get('naissance'))}",
        f"deces = {toml_str(p.get('deces'))}",
        f"ville = {toml_str(p.get('ville'))}",
        f"commentaires = {toml_str(p.get('commentaires'))}",
        f"photo = {toml_str(p.get('photo'))}",
        "draft = false",
    ]
    for par in p.get("parents", []):
        lines += ["", "[[parents]]",
                  f"  nom = {toml_str(par.get('nom'))}",
                  f"  id = {toml_str(par.get('id'))}",
                  f"  relation = {toml_str(par.get('relation'))}"]
    for fam in p.get("familles", []):
        lines += ["", "[[familles]]",
                  f"  conjoint = {toml_str(fam.get('conjoint'))}",
                  f"  conjoint_id = {toml_str(fam.get('conjoint_id'))}"]
        for e in fam.get("enfants", []):
            lines += ["", "  [[familles.enfants]]",
                      f"    nom = {toml_str(e.get('nom'))}",
                      f"    id = {toml_str(e.get('id'))}"]
    lines += ["+++", "", f"## {p.get('nom') or gid}", ""]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def update_references(persons, gid, old_nom, new_nom):
    """Update the name of gid wherever it appears as parent/conjoint/enfant."""
    if old_nom == new_nom:
        return
    for pid, p in persons.items():
        changed = False
        for par in p.get("parents", []):
            if par.get("id") == gid and par.get("nom") == old_nom:
                par["nom"] = new_nom
                changed = True
        for fam in p.get("familles", []):
            if fam.get("conjoint_id") == gid and fam.get("conjoint") == old_nom:
                fam["conjoint"] = new_nom
                changed = True
            for e in fam.get("enfants", []):
                if e.get("id") == gid and e.get("nom") == old_nom:
                    e["nom"] = new_nom
                    changed = True
        if changed:
            regen_markdown(pid, p)


def resolve_id(raw_id, persons):
    """Resolve a person ID case-insensitively against the persons dict keys."""
    if raw_id in persons:
        return raw_id
    upper = raw_id.upper()
    if upper in persons:
        return upper
    lower = raw_id.lower()
    if lower in persons:
        return lower
    # fallback: case-insensitive scan
    raw_lower = raw_id.lower()
    for key in persons:
        if key.lower() == raw_lower:
            return key
    return raw_id  # not found, return as-is so caller gets 404


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _cors_origin(self):
        """Return the allowed origin for this request, or None if disallowed."""
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            return origin
        # Allow requests with no Origin header (direct curl / Hugo server-side)
        return None if origin else ""

    def _send_cors(self, include_origin=True):
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        if include_origin:
            origin = self._cors_origin()
            if origin is not None:
                self.send_header("Access-Control-Allow-Origin", origin or "*")

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self._cors_origin()
        if origin is None:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")
        # GET /api/person/{id}
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

    def do_PATCH(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")
        # PATCH /api/person/{id}
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "person":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            length = int(self.headers.get("Content-Length", 0))
            if length > 64 * 1024:  # 64 KB max for JSON body
                self.send_json(413, {"error": "Request body too large"})
                return
            body   = json.loads(self.rfile.read(length))

            data    = load_data()
            persons = data["personnes"]
            gid     = resolve_id(parts[2], persons)
            if gid not in persons:
                self.send_json(404, {"error": f"Person {gid} not found"})
                return

            p = persons[gid]
            old_nom = p.get("nom")

            # Allowed editable fields
            ALLOWED = ("nom", "genre", "naissance", "deces", "ville", "commentaires")
            for field in ALLOWED:
                if field in body:
                    p[field] = body[field].strip() if isinstance(body[field], str) else body[field]

            new_nom = p.get("nom")

            # Propagate name change to all references
            if old_nom != new_nom:
                update_references(persons, gid, old_nom, new_nom)

            # Save JSON + regen markdown for this person
            save_data(data)
            regen_markdown(gid, p)

            print(f"  ✓ Updated {gid}: {old_nom!r} → {new_nom!r}")
            self.send_json(200, {"id": gid, "ok": True, **p})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")
        # POST /api/photo/{id}
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            data    = load_data()
            persons = data["personnes"]
            gid     = resolve_id(raw_gid, persons)
            if gid not in persons:
                self.send_json(404, {"error": f"Person {gid} not found"})
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_json(400, {"error": "Expected multipart/form-data"})
                return

            # Extract boundary
            boundary_match = re.search(r'boundary=([^\s;]+)', content_type)
            if not boundary_match:
                self.send_json(400, {"error": "Missing multipart boundary"})
                return
            boundary = boundary_match.group(1).encode()

            length   = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD_BYTES:
                self.send_json(413, {"error": f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)"})
                return
            raw_body = self.rfile.read(length)

            # Split parts on boundary
            delimiter = b"--" + boundary
            parts_raw = raw_body.split(delimiter)
            file_data     = None
            file_ext      = ".jpg"
            for part in parts_raw:
                if b'name="photo"' not in part:
                    continue
                # Split headers from body
                if b"\r\n\r\n" not in part:
                    continue
                headers_raw, body = part.split(b"\r\n\r\n", 1)
                # Strip trailing \r\n--
                body = body.rstrip(b"\r\n")
                if body.endswith(b"--"):
                    body = body[:-2].rstrip(b"\r\n")
                # Extract filename for extension
                fn_match = re.search(rb'filename="([^"]+)"', headers_raw)
                if fn_match:
                    orig_name = fn_match.group(1).decode(errors="replace")
                    ext = Path(orig_name).suffix.lower()
                    if ext in ALLOWED_EXTENSIONS:
                        file_ext = ext
                file_data = body
                break

            if not file_data:
                self.send_json(400, {"error": "No photo data found in request"})
                return

            # Delete old photo file if it exists (may have different extension)
            old_photo = persons[gid].get("photo")
            if old_photo:
                old_path = (HUGO_DIR / "static" / old_photo.lstrip("/")).resolve()
                photos_resolved = PHOTOS_DIR.resolve()
                if old_path.exists() and old_path.is_file() and str(old_path).startswith(str(photos_resolved)):
                    old_path.unlink()
                    print(f"  🗑️  Ancienne photo supprimée: {old_path.name}")

            # Save new file as {GID}{ext}
            dest_filename = f"{gid}{file_ext}"
            dest_path     = PHOTOS_DIR / dest_filename
            with open(dest_path, "wb") as f:
                f.write(file_data)

            # Update JSON + markdown
            photo_url = f"/images/personnes/{dest_filename}"
            persons[gid]["photo"] = photo_url
            save_data(data)
            regen_markdown(gid, persons[gid])

            print(f"  📷 Photo uploadée pour {gid}: {dest_filename} ({len(file_data)} bytes)")
            self.send_json(200, {"id": gid, "ok": True, "photo": photo_url})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")
        # DELETE /api/photo/{id}
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "photo":
            raw_gid = parts[2]
            if not GID_RE.match(raw_gid):
                self.send_json(400, {"error": "Invalid person ID"})
                return

            data    = load_data()
            persons = data["personnes"]
            gid     = resolve_id(raw_gid, persons)
            if gid not in persons:
                self.send_json(404, {"error": f"Person {gid} not found"})
                return

            old_photo = persons[gid].get("photo")
            if old_photo:
                old_path = (HUGO_DIR / "static" / old_photo.lstrip("/")).resolve()
                photos_resolved = PHOTOS_DIR.resolve()
                if old_path.exists() and old_path.is_file() and str(old_path).startswith(str(photos_resolved)):
                    old_path.unlink()
                    print(f"  🗑️  Photo supprimée: {old_path.name}")

            persons[gid]["photo"] = None
            save_data(data)
            regen_markdown(gid, persons[gid])
            self.send_json(200, {"id": gid, "ok": True, "photo": None})
        else:
            self.send_json(404, {"error": "Not found"})


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 1315
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"🌳 API généalogie démarrée sur http://localhost:{port}")
    print(f"   PATCH http://localhost:{port}/api/person/I1  (modifier une personne)")
    print("   Ctrl+C pour arrêter\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
