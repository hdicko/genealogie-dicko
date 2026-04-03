# GitHub Copilot Instructions — Arbre Généalogique Dicko Ardo Hayre

## Project Overview

This is a custom-built Hugo static genealogy website for the Dicko Ardo Hayre family (branches: Diona, Boundoucoli, Dalla, Boni). It features an interactive D3.js family tree, ~1,500 person profiles generated from Gramps genealogy software, and a local Python API for editing data.

**Technology stack:**
- **Hugo 0.159.0+** — static site generator (version is critical, do not downgrade)
- **Python 3** — Gramps data parser (`scripts/parse_gramps.py`) and local editing API (`scripts/api_server.py`)
- **D3.js** (CDN) — interactive tree visualization
- **Plain CSS** — no Sass, no build pipeline
- **Netlify** — deployment platform
- **Gramps** — external genealogy software used as data source

**Language:** French (`fr-FR`). All UI text, comments, and variable names related to genealogical domain should be in French.

---

## Architecture & Data Flow

```
Gramps HTML export
      │
      ▼
scripts/parse_gramps.py
      │
      ├──► data/famille.json          (master data, source of truth)
      └──► content/personnes/*.md    (Hugo content pages, auto-generated)
                │
                ▼
           hugo --minify
                │
                ▼
            public/                  (deployed to Netlify)
```

**Editing flow (local development only):**
- `hugo server` runs on port 1313
- `python3 scripts/api_server.py` runs on port 1315
- Templates call `http://127.0.0.1:1315/api/person/{ID}` (PATCH) and `/api/photo/{ID}` (POST/DELETE)
- The API updates `data/famille.json` and regenerates the corresponding `.md` file

**Important:** `content/personnes/*.md` files are auto-generated. The canonical source of truth for person data is `data/famille.json`. Do not manually edit person markdown files — use the API or `parse_gramps.py`.

---

## Hugo Conventions

### Version requirement
Hugo `0.159.0` or later is **mandatory** — it introduced `hugo.Data` support used throughout templates. Never change the version in `netlify.toml` to below `0.159.0`.

### Data access pattern
```go-html-template
{{ $person := index hugo.Data.famille.personnes .Params.gramps_id }}
{{ range hugo.Data.famille.personnes }}
```

### Template structure
```
layouts/
├── _default/
│   ├── baseof.html     # Base template: nav (Accueil / Arbre / Personnes), footer with person count
│   ├── list.html
│   └── taxonomy.html
├── index.html          # Homepage with search widget
├── personnes/
│   ├── list.html       # Person list with filtering
│   └── single.html     # Person detail card + edit modal (287 lines)
└── arbre/
    └── list.html       # Full D3.js tree (831 lines, inline CSS+JS)
```

There are **no partials**. All markup is inlined directly in layout files. If adding reusable components, create files under `layouts/partials/` and include them with `{{ partial "name.html" . }}`.

### Front matter format
All content uses **TOML** front matter (not YAML). Person pages follow this schema:
```toml
+++
title = "Prénom Nom"
gramps_id = "I1"
genre = "male"        # "male", "female", or "unknown"
naissance = ""
deces = ""
ville = ""
commentaires = ""
photo = "/images/personnes/filename.jpg"  # or ""
draft = false

[[parents]]
  nom = "Prénom Nom"
  id = "I2"
  relation = "pere"   # "pere" or "mere"

[[familles]]
  conjoint = "Prénom Nom"
  conjoint_id = "I3"
  [[familles.enfants]]
    nom = "Prénom Nom"
    id = "I4"
+++
```

### URL slugs
Person IDs are lowercased for URLs: `gramps_id = "I1"` → `/personnes/i1/`. Use `{{ lower .Params.gramps_id }}` when building links.

---

## Python API (scripts/)

### api_server.py
Runs on `http://127.0.0.1:1315`. Endpoints:
- `PATCH /api/person/{ID}` — update person fields in `data/famille.json` and regenerate `.md`
- `POST /api/photo/{ID}` — upload photo to `static/images/personnes/`
- `DELETE /api/photo/{ID}` — remove photo
- `OPTIONS /api/*` — CORS preflight

