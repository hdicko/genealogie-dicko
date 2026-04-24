#!/usr/bin/env python3
"""
Tests unitaires pour le package genealogie et les utilitaires parse_gramps.

Exécuter depuis la racine du dépôt :
    python3 scripts/tests/test_genealogie.py
ou :
    python3 -m pytest scripts/tests/test_genealogie.py -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ajouter scripts/ au PYTHONPATH pour pouvoir importer le package genealogie
# et les fonctions de parse_gramps
sys.path.insert(0, str(Path(__file__).parent.parent))

from genealogie.markup import (
    _escape_front_matter_delimiters,
    toml_str,
    regen_markdown,
    update_references,
)
from genealogie.handlers import _is_valid_image, _cors_origin, resolve_id, _RateLimiter
from parse_gramps import extract_gramps_id, clean_name, match_photos


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------

def _make_person(**overrides):
    """Retourne un dict personne minimal avec des valeurs par défaut."""
    base = {
        "gramps_id": "T001",
        "nom": "Test Person",
        "genre": "male",
        "naissance": "1970",
        "deces": "",
        "ville": "Paris",
        "commentaires": "",
        "photo": None,
        "parents": [],
        "fratrie": [],
        "familles": [],
    }
    base.update(overrides)
    return base


def _patch_ppl_dir(ppl_dir):
    """Redirige PPL_DIR vers un répertoire temporaire pour les tests de fichiers."""
    import genealogie.markup as m
    import genealogie.config as c
    m.PPL_DIR = ppl_dir
    c.PPL_DIR = ppl_dir


# ---------------------------------------------------------------------------
# markup.py — _escape_front_matter_delimiters
# ---------------------------------------------------------------------------

class TestEscapeFrontMatterDelimiters(unittest.TestCase):

    def test_plain_text_unchanged(self):
        self.assertEqual(_escape_front_matter_delimiters("bonjour"), "bonjour")

    def test_plus_plus_plus_line_escaped(self):
        result = _escape_front_matter_delimiters("avant\n+++\naprès")
        self.assertNotIn("+++", result)
        self.assertIn("\\u002b\\u002b\\u002b", result)

    def test_partial_plus_unchanged(self):
        """++ ou ++++ ne doivent pas être touchés, seulement exactement +++."""
        result = _escape_front_matter_delimiters("++\n++++\n+++")
        self.assertIn("++\n++++\n", result)      # ++ et ++++ inchangés
        self.assertNotIn("\n+++\n", result)       # seule la ligne +++ est remplacée

    def test_multiline_no_plus_plus_plus(self):
        text = "ligne 1\nligne 2\nligne 3"
        self.assertEqual(_escape_front_matter_delimiters(text), text)


# ---------------------------------------------------------------------------
# markup.py — toml_str
# ---------------------------------------------------------------------------

class TestTomlStr(unittest.TestCase):

    def test_none_returns_empty_string(self):
        self.assertEqual(toml_str(None), '""')

    def test_empty_string(self):
        self.assertEqual(toml_str(""), '""')

    def test_simple_string(self):
        self.assertEqual(toml_str("bonjour"), '"bonjour"')

    def test_double_quotes_escaped(self):
        result = toml_str('il dit "bonjour"')
        self.assertIn('\\"bonjour\\"', result)

    def test_backslash_escaped_single_line(self):
        result = toml_str("C:\\Users\\dicko")
        self.assertEqual(result, '"C:\\\\Users\\\\dicko"')

    def test_multiline_uses_triple_quotes(self):
        result = toml_str("ligne 1\nligne 2")
        self.assertTrue(result.startswith('"""'))

    def test_multiline_plus_plus_plus_protected(self):
        """Un +++ dans une valeur multiline ne doit pas fermer le front matter TOML.

        Le fichier doit contenir \\\\u002b (backslash doublé + u002b) de façon
        que TOML lise \\u002b (texte littéral), et non + (décodage Unicode).
        """
        import re
        result = toml_str("avant\n+++\naprès")
        # Doit contenir le backslash doublé qui protège la séquence unicode
        self.assertIn("\\\\u002b", result)
        # Ne doit PAS contenir \u002b nu (non précédé d'un backslash supplémentaire)
        bare = re.findall(r'(?<!\\)\\u002b', result)
        self.assertEqual(bare, [],
                         "\\u002b nu détecté — TOML le décodera en '+', protection brisée")

    def test_multiline_backslash_preserved(self):
        result = toml_str("C:\\chemin\nseconde ligne")
        self.assertIn("\\\\chemin", result)

    def test_non_string_converted(self):
        self.assertEqual(toml_str(42), '"42"')


