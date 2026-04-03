from .config import PPL_DIR


def toml_str(s):
    """Encode a Python value as a TOML string literal.

    - None          → ""
    - multi-line str → triple-quoted TOML basic string
    - single-line str → regular double-quoted string with escaping
    """
    if s is None:
        return '""'
    s = str(s)
    if '\n' in s:
        # TOML multi-line basic string — escape backslashes and any triple-quote
        # sequences that would prematurely close the literal.
        s = s.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        return '"""\n' + s + '"""'
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def regen_markdown(gid, p):
    """Rewrite the Hugo markdown file for one person from their data dict.

    The file is at content/personnes/{gid_lowercase}.md.
    It is always fully regenerated — partial updates are not supported.
    The front matter is TOML (delimited by +++).
    """
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

    # Parent entries — each becomes a [[parents]] TOML array-of-tables block
    for par in p.get("parents", []):
        lines += ["", "[[parents]]",
                  f"  nom = {toml_str(par.get('nom'))}",
                  f"  id = {toml_str(par.get('id'))}",
                  f"  relation = {toml_str(par.get('relation'))}"]  # "pere" or "mere"

    # Family entries — one [[familles]] block per spouse, with nested children
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
    """Propagate a name change to every other person that references gid.

    When a person's name changes, their name is stored denormalised in the
    parents/conjoint/enfants lists of other people. This function walks the
    entire persons dict and patches those stale copies, then regenerates the
    affected markdown files.

    Only updates entries where both the id AND the old name match, to avoid
    accidental overwrites of legitimately different people with the same name.
    """
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
