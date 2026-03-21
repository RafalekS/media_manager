#!/bin/bash
# Silent (non-interactive) archive extractor for QNAP NAS.
# Called via SSH from media_manager Extract step.
#
# Usage: extractor_silent.sh <work_dir> [--no-delete]
#
# Arguments:
#   work_dir     Path to folder containing archives (required)
#   --no-delete  Keep archives after successful extraction (default: delete)

set -euo pipefail

# QNAP puts tools in /usr/local/sbin which isn't in non-login SSH PATH
export PATH="/usr/local/sbin:/usr/local/bin:$PATH"

WORK_DIR="${1:-}"
DELETE_AFTER=true

if [[ "$*" == *"--no-delete"* ]]; then
    DELETE_AFTER=false
fi

if [[ -z "$WORK_DIR" ]]; then
    echo "[ERROR] Usage: $0 <work_dir> [--no-delete]"
    exit 1
fi

if [[ ! -d "$WORK_DIR" ]]; then
    echo "[ERROR] Directory not found: $WORK_DIR"
    exit 1
fi

LOG_FILE="$WORK_DIR/unpack.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ── Clean filename (matches Python clean_folder_name logic) ──────────────────
clean_name() {
    local raw="$1"
    local name

    # Strip extension
    name="${raw%.*}"

    # Strip version / build / update / date tags
    name=$(echo "$name" | sed -E '
        s/[._-]+(v|V)[0-9]+[\.0-9]*.*//g
        s/[._-]+(build|Build)[._-]*[0-9]+.*//g
        s/[._-]+(update|Update)[._-].*//g
        s/[._-]+[0-9]{4}[._-][0-9]{2}[._-][0-9]{2}.*//g
        s/[._-]+(RUNE|TENOKE|SKIDROW|DINO|DINOByTES|Razor1911|TiNYiSO|Unleashed|FitGirl|CODEX|EMPRESS|SiMPLEX|RELOADED|HOODLUM).*//gi
    ')

    # Dots and underscores → spaces, collapse whitespace
    name=$(echo "$name" | tr '._' ' ' | tr -s ' ' | sed 's/^ //;s/ $//')

    # Remove non-alphanumeric except spaces and hyphens
    name=$(echo "$name" | sed 's/[^a-zA-Z0-9 -]//g')

    # Truncate, spaces → underscores, trim underscores
    name=$(echo "$name" | cut -c1-60 | sed 's/ /_/g;s/^_*//;s/_*$//')

    echo "${name:-extracted_archive}"
}

# ── Flatten single inner subfolder ───────────────────────────────────────────
flatten_if_single_subdir() {
    local dest="$1"
    local items
    mapfile -t items < <(find "$dest" -maxdepth 1 -mindepth 1)

    if [[ ${#items[@]} -eq 1 && -d "${items[0]}" ]]; then
        local subdir="${items[0]}"
        log "  Flattening inner folder: $(basename "$subdir")/"
        find "$subdir" -maxdepth 1 -mindepth 1 -exec mv {} "$dest/" \;
        rmdir "$subdir" 2>/dev/null || true
    fi
}

# ── Find archives ─────────────────────────────────────────────────────────────
declare -a ARCHIVES=()

while IFS= read -r -d '' f; do
    name=$(basename "$f")
    ext="${name##*.}"
    ext_lower=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    # Skip multi-part continuations
    if [[ "$name" =~ \.part([0-9]+)\.rar$ ]]; then
        part_num="${BASH_REMATCH[1]}"
        [[ "$part_num" -gt 1 ]] && continue
    fi
    if [[ "$ext_lower" =~ ^r[0-9]{2}$ || "$ext_lower" =~ ^s[0-9]{2}$ ]]; then
        continue
    fi

    if [[ "$ext_lower" == "rar" || "$ext_lower" == "zip" || "$ext_lower" == "7z" ]]; then
        ARCHIVES+=("$f")
    fi
done < <(find "$WORK_DIR" -maxdepth 1 -type f -print0 | sort -z)

TOTAL=${#ARCHIVES[@]}

if [[ $TOTAL -eq 0 ]]; then
    log "No archives found in: $WORK_DIR"
    exit 0
fi

# ── Write log header ──────────────────────────────────────────────────────────
{
    echo ""
    echo "=================================================="
    echo "Archive Extractor Log — $TIMESTAMP"
    echo "Source: $WORK_DIR"
    echo "Delete after: $DELETE_AFTER"
    echo "=================================================="
} >> "$LOG_FILE"

log "Found $TOTAL archive(s) in: $WORK_DIR"

SUCCESS=0
FAIL=0
IDX=0

for archive in "${ARCHIVES[@]}"; do
    ((IDX++))
    name=$(basename "$archive")
    folder_name=$(clean_name "$name")
    dest="$WORK_DIR/$folder_name"

    if [[ -d "$dest" ]]; then
        log "[$IDX/$TOTAL] Skip — already exists: $folder_name/"
        echo "[SKIP] $name" >> "$LOG_FILE"
        continue
    fi

    log "[$IDX/$TOTAL] Extracting: $name  →  $folder_name/"
    mkdir -p "$dest"

    ext_lower=$(echo "${name##*.}" | tr '[:upper:]' '[:lower:]')
    ok=false

    if [[ "$ext_lower" == "rar" ]]; then
        if unrar x -y "$archive" "$dest/" >> "$LOG_FILE" 2>&1; then
            ok=true
        fi
    elif [[ "$ext_lower" == "zip" ]]; then
        if unzip -o "$archive" -d "$dest/" >> "$LOG_FILE" 2>&1; then
            ok=true
        fi
    elif [[ "$ext_lower" == "7z" ]]; then
        if 7z x "$archive" "-o$dest" -y >> "$LOG_FILE" 2>&1; then
            ok=true
        fi
    fi

    if $ok; then
        flatten_if_single_subdir "$dest"
        log "  [OK]"
        echo "[OK] $name → $folder_name/" >> "$LOG_FILE"
        ((SUCCESS++))
        if $DELETE_AFTER; then
            if rm "$archive"; then
                log "  Deleted: $name"
                echo "[DELETED] $name" >> "$LOG_FILE"
            else
                log "  [WARN] Could not delete: $name"
            fi
        fi
    else
        log "  [FAIL] $name"
        echo "[FAIL] $name" >> "$LOG_FILE"
        # Clean up empty dest
        rmdir "$dest" 2>/dev/null || true
        ((FAIL++))
    fi
done

log ""
log "Done: $SUCCESS extracted, $FAIL failed."
echo "Total: $SUCCESS extracted, $FAIL failed — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