# ---------------------------------------------------------------------------
# markup.py — regen_markdown
# ---------------------------------------------------------------------------

class TestRegenMarkdown(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        _patch_ppl_dir(Path(self.tmpdir.name))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _read(self, gid):
        return (Path(self.tmpdir.name) / f"{gid.lower()}.md").read_text(encoding="utf-8")

    def test_file_created_with_correct_slug(self):
        regen_markdown("T001", _make_person())
        self.assertTrue((Path(self.tmpdir.name) / "t001.md").exists())

    def test_basic_fields_present(self):
        p = _make_person(nom="Amadou Dicko", genre="male", naissance="1920", ville="Diona")
        regen_markdown("T001", p)
        content = self._read("T001")
        self.assertIn('title = "Amadou Dicko"', content)
        self.assertIn('genre = "male"', content)
        self.assertIn('naissance = "1920"', content)
        self.assertIn('ville = "Diona"', content)

    def test_fratrie_section_present(self):
        """Régression : regen_markdown doit écrire [[fratrie]] dans le front matter."""
        p = _make_person(fratrie=[{"nom": "Seyma", "id": "T002"}])
        regen_markdown("T001", p)
        content = self._read("T001")
        self.assertIn("[[fratrie]]", content)
        self.assertIn('"Seyma"', content)
        self.assertIn('"T002"', content)

    def test_parents_section_present(self):
        p = _make_person(parents=[{"nom": "Père Test", "id": "T010", "relation": "pere"}])
        regen_markdown("T001", p)
        content = self._read("T001")
        self.assertIn("[[parents]]", content)
        self.assertIn('relation = "pere"', content)

    def test_familles_with_enfants(self):
        p = _make_person(familles=[{
            "conjoint": "Oumou",
            "conjoint_id": "T020",
            "enfants": [{"nom": "Fata", "id": "T021"}],
        }])
        regen_markdown("T001", p)
        content = self._read("T001")
        self.assertIn("[[familles]]", content)
        self.assertIn("[[familles.enfants]]", content)
        self.assertIn('"Fata"', content)

    def test_toml_delimiters_present(self):
        regen_markdown("T001", _make_person())
        content = self._read("T001")
        self.assertTrue(content.startswith("+++\n"))
        lines = content.split("\n")
        closing = [i for i, l in enumerate(lines) if l == "+++" and i > 0]
        self.assertTrue(len(closing) >= 1, "Pas de +++ de fermeture trouvé")

    def test_overwrite_existing_file(self):
        """regen_markdown doit toujours réécrire complètement le fichier."""
        regen_markdown("T001", _make_person(nom="Ancien Nom"))
        regen_markdown("T001", _make_person(nom="Nouveau Nom"))
        content = self._read("T001")
        self.assertIn("Nouveau Nom", content)
        self.assertNotIn("Ancien Nom", content)


# ---------------------------------------------------------------------------
# markup.py — update_references
# ---------------------------------------------------------------------------

class TestUpdateReferences(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        _patch_ppl_dir(Path(self.tmpdir.name))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_name_propagated_to_parent_entry(self):
        persons = {
            "I1": _make_person(gramps_id="I1", nom="Père Original"),
            "I2": _make_person(
                gramps_id="I2", nom="Fils",
                parents=[{"nom": "Père Original", "id": "I1", "relation": "pere"}],
            ),
        }
        for gid, p in persons.items():
            regen_markdown(gid, p)
        update_references(persons, "I1", "Père Original", "Père Renommé")
        self.assertEqual(persons["I2"]["parents"][0]["nom"], "Père Renommé")

    def test_no_change_if_names_equal(self):
        """update_references ne doit rien faire si old_nom == new_nom."""
        persons = {
            "I1": _make_person(gramps_id="I1", nom="Même Nom"),
            "I2": _make_person(
                gramps_id="I2", nom="Autre",
                parents=[{"nom": "Même Nom", "id": "I1", "relation": "pere"}],
            ),
        }
        for gid, p in persons.items():
            regen_markdown(gid, p)
        update_references(persons, "I1", "Même Nom", "Même Nom")
        self.assertEqual(persons["I2"]["parents"][0]["nom"], "Même Nom")

    def test_only_matching_id_updated(self):
        """Ne pas toucher une entrée qui porte le même ancien nom mais un ID différent."""
        persons = {
            "I1":  _make_person(gramps_id="I1",  nom="Dupont"),
            "I99": _make_person(gramps_id="I99", nom="Autre Dupont"),
            "I2":  _make_person(
                gramps_id="I2", nom="Enfant",
                parents=[
                    {"nom": "Dupont", "id": "I1",  "relation": "pere"},
                    {"nom": "Dupont", "id": "I99", "relation": "mere"},
                ],
            ),
        }
        for gid, p in persons.items():
            regen_markdown(gid, p)
        update_references(persons, "I1", "Dupont", "Dupont Renommé")
        parents = persons["I2"]["parents"]
        self.assertEqual(parents[0]["nom"], "Dupont Renommé")  # I1 → renommé
        self.assertEqual(parents[1]["nom"], "Dupont")          # I99 → inchangé


# ---------------------------------------------------------------------------
# handlers.py — _is_valid_image
# ---------------------------------------------------------------------------

class TestIsValidImage(unittest.TestCase):

    def test_jpeg_magic(self):
        self.assertTrue(_is_valid_image(b"\xff\xd8\xff" + b"\x00" * 10))

    def test_png_magic(self):
        self.assertTrue(_is_valid_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10))

    def test_gif87a(self):
        self.assertTrue(_is_valid_image(b"GIF87a" + b"\x00" * 10))

    def test_gif89a(self):
        self.assertTrue(_is_valid_image(b"GIF89a" + b"\x00" * 10))

    def test_webp(self):
        data = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 10
        self.assertTrue(_is_valid_image(data))

    def test_invalid_returns_false(self):
        self.assertFalse(_is_valid_image(b"\x00\x01\x02\x03"))

    def test_empty_returns_false(self):
        self.assertFalse(_is_valid_image(b""))

    def test_text_file_rejected(self):
        self.assertFalse(_is_valid_image(b"This is a text file, not an image"))


# ---------------------------------------------------------------------------
# handlers.py — _cors_origin
# ---------------------------------------------------------------------------

class TestCorsOrigin(unittest.TestCase):

    def _h(self, origin):
        return {"Origin": origin}

    def test_allowed_localhost_1313(self):
        self.assertEqual(_cors_origin(self._h("http://localhost:1313")), "http://localhost:1313")

    def test_allowed_127_1313(self):
        self.assertEqual(_cors_origin(self._h("http://127.0.0.1:1313")), "http://127.0.0.1:1313")

    def test_allowed_localhost_1314(self):
        self.assertEqual(_cors_origin(self._h("http://localhost:1314")), "http://localhost:1314")

    def test_disallowed_origin_returns_none(self):
        self.assertIsNone(_cors_origin(self._h("https://evil.com")))

    def test_no_origin_returns_none(self):
        self.assertIsNone(_cors_origin({}))

    def test_wildcard_rejected(self):
        self.assertIsNone(_cors_origin(self._h("*")))


# ---------------------------------------------------------------------------
# handlers.py — resolve_id
# ---------------------------------------------------------------------------

class TestResolveId(unittest.TestCase):

    def setUp(self):
        self.persons = {"I1": {}, "I351": {}, "ABC": {}}

    def test_exact_match(self):
        self.assertEqual(resolve_id("I1", self.persons), "I1")

    def test_uppercase_fallback(self):
        self.assertEqual(resolve_id("i1", self.persons), "I1")

    def test_lowercase_fallback(self):
        self.assertEqual(resolve_id("I351", {"i351": {}}), "i351")

    def test_case_insensitive_scan(self):
        self.assertEqual(resolve_id("ABC", {"aBc": {}}), "aBc")

    def test_not_found_returns_raw(self):
        self.assertEqual(resolve_id("ZZZZ", self.persons), "ZZZZ")


# ---------------------------------------------------------------------------
# handlers.py — _RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter(unittest.TestCase):

    def test_requests_within_limit_allowed(self):
        rl = _RateLimiter(max_requests=5, window=60)
        for _ in range(5):
            self.assertTrue(rl.is_allowed("127.0.0.1"))

    def test_request_beyond_limit_blocked(self):
        rl = _RateLimiter(max_requests=3, window=60)
        for _ in range(3):
            rl.is_allowed("127.0.0.1")
        self.assertFalse(rl.is_allowed("127.0.0.1"))

    def test_different_ips_are_independent(self):
        rl = _RateLimiter(max_requests=1, window=60)
        rl.is_allowed("1.1.1.1")
        self.assertFalse(rl.is_allowed("1.1.1.1"))  # bloqué
        self.assertTrue(rl.is_allowed("2.2.2.2"))   # autre IP → ok


# ---------------------------------------------------------------------------
# parse_gramps.py — extract_gramps_id
# ---------------------------------------------------------------------------

class TestExtractGrampsId(unittest.TestCase):

    def test_simple_id(self):
        self.assertEqual(extract_gramps_id("Breima (Ameri) [I1]"), "I1")

    def test_three_digit_id(self):
        self.assertEqual(extract_gramps_id("Oumou [I351]"), "I351")

    def test_no_id_returns_none(self):
        self.assertIsNone(extract_gramps_id("Pas d'identifiant ici"))

    def test_numeric_only_id(self):
        self.assertEqual(extract_gramps_id("Personne [0497]"), "0497")

    def test_empty_string(self):
        self.assertIsNone(extract_gramps_id(""))


# ---------------------------------------------------------------------------
# parse_gramps.py — clean_name
# ---------------------------------------------------------------------------

class TestCleanName(unittest.TestCase):

    def test_removes_id_suffix(self):
        self.assertEqual(clean_name("Breima (Ameri) [I1]"), "Breima (Ameri)")

    def test_no_suffix_unchanged(self):
        self.assertEqual(clean_name("Oumou"), "Oumou")

    def test_none_returns_none(self):
        self.assertIsNone(clean_name(None))

    def test_strips_whitespace(self):
        self.assertEqual(clean_name("  Fata  [I9]  "), "Fata")

    def test_numeric_id_removed(self):
        self.assertEqual(clean_name("Personne [0497]"), "Personne")


# ---------------------------------------------------------------------------
# parse_gramps.py — match_photos
# ---------------------------------------------------------------------------

class TestMatchPhotos(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.img_src = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_img(self, name):
        (self.img_src / name).write_bytes(b"\xff\xd8\xff")  # stub JPEG

    def _run(self, persons):
        import parse_gramps
        orig = parse_gramps.IMAGES_SRC
        parse_gramps.IMAGES_SRC = self.img_src
        try:
            return match_photos(persons)
        finally:
            parse_gramps.IMAGES_SRC = orig

    def test_exact_name_match(self):
        self._write_img("isAmadouDicko.jpg")
        result = self._run({"I1": {"nom": "AmadouDicko", "photo": None}})
        self.assertIn("I1", result)
        self.assertEqual(result["I1"], "isAmadouDicko.jpg")

    def test_alias_prefix_stripped(self):
        """Fichier "is'Alias' Prénom Nom.jpg" → correspond à "Prénom Nom"."""
        self._write_img("is'Breima' Amadou Dicko.jpg")
        result = self._run({"I5": {"nom": "Amadou Dicko", "photo": None}})
        self.assertIn("I5", result)

    def test_no_match_returns_empty(self):
        self._write_img("isInconnu.jpg")
        result = self._run({"I1": {"nom": "Nom Totalement Différent", "photo": None}})
        self.assertEqual(result, {})

    def test_missing_images_src_returns_empty(self):
        import parse_gramps
        orig = parse_gramps.IMAGES_SRC
        parse_gramps.IMAGES_SRC = Path("/chemin/inexistant/xxxx")
        try:
            result = match_photos({"I1": {"nom": "Test", "photo": None}})
        finally:
            parse_gramps.IMAGES_SRC = orig
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
