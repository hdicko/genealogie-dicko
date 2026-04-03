#!/usr/bin/env bash
# deploy.sh — Sauvegarde, commit, push et publication vers Netlify
# Usage: ./scripts/deploy.sh "Message de commit"
#        ./scripts/deploy.sh          (message auto-généré)
set -euo pipefail

REMOTE="ardo"
BRANCH="main"

cd "$(git rev-parse --show-toplevel)"

# Vérifier s'il y a des changements
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "✅ Aucun changement à déployer."
  exit 0
fi

echo ""
echo "📂 Fichiers modifiés :"
git status --short
echo ""

# Message de commit
if [ -n "${1:-}" ]; then
  MSG="$1"
else
  CHANGED=$(git diff --name-only HEAD 2>/dev/null | head -5 | tr '\n' ', ' | sed 's/,$//')
  NEW=$(git ls-files --others --exclude-standard | head -3 | tr '\n' ', ' | sed 's/,$//')
  PARTS=""
  [ -n "$CHANGED" ] && PARTS="modif: $CHANGED"
  [ -n "$NEW" ]     && PARTS="${PARTS:+$PARTS | }ajout: $NEW"
  MSG="${PARTS:-mise à jour du site}"
fi

echo "💬 Message : $MSG"
echo ""

# Stage + commit
git add -A
git commit -m "$MSG

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

# Push
echo "🚀 Push vers $REMOTE/$BRANCH…"
git push "$REMOTE" "$BRANCH"

echo ""
echo "✅ Déployé ! Netlify va construire le site automatiquement."
echo "🔗 Suivi : https://app.netlify.com"
echo "🔗 Dépôt : https://github.com/hdicko/genealogie-dicko"
