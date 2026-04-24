---
mode: agent
description: Importer ou re-importer les données depuis l'export HTML Gramps
---

# Importer les données depuis Gramps

## Contexte

`scripts/parse_gramps.py` lit l'export HTML produit par Gramps et (re)génère :
- `data/famille.json` — base de données principale (source de vérité)
- `content/personnes/*.md` — pages Hugo auto-générées

⚠️ **Ce script écrase tout.** Les modifications apportées via l'API locale
(`api_server.py`) ou manuellement dans `famille.json` seront perdues si elles
ne sont pas reflétées dans Gramps avant l'export.

## Prérequis

```bash
pip install beautifulsoup4 lxml   # si pas encore installé
```

## Chemins à configurer

Ouvrir `scripts/parse_gramps.py` et vérifier les constantes en haut du fichier :

| Constante | Description |
|-----------|-------------|
| `GRAMPS_DIR` | Répertoire racine de l'export HTML Gramps |
| `HUGO_DIR` | Racine du dépôt Hugo (détecté automatiquement si importé depuis `genealogie.config`) |
| `IMAGES_SRC` | Dossier contenant les photos sources à copier |
| `IMAGES_DST` | `static/images/personnes/` dans le dépôt Hugo |

Si `GRAMPS_DIR` ou `IMAGES_SRC` a changé (nouvelle exportation Gramps, déplacement
de fichiers), mettre à jour ces chemins avant de lancer le script.

## Lancer l'import

```bash
cd /home/dicko/dev/hugo/hugo_sites/genealogie
python3 scripts/parse_gramps.py
```

La sortie attendue ressemble à :

```
Parsing ppl/ ... 1523 personnes trouvées
Copie des photos ... 412 photos copiées
Écriture data/famille.json ... OK
Génération content/personnes/ ... 1523 fichiers
Terminé.
```

## Vérifier le résultat

```bash
# Vérifier que famille.json est valide
python3 -c "import json; d=json.load(open('data/famille.json')); print(f\"{d['total']} personnes\")"

# Vérifier qu'aucun fichier .md n'est manquant
ls content/personnes/ | wc -l

# Build Hugo pour détecter toute erreur de template
hugo --minify 2>&1 | grep -i "error\|warn" || echo "✅ Build OK"
```

## Après l'import

1. Inspecter quelques fiches au hasard sur `hugo server` pour s'assurer que les
   données s'affichent correctement.
2. Si des modifications manuelles avaient été faites dans `famille.json` (via
   l'API ou à la main), les réappliquer maintenant — elles ont été écrasées.
3. Faire un commit pour sauvegarder le nouvel état :
   ```bash
   git add data/famille.json content/personnes/ static/images/personnes/
   git commit -m "chore: mise à jour import Gramps $(date +%Y-%m-%d)"
   ```

## Résolution de problèmes courants

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| `FileNotFoundError: ppl/` | `GRAMPS_DIR` incorrect | Corriger le chemin dans `parse_gramps.py` |
| `ModuleNotFoundError: bs4` | BeautifulSoup non installé | `pip install beautifulsoup4 lxml` |
| Personnes sans photo alors qu'elles en ont une | Nom de fichier photo ne correspond pas | Vérifier la logique `is'Alias'`/`isName` dans `parse_gramps.py` |
| `hugo --minify` échoue après import | TOML mal formé dans un `.md` | Chercher le fichier avec `grep -r '+++' content/personnes/ -l` et inspecter |
| Nombre de personnes diminue | Export Gramps incomplet | Vérifier que l'export inclut toutes les branches (Diona, Boundoucoli, Dalla, Boni) |

## Architecture du script

```
parse_gramps.py
├── extract_gramps_id()          — extrait l'ID [Ixx] depuis le texte HTML
├── clean_name()                 — supprime le suffixe [Ixx] des noms
├── parse_person_page(html_path) — parse une fiche individuelle Gramps
│     ├── nom, genre
│     ├── naissance, décès, ville (section "Événements")
│     ├── parents (section "Parents et fratrie")
│     ├── fratrie
│     ├── familles + enfants (section "Familles")
│     └── commentaires (section "Notes")
└── main()
      ├── itère sur ppl/**/*.html
      ├── appelle parse_person_page() pour chaque fichier
      ├── copie les photos (IMAGES_SRC → IMAGES_DST)
      ├── écrit data/famille.json
      └── appelle regen_markdown() pour chaque personne
```
