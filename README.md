# Arbre Généalogique — Famille Dicko Ardo Hayre

Site généalogique interactif pour les familles **Diona · Boundoucoli · Dalla · Boni**.

Il permet de :
- consulter les fiches individuelles de chaque personne (naissance, décès, lieu, parents, conjoint(s), enfants) ;
- naviguer dans un arbre interactif en D3.js ;
- modifier les informations et photos directement depuis le navigateur (en local).

---

## Sommaire

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Lancer le site en local](#lancer-le-site-en-local)
4. [Modifier une fiche](#modifier-une-fiche)
5. [Ajouter ou changer une photo](#ajouter-ou-changer-une-photo)
6. [Importer depuis Gramps](#importer-depuis-gramps)
7. [Déployer sur Netlify](#déployer-sur-netlify)
8. [Structure du projet](#structure-du-projet)
9. [Questions fréquentes](#questions-fréquentes)

---

## Prérequis

| Outil | Version minimale | Utilité |
|---|---|---|
| [Hugo](https://gohugo.io/installation/) | **0.159.0** | Génère le site statique |
| [Python](https://www.python.org/downloads/) | 3.9+ | API locale d'édition + import Gramps |
| [pip](https://pip.pypa.io/) | — | Installe les dépendances Python |
| [Git](https://git-scm.com/) | — | Versionnement |

> ⚠️ La version **0.159.0 de Hugo est obligatoire**. Les versions antérieures ne supportent pas `hugo.Data`, utilisé pour lire `data/famille.json`.

---

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd genealogie

# 2. Installer les dépendances Python
pip install beautifulsoup4 lxml
```

Aucune dépendance npm ou autre outil de build n'est nécessaire.

---

## Lancer le site en local

Le site fonctionne avec **deux processus** : le serveur Hugo pour la navigation, et l'API Python pour l'édition.

### Terminal 1 — Serveur Hugo

```bash
hugo server
```

Le site est disponible sur **http://localhost:1313**.

Hugo recharge automatiquement la page à chaque modification de fichier.

### Terminal 2 — API d'édition (optionnel)

Nécessaire uniquement si vous souhaitez modifier des fiches ou des photos depuis le navigateur.

```bash
python3 scripts/api_server.py
```

L'API tourne sur **http://127.0.0.1:1315** et répond aux modifications envoyées par les formulaires du site.
Les interfaces d'édition acceptent aussi bien **localhost** que **127.0.0.1** côté navigateur.

---

## Modifier une fiche

1. Ouvrez la fiche d'une personne : **http://localhost:1313/personnes/{id}/**  
   *(exemple : `/personnes/i1/` pour la personne I1)*
2. Cliquez sur le bouton **✏️ Modifier**.
3. Remplissez les champs souhaités : nom, genre, date de naissance, date de décès, lieu, commentaires.
4. Cliquez sur **Enregistrer**.

Les modifications sont immédiatement sauvegardées dans `data/famille.json` et le fichier markdown correspondant est régénéré.

> ℹ️ Les relations (parents, conjoint, enfants) ne peuvent pas être modifiées via l'interface. Elles sont gérées par l'import Gramps (voir [Importer depuis Gramps](#importer-depuis-gramps)).

---

## Ajouter ou changer une photo

Depuis la fiche d'une personne (avec l'API démarrée) :

1. Cliquez sur **✏️ Modifier**.
2. Dans la section *Photo*, cliquez sur **Choisir un fichier** et sélectionnez une image.
3. Formats acceptés : `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` — taille max **10 Mo**.
4. Cliquez sur **Enregistrer**.

La photo est sauvegardée dans `static/images/personnes/` sous le nom `{ID}.{ext}`.

Pour **supprimer** une photo, cliquez sur **🗑️ Supprimer la photo** dans le formulaire d'édition.

---

## Importer depuis Gramps

L'intégralité des données (personnes, relations, photos) provient d'un export HTML du logiciel [Gramps](https://gramps-project.org/). Pour mettre à jour le site après une modification dans Gramps :

### 1. Exporter depuis Gramps

Dans Gramps : **Fichier → Exporter → Page web complète (HTML)**, vers le dossier configuré dans `scripts/parse_gramps.py` :

```python
GRAMPS_DIR = Path("/home/dicko/Documents/HD/Ardo Diona/Genealogie/Famille Dicko/Complet HTML")
```

### 2. Lancer le script d'import

```bash
python3 scripts/parse_gramps.py
```

Ce script :
- lit les pages HTML individuelles dans `GRAMPS_DIR/ppl/`
- copie les photos depuis `IMAGES_SRC` vers `static/images/personnes/`
- génère `data/famille.json` (base de données principale)
- génère `content/personnes/*.md` (une page Hugo par personne)

> ⚠️ Ce script **écrase** tout le contenu de `content/personnes/` et `data/famille.json`. Les modifications faites via l'API (noms, commentaires, photos) seront perdues si vous relancez l'import sans les avoir reportées dans Gramps au préalable.

---

## Déployer sur Netlify

Le site est configuré pour un déploiement automatique sur [Netlify](https://www.netlify.com/).

Chaque `git push` sur la branche principale déclenche automatiquement un build.

La configuration se trouve dans `netlify.toml` :

```toml
[build]
  command = "hugo --minify"
  publish = "public"

[build.environment]
  HUGO_VERSION = "0.159.0"
```

Pour un premier déploiement :
1. Connectez votre dépôt Git à Netlify.
2. Netlify détecte `netlify.toml` automatiquement.
3. Cliquez sur **Deploy site**.

---

## Structure du projet

```
genealogie/
├── hugo.toml                  # Configuration Hugo (titre, langue, rootPerson)
├── netlify.toml               # Configuration déploiement Netlify
│
├── data/
│   └── famille.json           # Base de données principale (généré par parse_gramps.py)
│
├── content/
│   ├── _index.md              # Page d'accueil
│   ├── arbre/_index.md        # Page de l'arbre interactif
│   └── personnes/             # Une page .md par personne (généré par parse_gramps.py)
│       ├── i1.md
│       └── ...
│
├── layouts/                   # Templates Hugo personnalisés (pas de thème externe)
│   ├── _default/baseof.html   # Structure commune : en-tête, nav, pied de page
│   ├── index.html             # Page d'accueil avec recherche
│   ├── personnes/single.html  # Fiche individuelle + formulaire d'édition
│   └── arbre/list.html        # Arbre D3.js interactif
│
├── static/
│   ├── css/style.css          # Feuille de style principale
│   └── images/personnes/      # Photos des personnes
│
└── scripts/
    ├── parse_gramps.py        # Import depuis export HTML Gramps
    ├── api_server.py          # Serveur API local (port 1315)
    └── genealogie/            # Package Python de l'API
        ├── handlers.py        # Logique des endpoints HTTP
        ├── data.py            # Lecture/écriture thread-safe de famille.json
        ├── markup.py          # Régénération des fichiers markdown
        └── config.py          # Constantes (chemins, limites, CORS)
```

---

## Questions fréquentes

**Le site affiche "0 personnes" ou ne charge pas les fiches.**  
Vérifiez que `data/famille.json` existe et n'est pas vide. Si besoin, relancez `python3 scripts/parse_gramps.py`.

**L'API ne répond pas / le bouton Modifier ne fonctionne pas.**  
Assurez-vous que `python3 scripts/api_server.py` est bien lancé dans un terminal séparé, et que Hugo tourne sur le port 1314 (`hugo server --port 1314`) ou le port par défaut 1313 selon votre configuration.

**Hugo échoue avec une erreur sur `hugo.Data`.**  
Votre version de Hugo est probablement inférieure à 0.159.0. Vérifiez avec `hugo version` et mettez à jour si nécessaire.

**Je veux changer la personne racine de l'arbre.**  
Modifiez la valeur `rootPerson` dans `hugo.toml` :
```toml
[params]
  rootPerson = "I1"   # remplacer par l'ID Gramps souhaité
```
