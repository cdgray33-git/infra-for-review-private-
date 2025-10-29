#!/usr/bin/env bash
set -euo pipefail

# infra_repo_upload.sh
# Usage:
#   sudo ./infra_repo_upload.sh [repo_name] [make_private]
# Example:
#   sudo ./infra_repo_upload.sh infra-for-review-private- true
#
# What it does:
#  - creates a sanitized copy of the current repository under ./infra-upload
#  - redacts sensitive-looking keys in files under ./config/*.env and root *.env
#  - excludes large model dirs and other runtime artifacts
#  - initializes a git repo, commits the sanitized copy
#  - if gh CLI is present and authenticated it will create a GitHub repo and push
#
# IMPORTANT:
#  - The script replaces values for keys containing: PASS, PASSWORD, SECRET, TOKEN, KEY, ADMIN, CREDENTIAL, API_KEY, APIKEY, AUTH
#  - The script avoids copying model files; verify infra-upload before pushing.
#  - After pushing, rotate any real credentials used on the actual host.

REPO_NAME="${1:-infra-for-review}"
MAKE_PRIVATE="${2:-true}"   # true or false
OUTDIR="$(pwd)/infra-upload"

# Exclude patterns (rsync --exclude)
EXCLUDES=(
  "openwebui/models"
  "openwebui/models/*"
  "/mnt/llama_models"
  "/mnt/llama_models/*"
  "*/models/*"
  "node_modules"
  ".venv"
  "__pycache__"
  "*.pyc"
  ".git"
  ".git/*"
  ".env"
)

# Sensitive key fragments (case-insensitive)
SENSITIVE_KEYS=("PASS" "PASSWORD" "SECRET" "TOKEN" "KEY" "ADMIN" "CREDENTIAL" "API_KEY" "APIKEY" "AUTH")

echo "Preparing sanitized copy -> $OUTDIR"
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

# Build rsync exclude args
RSYNC_EXCLUDES=()
for ex in "${EXCLUDES[@]}"; do
  RSYNC_EXCLUDES+=(--exclude "$ex")
done

# Copy repo to OUTDIR excluding big folders and .git
echo "Copying repository files (excluding model dirs and runtime files)..."
rsync -av "${RSYNC_EXCLUDES[@]}" --exclude-from=/dev/null . "$OUTDIR/" >/dev/null

# Redact env files in config/ and root-level *.env
redact_file() {
  src="$1"
  dst="$2"
  tmp="$(mktemp)"
  # preserve comments and blank lines, redact values for keys that match SENSITIVE_KEYS
  while IFS= read -r line || [ -n "$line" ]; do
    # preserve comment or empty
    if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "$line" ]]; then
      echo "$line" >> "$tmp"
      continue
    fi
    # if contains '=' treat as key=value
    if [[ "$line" == *"="* ]]; then
      key="${line%%=*}"
      val="${line#*=}"
      upkey="$(echo "$key" | tr '[:lower:]' '[:upper:]')"
      redacted=false
      for sk in "${SENSITIVE_KEYS[@]}"; do
        if [[ "$upkey" == *"$sk"* ]]; then
          redacted=true
          break
        fi
      done
      if $redacted; then
        echo "${key}=REDACTED" >> "$tmp"
      else
        echo "${key}=${val}" >> "$tmp"
      fi
    else
      # keep line as-is
      echo "$line" >> "$tmp"
    fi
  done < "$src"
  mv "$tmp" "$dst"
  chmod 600 "$dst" || true
}

echo "Redacting config/*.env and root-level *.env files (if present)..."

# config directory
if [ -d "$OUTDIR/config" ]; then
  for f in "$OUTDIR"/config/*; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    echo " - redacting config/$base"
    redact_file "$f" "$f"
  done
else
  echo " - no config/ directory in sanitized copy (ok)"
fi

# root-level env files: any *.env files in OUTDIR root
shopt -s nullglob
for f in "$OUTDIR"/*.env; do
  [ -f "$f" ] || continue
  base=$(basename "$f")
  echo " - redacting root $base"
  redact_file "$f" "$f"
done
shopt -u nullglob

# Create a protective .gitignore to avoid accidental commits of model or secret files
cat > "$OUTDIR/.gitignore" <<'GITIGNORE'
# Ignore model files and sensitive envs
openwebui/models/
openwebui/models/*
/mnt/llama_models/
/config/*.env
*.env
*.pem
*.key
node_modules/
__pycache__/
*.pyc
.vscode/
.idea/
infra-upload/
GITIGNORE

# Ensure .gitignore readable
chmod 644 "$OUTDIR/.gitignore"

# Initialize git repo and commit sanitized copy
cd "$OUTDIR"
if [ ! -d ".git" ]; then
  git init -b main >/dev/null 2>&1 || git init >/dev/null 2>&1
fi

git add -A
if git commit -m "Sanitized copy for review: ${REPO_NAME}" >/dev/null 2>&1; then
  echo "Committed sanitized copy in $OUTDIR"
else
  echo "No changes to commit or commit failed; continuing"
fi

# If gh cli exists and user wants auto-create, try to create and push to GitHub
if command -v gh >/dev/null 2>&1; then
  echo "gh CLI is available."
  if [ "$MAKE_PRIVATE" = "true" ] || [ "$MAKE_PRIVATE" = "True" ]; then
    echo "Creating private GitHub repo named $REPO_NAME and pushing..."
    # Attempt to create and push; if repo exists try to push
    set +e
    gh repo create "$REPO_NAME" --private --description "Sanitized infra repo for review" --source=. --remote=origin --push
    rc=$?
    set -e
    if [ $rc -ne 0 ]; then
      echo "gh repo create returned non-zero (repo may already exist). Attempting to set remote and push..."
      # try to get remote and push
      remote_url=$(gh repo view "$REPO_NAME" --json sshUrl -q .sshUrl 2>/dev/null || true)
      if [ -n "$remote_url" ]; then
        git remote remove origin 2>/dev/null || true
        git remote add origin "$remote_url" 2>/dev/null || true
      fi
      git branch -M main 2>/dev/null || true
      git push -u origin main 2>/dev/null || true
    fi
    # print remote url
    if git remote get-url origin >/dev/null 2>&1; then
      echo "Remote origin: $(git remote get-url origin)"
      echo "Sanitized repo pushed. Review the remote and then share the link here when ready."
    else
      echo "Could not determine remote URL. Please push manually if desired."
    fi
  else
    echo "User requested not to auto-create a private repo. Please create a repo and push manually."
    echo "To push manually:"
    echo "  git remote add origin git@github.com:<your-org-or-user>/${REPO_NAME}.git"
    echo "  git branch -M main"
    echo "  git push -u origin main"
  fi
else
  echo "gh CLI not found. Please create the GitHub repo manually and push the infra-upload directory."
  echo "Manual push instructions:"
  echo "  cd \"$OUTDIR\""
  echo "  git remote add origin git@github.com:<your-org-or-user>/${REPO_NAME}.git"
  echo "  git branch -M main"
  echo "  git push -u origin main"
fi

echo ""
echo "SANITIZED COPY LOCATION: $OUTDIR"
echo "IMPORTANT NEXT STEPS:"
echo " - Inspect files in $OUTDIR carefully to confirm all secrets are redacted."
echo " - Rotate any real credentials used in your live system (DB passwords, API keys, email passwords)."
echo " - If you allowed the script to push, share the repo URL here so I can review and produce the merged compose & ports mapping."
echo " - If you did NOT allow auto-push, run the manual push commands printed above."
