#!/usr/bin/env python3
"""
Scrape genealogie-dicko-ardo.netlify.app and regenerate data/famille.json
and all person markdown files.

Optimizations:
- Photo detection par Gramps ID
- Error handling gracieux
- Progress indicators
- Idempotent (safe to re-run)
"""

import os
import json
import re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Configuration
SITE_URL = "https://genealogie-dicko-ardo.netlify.app"
PERSONNES_LIST_URL = urljoin(SITE_URL, "/personnes/")
HUGO_DIR = Path(__file__).parent.parent
DATA_FILE = HUGO_DIR / "data" / "famille.json"
CONTENT_DIR = HUGO_DIR / "content" / "personnes"

# Genre mapping
GENRE_MAP = {
    "Homme": "male",
    "Femme": "female",
    "Inconnu": "unknown",
}

def get_person_links():
    """Fetch list of person URLs from personnes/ page."""
    print(f"Fetching person list from {PERSONNES_LIST_URL}...")
    response = requests.get(PERSONNES_LIST_URL, timeout=10)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    links = []
    
    for a in soup.find_all('a', href=re.compile(r'^/personnes/[^/]+/$')):
        href = a.get('href')
        if href:
            links.append(urljoin(SITE_URL, href))
    
    return links

def extract_gramps_id(url):
    """Extract Gramps ID from URL like /personnes/i1/ -> I1"""
    match = re.search(r'/personnes/([^/]+)/', url)
    if match:
        return match.group(1).upper()
    return None

def find_person_photo(gramps_id):
    """Find photo file for person by Gramps ID.
    
    Checks in order:
    1. Exact ID match: I1.jpg, 0497.jpg
    2. Lowercase ID: i1.jpg
    
    Returns path like /images/personnes/I1.jpg or None
    """
    photo_dir = HUGO_DIR / "static" / "images" / "personnes"
    
    # Try exact ID
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        for name in [gramps_id, gramps_id.lower()]:
            photo_file = photo_dir / f"{name}{ext}"
            if photo_file.exists():
                return f"/images/personnes/{photo_file.name}"
    
    return None

def parse_person_page(url):
    """Parse a single person page and extract data."""
    gramps_id = extract_gramps_id(url)
    if not gramps_id:
        return None
    
    print(f"  Scraping {gramps_id}...", end="", flush=True)
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f" ERROR: {e}")
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    person_data = {
        "gramps_id": gramps_id,
        "nom": "",
        "genre": "unknown",
        "naissance": "",
        "deces": "",
        "ville": "",
        "commentaires": "",
        "photo": None,
        "parents": [],
        "fratrie": [],
        "familles": [],
        "html_file": ""
    }
    
    # Extract nom from h1
    h1 = soup.find('h1', id='person-title')
    if h1:
        person_data["nom"] = h1.get_text(strip=True)
    
    # Extract details from dl (ID Gramps, Genre, Époux)
    dl = soup.find('dl', class_='person-details')
    if dl:
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True).lower()
            if label == "genre":
                text = dd.get_text(strip=True)
                person_data["genre"] = GENRE_MAP.get(text, "unknown")
    
    # Extract parents
    for section in soup.find_all('section', class_='person-section'):
        h2 = section.find('h2')
        if not h2:
            continue
        
        title = h2.get_text(strip=True).lower()
        
        # Parents section
        if "parent" in title:
            for li in section.find_all('li'):
                badge = li.find('span', class_='relation-badge')
                a = li.find('a')
                if badge and a:
                    relation_text = badge.get_text(strip=True).lower()
                    nom = a.get_text(strip=True)
                    pid = extract_gramps_id(a.get('href', ''))
                    if pid:
                        person_data["parents"].append({
                            "nom": nom,
                            "id": pid,
                            "relation": "pere" if "père" in relation_text else "mere"
                        })
        
        # Fratrie section
        if "frère" in title or "sœur" in title or "siblings" in title:
            for li in section.find_all('li'):
                a = li.find('a')
                if a:
                    nom = a.get_text(strip=True)
                    pid = extract_gramps_id(a.get('href', ''))
                    if pid:
                        person_data["fratrie"].append({
                            "nom": nom,
                            "id": pid
                        })
        
        # Familles section
        if "famille" in title:
            for family_block in section.find_all('div', class_='family-block'):
                conjoint_p = family_block.find('p', class_='conjoint')
                if conjoint_p:
                    a = conjoint_p.find('a')
                    if a:
                        conjoint_nom = a.get_text(strip=True)
                        conjoint_id = extract_gramps_id(a.get('href', ''))
                        
                        famille = {
                            "conjoint": conjoint_nom,
                            "conjoint_id": conjoint_id if conjoint_id else "",
                            "enfants": []
                        }
                        
                        children_list = family_block.find('ul', class_='person-list--children')
                        if children_list:
                            for li in children_list.find_all('li'):
                                a = li.find('a')
                                if a:
                                    enfant_nom = a.get_text(strip=True)
                                    enfant_id = extract_gramps_id(a.get('href', ''))
                                    if enfant_id:
                                        famille["enfants"].append({
                                            "nom": enfant_nom,
                                            "id": enfant_id
                                        })
                        
                        person_data["familles"].append(famille)
    
    # Extract photo if present (check local files first)
    photo_path = find_person_photo(gramps_id)
    if photo_path:
        person_data["photo"] = photo_path
    
    print(" ✓")
    return person_data

