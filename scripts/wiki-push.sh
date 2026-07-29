#!/usr/bin/env bash
# Push generated wiki to both GitHub and GitLab wikis
set -euo pipefail

WIKI_OUTPUT="${WIKI_OUTPUT:-/wiki-output}"
GITHUB_REPO="${GITHUB_REPO:-batmunkhcom/nvr}"
GITLAB_REPO="${GITLAB_REPO:-batmunkh/nvr}"
GITLAB_HOST="${GITLAB_HOST:-git.mbm.mn}"

echo "=== Wiki Sync Push ==="
echo "Output dir: $WIKI_OUTPUT"
echo "GitHub repo: $GITHUB_REPO"
echo "GitLab repo: $GITLAB_REPO"

# Ensure wiki output exists
if [ ! -d "$WIKI_OUTPUT" ]; then
    echo "ERROR: $WIKI_OUTPUT not found. Run wiki-sync.py first."
    exit 1
fi

# --- Push to GitLab Wiki ---
echo ""
echo "--- Pushing to GitLab Wiki ---"
GITLAB_WIKI_URL="https://oauth2:${GITLAB_PUSH_TOKEN}@${GITLAB_HOST}/${GITLAB_REPO}.wiki.git"
git clone "$GITLAB_WIKI_URL" wiki-gitlab --depth 1 2>/dev/null || git clone "$GITLAB_WIKI_URL" wiki-gitlab

cp -r "$WIKI_OUTPUT"/. wiki-gitlab/
cd wiki-gitlab
git config user.name "wiki-sync-bot"
git config user.email "wiki-sync@mbm.mn"
git add .
if git commit -m "📚 Wiki sync from docs/ ($(date +%Y-%m-%d))"; then
    git push
    echo "✓ GitLab wiki pushed"
else
    echo "⊘ No changes in GitLab wiki"
fi
cd ..

# --- Push to GitHub Wiki ---
echo ""
echo "--- Pushing to GitHub Wiki ---"
GITHUB_WIKI_URL="https://${GITHUB_WIKI_TOKEN}@github.com/${GITHUB_REPO}.wiki.git"
git clone "$GITHUB_WIKI_URL" wiki-github --depth 1 2>/dev/null || git clone "$GITHUB_WIKI_URL" wiki-github

cp -r "$WIKI_OUTPUT"/. wiki-github/
cd wiki-github
git config user.name "wiki-sync-bot"
git config user.email "wiki-sync@mbm.mn"
git add .
if git commit -m "📚 Wiki sync from docs/ ($(date +%Y-%m-%d))"; then
    git push
    echo "✓ GitHub wiki pushed"
else
    echo "⊘ No changes in GitHub wiki"
fi
cd ..

echo ""
echo "=== Wiki sync complete ==="
