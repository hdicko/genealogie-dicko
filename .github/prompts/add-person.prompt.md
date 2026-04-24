---
mode: agent
description: Ajouter une nouvelle personne à l'arbre généalogique Dicko Ardo Hayre
---

# Ajouter une personne à l'arbre généalogique

## Contexte

La source de vérité est `data/famille.json`. Les fichiers `content/personnes/*.md`
sont auto-générés à partir de ce fichier — **ne jamais les modifier manuellement**.

Les IDs de personnes viennent de Gramps (ex. `I1`, `I351`, `0497`). Pour une nouvelle
personne saisie manuellement, choisir un ID libre au format `M001`, `M002`, etc.
(préfixe `M` pour "manuel").

## Étapes

### 1. Recueillir les informations

Demander à l'utilisateur les informations suivantes (toutes optionnelles sauf le nom et l'ID) :

| Champ | Description | Valeur par défaut |
|-------|-------------|-------------------|
| `gramps_id` | Identifiant unique (ex. `M001`) | — obligatoire |
| `nom` | Prénom et nom complet | — obligatoire |
| `genre` | `"male"`, `"female"` ou `"unknown"` | `"unknown"` |
| `naissance` | Date de naissance (texte libre) | `""` |
| `deces` | Date de décès (texte libre) | `""` |
| `ville` | Lieu associé | `""` |
| `commentaires` | Notes biographiques | `""` |
| `photo` | Chemin `/images/personnes/fichier.jpg` | `null` |
| `parents` | Liste `[{nom, id, relation}]` — relation : `"pere"` ou `"mere"` | `[]` |
| `fratrie` | Liste `[{nom, id}]` | `[]` |
| `familles` | Liste `[{conjoint, conjoint_id, enfants:[{nom,id}]}]` | `[]` |

### 2. Vérifier l'unicité de l'ID

```bash
python3 - <<'EOF'
import json, sys
data = json.load(open("data/famille.json"))
gid = input("ID à vérifier : ").strip()
if gid in data["personnes"]:
    print(f"⚠️  ID {gid!r} déjà utilisé par : {data['personnes'][gid]['nom']}")
else:
    print(f"✅ ID {gid!r} disponible")
EOF
```

### 3. Ajouter l'entrée dans `data/famille.json`

Insérer dans `data["personnes"]` un objet respectant ce schéma :

```json
{
  "gramps_id": "M001",
  "nom": "Prénom Nom",
  "genre": "male",
  "naissance": "",
  "deces": "",
  "ville": "",
  "commentaires": "",
  "photo": null,
  "parents": [],
  "fratrie": [],
  "familles": [],
  "html_file": null
}
```

Incrémenter aussi `data["total"]` de 1.

### 4. Générer le fichier Markdown

Appeler `regen_markdown` depuis le package `genealogie` :

```python
import sys
sys.path.insert(0, "scripts")
import json
from genealogie.markup import regen_markdown

data = json.load(open("data/famille.json"))
gid  = "M001"   # remplacer par l'ID réel
regen_markdown(gid, data["personnes"][gid])
print(f"✅ content/personnes/{gid.lower()}.md généré")
```

Ou via le script dédié :

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import json
from genealogie.markup import regen_markdown
d = json.load(open('data/famille.json'))
regen_markdown('M001', d['personnes']['M001'])
"
```

### 5. Mettre à jour les références croisées (optionnel)

Si la personne ajoutée est mentionnée dans les `parents`, `familles` ou `fratrie`
d'autres personnes, mettre à jour ces entrées dans `famille.json` et regénérer
les fichiers `.md` concernés via `regen_markdown`.

### 6. Valider

```bash
# Vérifier que Hugo accepte le fichier généré
hugo --minify 2>&1 | grep -i "error\|warn" || echo "✅ Build OK"

# Vérifier la page de la personne en local
hugo server &
# Ouvrir http://localhost:1313/personnes/m001/
```

## Règles importantes

- **Ne jamais modifier** un fichier `content/personnes/*.md` directement.
- Les fichiers `.md` sont **toujours entièrement regénérés** par `regen_markdown` — pas de mise à jour partielle.
- Le champ `html_file` doit être `null` pour les personnes créées manuellement (il pointe vers l'export Gramps, non applicable ici).
- Les noms sont **dénormalisés** dans les listes `parents`/`familles`/`fratrie` — si le nom d'une personne change, utiliser `update_references(persons, gid, old_nom, new_nom)` depuis `genealogie/markup.py`.
