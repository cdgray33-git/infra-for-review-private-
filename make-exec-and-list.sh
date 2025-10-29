#!/usr/bin/env bash
# make-exec-and-list.sh
# Idempotent helper to set +x on shell scripts and list them with full path and permissions.
#
# Usage:
#   ./make-exec-and-list.sh                # operate in current directory, change permissions and list
#   ./make-exec-and-list.sh --path /repo   # target a different root
#   ./make-exec-and-list.sh --dry-run      # show what would be changed, do not modify
#   ./make-exec-and-list.sh --pattern '*.sh'  # use a different filename pattern
#
# Notes:
# - If the script cannot chmod a file because of permission restrictions it will attempt to use sudo.
# - It prints a summary of which files were changed and a final full listing (ls -l) of matching files.
# - Designed for POSIX shells; run on Linux/macOS. For Windows PowerShell use the earlier provided PS script.

set -euo pipefail

# Defaults
TARGET_DIR="."
PATTERN="*.sh"
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 [--path DIR] [--pattern GLOB] [--dry-run] [-h|--help]

Options:
  --path DIR        Root directory to search (default: current directory)
  --pattern GLOB    Filename glob to match (default: '*.sh')
  --dry-run         Do not change permissions; only report what would be done
  -h, --help        Show this help
EOF
  exit 1
}

# Simple arg parse
while [[ $# -gt 0 ]]; do
  case "$1" in
    --path) TARGET_DIR="$2"; shift 2 ;;
    --pattern) PATTERN="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1"; usage ;;
  esac
done

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Error: target path does not exist: $TARGET_DIR" >&2
  exit 2
fi

echo "Target directory: $TARGET_DIR"
echo "Filename pattern: $PATTERN"
echo "Dry run: $DRY_RUN"
echo ""

# Collect matching files safely (handle spaces/newlines)
mapfile -d '' files < <(find "$TARGET_DIR" -type f -name "$PATTERN" -print0)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No files matching pattern found under $TARGET_DIR"
  exit 0
fi

changed=()
failed=()

for f in "${files[@]}"; do
  # strip possible trailing NUL from mapfile entry (mapfile -d '' keeps no delimiter)
  file="$f"
  # normalize
  file="$(printf '%s' "$file")"
  # get current perms
  perms=$(stat -c '%A' "$file" 2>/dev/null || stat -f '%A' "$file" 2>/dev/null || echo "unknown")
  if [[ "$DRY_RUN" == true ]]; then
    if [[ "$perms" == *"x"* ]]; then
      echo "[DRY] already executable: $file ($perms)"
    else
      echo "[DRY] would chmod +x:   $file ($perms)"
    fi
    continue
  fi

  # if file is already executable for owner/group/other, skip chmod but list
  if [[ "$perms" == *"x"* ]]; then
    echo "Already executable: $file ($perms)"
    continue
  fi

  # try chmod normally, fallback to sudo
  if chmod +x "$file" 2>/dev/null; then
    changed+=("$file")
    echo "Made executable: $file"
  else
    echo "Attempting sudo chmod +x on: $file"
    if sudo chmod +x "$file"; then
      changed+=("$file")
      echo "Made executable (sudo): $file"
    else
      echo "FAILED to chmod: $file" >&2
      failed+=("$file")
    fi
  fi
done

echo ""
echo "=== Summary ==="
echo "Total matched files: ${#files[@]}"
echo "Files made executable: ${#changed[@]}"
if [[ ${#changed[@]} -gt 0 ]]; then
  printf '%s\n' "${changed[@]}"
fi
if [[ ${#failed[@]} -gt 0 ]]; then
  echo ""
  echo "Files that failed to change (inspect permissions/ownership):"
  printf '%s\n' "${failed[@]}"
fi

echo ""
echo "=== Full listing of matched files (ls -l) ==="
# Use find to list files with full path and long listing to show permissions and ownership
# Use -exec ls -ld "{}" \; to avoid issues with many files
for f in "${files[@]}"; do
  # ensure file exists (defensive)
  if [[ -e "$f" ]]; then
    ls -ld -- "$f"
  fi
done

echo ""
echo "Done."