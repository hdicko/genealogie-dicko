# Scraper - genealogie-dicko

Scrape le site `https://genealogie-dicko-ardo.netlify.app` pour régénérer les données et fichiers de contenu.

## Usage

```bash
python3 scripts/scrape_site.py
```

### Output

- ✅ `data/famille.json` — data source de vérité (796 personnes)
- ✅ `content/personnes/*.md` — fichiers Markdown pour Hugo (762 fichiers)

## Architecture

### Scraper Flow

```
1. Fetch /personnes/   → extract person URLs
   └─ 796 person pages found
   
2. Parse each /personnes/<id>/
   ├─ Extract: nom, genre, dates, ville, commentaires
   ├─ Extract: relations (parents, fratrie, familles)
   └─ Map local photos by Gramps ID
   
3. Build famille.json
   └─ 782 personnes avec photo detection (154 photos mappées)
   
4. Generate Markdown files
   └─ One file per person with TOML frontmatter
```

### Photo Mapping

Photos are detected locally in `static/images/personnes/`:
- Exact ID match: `I1.jpg`, `0497.jpg`
- Lowercase variants: `i1.jpg`
- Multiple formats: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`

**Result:** 154 / 782 persons (19.7%) with photo

### Data Schema

```json
{
  "gramps_id": "I1",
  "nom": "Breima (Ameri)",
  "genre": "male | female | unknown",
  "naissance": "date or empty",
  "deces": "date or empty",
  "ville": "location or empty",
  "commentaires": "notes or empty",
  "photo": "/images/personnes/I1.jpg or null",
  "parents": [
    { "nom": "...", "id": "ID", "relation": "pere | mere" }
  ],
  "fratrie": [
    { "nom": "...", "id": "ID" }
  ],
  "familles": [
    {
      "conjoint": "...",
      "conjoint_id": "ID",
      "enfants": [
        { "nom": "...", "id": "ID" }
      ]
    }
  ]
}
```

## Performance

**Current (synchronous scraping):**
- 796 person pages
- ~2-3 min execution time
- Network I/O bound

**Future optimizations:**
1. Parallel requests with `ThreadPoolExecutor` / `asyncio`
2. Incremental scraping (skip unchanged persons)
3. Response caching (JSON file with person snapshots)
4. Logging to `scraper.log`

## Idempotency

The scraper is **safe to re-run**:
- Overwrites `data/famille.json` completely
- Deletes old `.md` files and regenerates
- No side effects on photos or templates
- Handles 404 errors gracefully

## Development

### Local Testing

```bash
# Run scraper
python3 scripts/scrape_site.py

# Build Hugo
hugo server

# Check data
cat data/famille.json | jq '.personnes | keys | length'
```

### Data Validation

```bash
# Count persons
python3 -c "import json; d=json.load(open('data/famille.json')); print(len(d['personnes']))"

# Check photos
python3 -c "import json; d=json.load(open('data/famille.json')); print(sum(1 for p in d['personnes'].values() if p.get('photo')))"

# Check orphans
python3 -c "import json; d=json.load(open('data/famille.json')); print(sum(1 for p in d['personnes'].values() if not p.get('parents')))"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `requests` not found | `pip install requests beautifulsoup4` |
| Scraper slow | Network latency is normal; check internet connection |
| Missing photos | Check `static/images/personnes/` for naming mismatches |
| Hugo build fails | Run scraper again, then `hugo --minify` |

## Related Files

- `scripts/api_server.py` — Local API for editing (uses generated data)
- `genealogie/markup.py` — Markdown generation utility
- `layouts/` — Hugo templates (unchanged)
- `data/famille.json` — Master data file
- `content/personnes/` — Generated Hugo content

## Notes

- **Source of truth:** The scraper extracts live data from production site
- **Photo strategy:** Local static files are source, not embedded in HTML
- **Timezone:** Gramps export dates may have UTC conversions
- **Encoding:** All output in UTF-8 with `ensure_ascii=False`

---

**Last updated:** 2026-08-04
