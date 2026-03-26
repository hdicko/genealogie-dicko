#!/usr/bin/env python3
"""
Parse Gramps HTML export and generate:
- data/famille.json  (Hugo data file)
- content/personnes/*.md (Hugo content pages)
"""

import os
import re
import json
import shutil
from pathlib import Path
from bs4 import BeautifulSoup

GRAMPS_DIR = Path("/home/dicko/Documents/HD/Ardo Diona/Genealogie/Famille Dicko/Complet HTML")
HUGO_DIR = Path("/home/dicko/dev/hugo/hugo_sites/genealogie")
PPL_DIR = GRAMPS_DIR / "ppl"
IMAGES_SRC = Path("/home/dicko/Documents/HD/Ardo Diona/Genealogie/Famille Dicko/images")
IMAGES_DST = HUGO_DIR / "static" / "images" / "personnes"


def extract_gramps_id(text):
    """Extract GRAMPS ID like [I1] from text."""
    m = re.search(r'\[([A-Z0-9]+)\]', text)
    return m.group(1) if m else None


def clean_name(n):
    """Remove [Ixx] suffix from names."""
    return re.sub(r'\s*\[[A-Z0-9]+\]\s*$', '', n).strip() if n else n


def parse_person_page(html_path):
    """Parse a single Gramps individual HTML page and return a dict."""
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'lxml')

    person = {
        'gramps_id': None,
        'nom': None,
        'genre': None,
        'naissance': None,
        'deces': None,
        'ville': None,
        'commentaires': None,
        'photo': None,
        'parents': [],
        'fratrie': [],
        'familles': [],
        'html_file': str(html_path.relative_to(GRAMPS_DIR)),
    }

    # Name from h3
    h3 = soup.find('h3')
    if h3:
        person['nom'] = h3.get_text(strip=True)

    # Summary table
    summary = soup.find('div', id='summaryarea')
    if summary:
        for row in summary.find_all('tr'):
            field = row.find('td', class_='field')
            data = row.find('td', class_='data')
            if not field or not data:
                continue
            label = field.get_text(strip=True).lower()
            value = data.get_text(strip=True)
            if 'gramps id' in label:
                person['gramps_id'] = value
            elif 'gender' in label:
                person['genre'] = value.lower()
        img = summary.find('img')
        if img and img.get('src'):
            person['photo'] = img['src']

    # Events
    events_div = soup.find('div', id='events')
    if events_div:
        for row in events_div.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if 'birth' in label:
                    person['naissance'] = value
                elif 'death' in label:
                    person['deces'] = value

    # Parents
    parents_div = soup.find('div', id='parents')
    if parents_div:
        for row in parents_div.find_all('tr'):
            field = row.find('td', class_='field')
            data = row.find('td', class_='data')
            if not field or not data:
                continue
            label = field.get_text(strip=True).lower()
            links = data.find_all('a')
            if 'father' in label:
                for a in links:
                    gid = extract_gramps_id(a.get_text())
                    person['parents'].append({'nom': clean_name(a.get_text(strip=True)), 'id': gid, 'relation': 'pere'})
            elif 'mother' in label:
                for a in links:
                    gid = extract_gramps_id(a.get_text())
                    person['parents'].append({'nom': clean_name(a.get_text(strip=True)), 'id': gid, 'relation': 'mere'})
            elif 'sibling' in label:
                for a in links:
                    gid = extract_gramps_id(a.get_text())
                    person['fratrie'].append({'nom': clean_name(a.get_text(strip=True)), 'id': gid})

    # Families
    families_div = soup.find('div', id='families')
    if families_div:
        current_family = None
        for row in families_div.find_all('tr'):
            category = row.find('td', class_='category')
            field = row.find('td', class_='field')
            data = row.find('td', class_='data')

            if category and category.get_text(strip=True).strip():
                cat_text = category.get_text(strip=True)
                if cat_text in ('Married', 'Partner', 'Unmarried', 'Unknown', 'Civil Union'):
                    current_family = {'conjoint': None, 'conjoint_id': None, 'enfants': []}
                    person['familles'].append(current_family)

            if field and data and current_family is not None:
                label = field.get_text(strip=True).lower()
                links = data.find_all('a')
                if 'wife' in label or 'husband' in label or 'spouse' in label:
                    if links:
                        a = links[0]
                        gid = extract_gramps_id(a.get_text())
                        current_family['conjoint'] = clean_name(a.get_text(strip=True))
                        current_family['conjoint_id'] = gid
                elif 'children' in label or 'child' in label:
                    for a in links:
                        gid = extract_gramps_id(a.get_text())
                        current_family['enfants'].append({'nom': clean_name(a.get_text(strip=True)), 'id': gid})

    # Clean nom
    person['nom'] = clean_name(person['nom'])

    return person