def main():
    print("\n=== Scraping genealogie-dicko-ardo.netlify.app ===\n")
    
    # Get all person links
    person_links = get_person_links()
    print(f"Found {len(person_links)} persons.\n")
    
    if not person_links:
        print("ERROR: No person links found!")
        return
    
    # Parse all persons
    personnes = {}
    print("Parsing person pages:")
    for url in sorted(person_links):
        person = parse_person_page(url)
        if person:
            personnes[person["gramps_id"]] = person
    
    print(f"\nSuccessfully parsed {len(personnes)} persons.\n")
    
    # Create famille.json
    famille_data = {
        "personnes": personnes,
        "total": len(personnes)
    }
    
    # Write famille.json
    print(f"Writing {DATA_FILE}...")
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(famille_data, f, ensure_ascii=False, indent=2)
    print(f"✓ {DATA_FILE} created with {len(personnes)} persons.\n")
    
    # Regenerate markdown files
    print(f"Regenerating markdown files in {CONTENT_DIR}...")
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Remove old files
    deletion_errors = []
    for md_file in CONTENT_DIR.glob('*.md'):
        try:
            md_file.unlink()
            print(f"  Removed {md_file.name}")
        except Exception as e:
            deletion_errors.append((md_file.name, str(e)))
            print(f"  ERROR removing {md_file.name}: {e}")
    
    if deletion_errors:
        print(f"\n⚠️  Warning: {len(deletion_errors)} files could not be deleted")
    
    # Generate new files
    from genealogie.markup import regen_markdown
    
    for gid, person in personnes.items():
        try:
            regen_markdown(gid, person)
            print(f"  Generated {gid.lower()}.md")
        except Exception as e:
            print(f"  ERROR generating {gid}: {e}")
    
    print(f"\n✅ Generated {len(personnes)} markdown files.")
    
    # Summary stats
    photos_with = sum(1 for p in personnes.values() if p.get("photo"))
    print(f"✅ Photos mapped: {photos_with}/{len(personnes)} ({100*photos_with/len(personnes):.1f}%)")
    
    # Validate data integrity
    orphans = sum(1 for p in personnes.values() if not p.get("parents"))
    print(f"✅ Data validation: {orphans} orphans (no parents)")
    
    print("\n=== Done! ===\n")

if __name__ == '__main__':
    main()