### genealogie/ package
- `handlers.py` — HTTP handlers, CORS validation (whitelist: `localhost:1314`, `127.0.0.1:1314`)
- `data.py` — thread-safe JSON read/write via `DataTransaction` context manager
- `markup.py` — TOML markdown regeneration (`regen_markdown(gid, person)`)
- `config.py` — shared constants

### Python conventions
- Use Python 3 type hints where possible
- Follow existing pattern: `DataTransaction` for all JSON mutations (atomic read-modify-write)
- Validate uploaded files: max 10 MB, extensions `.jpg .jpeg .png .gif .webp` only
- ID validation regex: `^[A-Za-z0-9_-]{1,40}$`
- Case-insensitive ID resolution (check uppercase, then lowercase, then iterate)
- Keep comments in French matching the domain language

### parse_gramps.py
- Source data: Gramps HTML export at the path defined by `GRAMPS_DIR`
- Outputs to `HUGO_DIR/data/famille.json` and `HUGO_DIR/content/personnes/`
- Photo matching uses smart regex prefix parsing (`is'Alias'` and `isName` patterns)
- Running this script regenerates ALL person content — changes in `data/famille.json` made via API will be overwritten if this script is re-run

---

## data/famille.json Schema

```json
{
  "personnes": {
    "I1": {
      "gramps_id": "I1",
      "nom": "Prénom Nom",
      "genre": "male | female | unknown",
      "naissance": "date string or empty",
      "deces": "date string or empty",
      "ville": "location or empty",
      "commentaires": "notes or empty",
      "photo": "/images/personnes/file.jpg or null",
      "parents": [{ "nom": "...", "id": "ID", "relation": "pere | mere" }],
      "fratrie": [{ "nom": "...", "id": "ID" }],
      "familles": [{
        "conjoint": "Prénom Nom",
        "conjoint_id": "ID",
        "enfants": [{ "nom": "...", "id": "ID" }]
      }],
      "html_file": "relative/path/in/gramps/export.html"
    }
  },
  "total": 1500
}
```

---

## CSS & Frontend

- All styles are in `static/css/style.css` — plain CSS, no preprocessors
- Use CSS custom properties defined at `:root`:
  - `--primary: #3b5998` (blue)
  - `--accent: #e87bae` (pink, for female)
  - `--bg: #f7f8fc`
- D3.js tree node colors: male `#4a90d9`, female `#e87bae`, unknown `#888`
- All JavaScript is **inline** in HTML templates — no separate `.js` files
- The `static/js/` and `assets/` directories are empty — do not introduce a JS build pipeline unless discussed

---

## Security Rules

The following security measures must be preserved in all changes:

1. **CSP header** in `netlify.toml` allows `https://d3js.org` for D3.js scripts. If adding other CDN dependencies, update the CSP accordingly.
2. **CORS** in `handlers.py` allows only `localhost:1314` and `127.0.0.1:1314` — never widen this to `*`.
3. **Path traversal** prevention in photo upload — never use unsanitized user input in file paths.
4. **File upload limits**: 10 MB max, extension whitelist only.
5. **No authentication** on the local API — the API must never be exposed to the public internet.

---

## Development Workflow

```bash
# Import/refresh data from Gramps export
python3 scripts/parse_gramps.py

# Local development (two terminals)
hugo server                          # http://localhost:1313
python3 scripts/api_server.py        # http://localhost:1315 (editing API)

# Production build
hugo --minify
```

Netlify deploys automatically on push to the main branch using `hugo --minify` (see `netlify.toml`).

---

## Content & Domain Notes

- The root ancestor is `I1` (configured in `hugo.toml` as `params.rootPerson`)
- Person IDs come from Gramps (e.g., `I1`, `I351`, `0497`) — do not rename or reassign them
- Photos are stored in `static/images/personnes/` and referenced as `/images/personnes/filename.jpg`
- Photo fallback emojis by gender: male → 👴, female → 👵, unknown → 👤
- All genealogical terms should remain in French: `père`, `mère`, `enfant`, `conjoint`, `fratrie`, `naissance`, `décès`