def match_photos(persons):
    """Try to match portrait images to persons."""
    photo_map = {}
    if not IMAGES_SRC.exists():
        return photo_map

    for img_file in IMAGES_SRC.iterdir():
        if img_file.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.gif'):
            continue
        stem = img_file.stem
        # Pattern: "is'Alias' Full Name" or "isFullName"
        # Remove leading "is"
        if stem.startswith('is'):
            stem = stem[2:]
        # Remove alias in single quotes: 'Alias'
        stem_clean = re.sub(r"'[^']*'\s*", '', stem).strip()
        stem_clean_lower = stem_clean.lower()

        for gid, person in persons.items():
            if person['nom']:
                nom_lower = person['nom'].lower()
                if stem_clean_lower == nom_lower or stem_clean_lower in nom_lower or nom_lower in stem_clean_lower:
                    photo_map[gid] = img_file.name
                    break

    return photo_map


def toml_str(s):
    if s is None:
        return '""'
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def main():
    print("=== Parsing Gramps HTML export ===")

    html_files = sorted(PPL_DIR.rglob("*.html"))
    print(f"Found {len(html_files)} individual pages")

    persons = {}
    for i, html_path in enumerate(html_files):
        try:
            p = parse_person_page(html_path)
            if p['gramps_id']:
                persons[p['gramps_id']] = p
            else:
                persons[f"UNK{i}"] = p
        except Exception as e:
            print(f"  ERROR {html_path.name}: {e}")

    print(f"Parsed {len(persons)} persons")

    # Copy images
    print("\n=== Copying images ===")
    IMAGES_DST.mkdir(parents=True, exist_ok=True)
    if IMAGES_SRC.exists():
        copied = 0
        for img_file in IMAGES_SRC.iterdir():
            if img_file.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif'):
                shutil.copy2(img_file, IMAGES_DST / img_file.name)
                copied += 1
        print(f"Copied {copied} images")

    # Match photos
    photo_map = match_photos(persons)
    print(f"Matched {len(photo_map)} photos to persons")
    for gid, fname in photo_map.items():
        persons[gid]['photo'] = f"/images/personnes/{fname}"

    # Write data/famille.json
    print("\n=== Writing data/famille.json ===")
    data_dir = HUGO_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    with open(data_dir / "famille.json", 'w', encoding='utf-8') as f:
        json.dump({'personnes': persons, 'total': len(persons)}, f, ensure_ascii=False, indent=2)
    print(f"Written {len(persons)} persons to data/famille.json")

    # Generate Hugo content pages
    print("\n=== Generating Hugo content pages ===")
    content_dir = HUGO_DIR / "content" / "personnes"
    content_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for gid, p in persons.items():
        slug = gid.lower()
        md_path = content_dir / f"{slug}.md"

        lines = [
            '+++',
            f'title = {toml_str(p["nom"] or gid)}',
            f'gramps_id = {toml_str(gid)}',
            f'genre = {toml_str(p["genre"])}',
            f'naissance = {toml_str(p["naissance"])}',
            f'deces = {toml_str(p["deces"])}',
            f'ville = {toml_str(p.get("ville"))}',
            f'commentaires = {toml_str(p.get("commentaires"))}',
            f'photo = {toml_str(p["photo"])}',
            'draft = false',
        ]

        for par in p['parents']:
            lines += ['', '[[parents]]',
                      f'  nom = {toml_str(par["nom"])}',
                      f'  id = {toml_str(par["id"])}',
                      f'  relation = {toml_str(par["relation"])}']

        for fam in p['familles']:
            lines += ['', '[[familles]]',
                      f'  conjoint = {toml_str(fam["conjoint"])}',
                      f'  conjoint_id = {toml_str(fam["conjoint_id"])}']
            for e in fam['enfants']:
                lines += ['', '  [[familles.enfants]]',
                          f'    nom = {toml_str(e["nom"])}',
                          f'    id = {toml_str(e["id"])}']

        lines += ['+++', '', f'## {p["nom"] or gid}', '']

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        generated += 1

    # Index pages
    with open(HUGO_DIR / "content" / "_index.md", 'w', encoding='utf-8') as f:
        f.write('+++\ntitle = "Famille Dicko — Généalogie"\ndraft = false\n+++\n')

    with open(content_dir / "_index.md", 'w', encoding='utf-8') as f:
        f.write('+++\ntitle = "Personnes"\ndraft = false\n+++\n')

    print(f"Generated {generated} content pages")
    print("\n=== Done ===")


if __name__ == '__main__':
    main()
