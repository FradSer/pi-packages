#!/usr/bin/env bash
#
# Lark CLI Skills Sync Script
# Syncs skills/ directory from upstream larksuite/cli repo into local package
#

set -euo pipefail

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
UPSTREAM_REPO="https://github.com/larksuite/cli.git"
UPSTREAM_BRANCH="main"
UPSTREAM_PATH="skills"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
TARGET_DIR="$SCRIPT_DIR/../skills"
BACKUP_DIR="$TARGET_DIR/.backup"
TEMP_DIR="/tmp/lark-cli-sync-$$"

# Local files (not overwritten)
LOCAL_FILES=("SKILL.md")

# Bundled denest / index generator tools (local package root tools/skill-sync/)
DENEST_SCRIPT="$SCRIPT_DIR/../tools/skill-sync/denest.py"
GEN_INDEX_SCRIPT="$SCRIPT_DIR/../tools/skill-sync/gen-index.py"

show_help() {
    cat << EOF
${BLUE}Lark CLI Skills Sync Script${NC}

${GREEN}Usage:${NC}
    $0 [options]

${GREEN}Options:${NC}
    -h, --help          Show this help message
    -c, --check         Check for updates without performing sync
    -f, --force         Force sync, skip confirmation
    --no-backup         Do not create backup during sync

${GREEN}Examples:${NC}
    $0                  # Sync and backup existing files
    $0 --check          # Check for updates only
    $0 --force          # Force sync, skip confirmation

${GREEN}Upstream Repository:${NC}
    $UPSTREAM_REPO (branch: $UPSTREAM_BRANCH)

${GREEN}Local Transforms:${NC}
    After sync, renames lark-*/SKILL.md to lark-*/<dirname>.md
    (only root SKILL.md router is auto-discovered)

EOF
}

log_info() {
    printf "${BLUE}[INFO]${NC} %s\n" "$1"
}

log_success() {
    printf "${GREEN}[SUCCESS]${NC} %s\n" "$1"
}

log_warning() {
    printf "${YELLOW}[WARNING]${NC} %s\n" "$1"
}

log_error() {
    printf "${RED}[ERROR]${NC} %s\n" "$1"
}

update_sync_md_field() {
    local file="$1" key="$2" value="$3"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^\*\*$key\*\*: .*|**$key**: $value|" "$file"
    else
        sed -i "s|^\*\*$key\*\*: .*|**$key**: $value|" "$file"
    fi
}

check_requirements() {
    local missing_tools=()

    for tool in git diff python3; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi
}

cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

clone_upstream() {
    log_info "Fetching skills directory from upstream repository..."

    mkdir -p "$TEMP_DIR"

    git clone --depth 1 --filter=blob:none --sparse \
        "$UPSTREAM_REPO" "$TEMP_DIR/repo" 2>/dev/null

    cd "$TEMP_DIR/repo"
    git sparse-checkout set "$UPSTREAM_PATH" 2>/dev/null
    cd - > /dev/null

    if [ ! -d "$TEMP_DIR/repo/$UPSTREAM_PATH" ]; then
        log_error "$UPSTREAM_PATH directory not found in upstream repo"
        return 1
    fi

    log_success "Upstream files fetched successfully"
    return 0
}

create_backup() {
    if [ ! -d "$TARGET_DIR" ]; then
        log_info "Target directory does not exist, skipping backup"
        return 0
    fi

    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$BACKUP_DIR/$timestamp"

    mkdir -p "$backup_path"

    local count=0
    while IFS= read -r -d '' item; do
        local basename
        basename=$(basename "$item")

        local skip=false
        for local_file in "${LOCAL_FILES[@]}"; do
            if [ "$basename" = "$local_file" ]; then
                skip=true
                break
            fi
        done
        [ "$basename" = ".backup" ] && skip=true
        [ "$skip" = true ] && continue

        cp -R "$item" "$backup_path/"
        count=$((count + 1))
    done < <(find "$TARGET_DIR" -maxdepth 1 -mindepth 1 -print0)

    if [ $count -gt 0 ]; then
        log_success "Backed up $count items to: $backup_path"
        prune_backups
    else
        log_info "Nothing to backup"
        rmdir "$backup_path" 2>/dev/null || true
    fi
}

KEEP_BACKUPS=2
prune_backups() {
    [ -d "$BACKUP_DIR" ] || return 0
    local old
    while IFS= read -r old; do
        [ -n "$old" ] || continue
        rm -rf "$BACKUP_DIR/$old"
        log_info "Cleaned up old backup: $old"
    done < <(ls -1 "$BACKUP_DIR" 2>/dev/null | sort -r | tail -n +$((KEEP_BACKUPS + 1)))
}

apply_denest() {
    local tree="$1"
    if [ ! -f "$DENEST_SCRIPT" ]; then
        log_error "Missing denest tool: $DENEST_SCRIPT"
        return 1
    fi
    python3 "$DENEST_SCRIPT" --tree "$tree" || return 1
}

check_diff() {
    local upstream_skills="$TEMP_DIR/repo/$UPSTREAM_PATH"
    local compare_dir="$TEMP_DIR/denested"
    local has_changes=false
    local new_count=0
    local changed_count=0
    local deleted_count=0

    if [ ! -d "$TARGET_DIR" ]; then
        log_warning "Local directory does not exist, will create new files"
        return 1
    fi

    log_info "Checking file differences..."

    rm -rf "$compare_dir"
    mkdir -p "$compare_dir"
    while IFS= read -r -d '' item; do
        cp -R "$item" "$compare_dir/"
    done < <(find "$upstream_skills" -maxdepth 1 -mindepth 1 -print0)
    apply_denest "$compare_dir" || return 1

    while IFS= read -r -d '' upstream_file; do
        local rel_path="${upstream_file#$compare_dir/}"
        local local_file="$TARGET_DIR/$rel_path"

        if [ ! -f "$local_file" ]; then
            new_count=$((new_count + 1))
            has_changes=true
        elif ! diff -q "$local_file" "$upstream_file" &> /dev/null; then
            changed_count=$((changed_count + 1))
            has_changes=true
        fi
    done < <(find "$compare_dir" -type f -print0)

    while IFS= read -r -d '' local_file; do
        local rel_path="${local_file#$TARGET_DIR/}"
        local basename
        basename=$(basename "$rel_path")
        local dirname
        dirname=$(dirname "$rel_path")

        local skip=false
        for lf in "${LOCAL_FILES[@]}"; do
            [ "$basename" = "$lf" ] && [ "$dirname" = "." ] && skip=true && break
        done
        [[ "$rel_path" == .backup* ]] && skip=true
        [ "$skip" = true ] && continue

        local upstream_file="$compare_dir/$rel_path"
        if [ ! -f "$upstream_file" ]; then
            deleted_count=$((deleted_count + 1))
            has_changes=true
        fi
    done < <(find "$TARGET_DIR" -type f -print0)

    if [ "$has_changes" = true ]; then
        [ $new_count -gt 0 ] && log_info "  Added: $new_count files"
        [ $changed_count -gt 0 ] && log_info "  Changed: $changed_count files"
        [ $deleted_count -gt 0 ] && log_info "  Deleted: $deleted_count files (removed upstream)"
        return 1
    else
        log_success "All files are up to date"
        return 0
    fi
}

sync_files() {
    local no_backup="$1"
    local upstream_skills="$TEMP_DIR/repo/$UPSTREAM_PATH"

    if [ "$no_backup" != "true" ]; then
        create_backup
    fi

    log_info "Syncing files..."

    while IFS= read -r -d '' item; do
        local basename
        basename=$(basename "$item")

        local skip=false
        for local_file in "${LOCAL_FILES[@]}"; do
            [ "$basename" = "$local_file" ] && skip=true && break
        done
        [ "$basename" = ".backup" ] && skip=true
        [ "$skip" = true ] && continue

        rm -rf "$item"
    done < <(find "$TARGET_DIR" -maxdepth 1 -mindepth 1 -print0)

    local count=0
    while IFS= read -r -d '' item; do
        cp -R "$item" "$TARGET_DIR/"
        count=$((count + 1))
    done < <(find "$upstream_skills" -maxdepth 1 -mindepth 1 -print0)

    log_success "Sync complete: $count skill directories synced"

    log_info "Denesting sub-skills (SKILL.md -> <dirname>.md)..."
    apply_denest "$TARGET_DIR" || return 1

    if [ -f "$GEN_INDEX_SCRIPT" ]; then
        python3 "$GEN_INDEX_SCRIPT" \
            --skills "$TARGET_DIR" \
            --router "$TARGET_DIR/SKILL.md" \
            --hoist lark-shared \
            --display "lark-shared=Shared Config & Auth" \
            --display "lark-doc=Documents" \
            --display "lark-markdown=Markdown" \
            --display "lark-sheets=Spreadsheets" \
            --display "lark-base=Multidimensional Tables" \
            --display "lark-calendar=Calendar" \
            --display "lark-im=Instant Messaging" \
            --display "lark-mail=Email" \
            --display "lark-task=Tasks" \
            --display "lark-okr=OKR" \
            --display "lark-drive=Drive" \
            --display "lark-wiki=Wiki" \
            --display "lark-slides=Slides" \
            --display "lark-apps=Web Apps (Miaoda)" \
            --display "lark-whiteboard=Whiteboard" \
            --display "lark-approval=Approval" \
            --display "lark-attendance=Attendance" \
            --display "lark-contact=Contact" \
            --display "lark-vc=Video Conference" \
            --display "lark-vc-agent=VC Agent (live)" \
            --display "lark-minutes=Minutes" \
            --display "lark-note=Note" \
            --display "lark-event=Event Subscription" \
            --display "lark-openapi-explorer=OpenAPI Explorer" \
            --display "lark-skill-maker=Skill Maker" \
            --display "lark-workflow-meeting-summary=Workflow: Meeting Summary" \
            --display "lark-workflow-standup-report=Workflow: Standup Report" \
            || log_warning "gen-index.py failed, please re-run manually"
    fi

    local sync_md="$SCRIPT_DIR/../SYNC.md"
    if [ -f "$sync_md" ]; then
        local lark_ver synced_commit today
        today=$(date +%Y-%m-%d)
        lark_ver=$(lark-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        [ -z "$lark_ver" ] && lark_ver="unknown"
        synced_commit=$(git -C "$TEMP_DIR/repo" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        update_sync_md_field "$sync_md" "Last sync" "$today"
        update_sync_md_field "$sync_md" "lark-cli version" "$lark_ver"
        update_sync_md_field "$sync_md" "Synced commit" "$synced_commit"
        log_info "Updated SYNC.md (date=$today, lark-cli=$lark_ver, commit=$synced_commit)"
    fi
}

main() {
    local check_only=false
    local force_sync=false
    local no_backup=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -c|--check)
                check_only=true
                shift
                ;;
            -f|--force)
                force_sync=true
                shift
                ;;
            --no-backup)
                no_backup=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    log_info "Starting Lark CLI skills sync..."

    check_requirements
    clone_upstream

    local has_diff=0
    check_diff || has_diff=$?

    if [ "$check_only" = true ]; then
        if [ $has_diff -eq 0 ]; then
            log_success "No updates available"
            exit 0
        else
            log_info "Updates available, run $0 to sync"
            exit 1
        fi
    fi

    if [ $has_diff -eq 0 ] && [ "$force_sync" != true ]; then
        exit 0
    fi

    if [ "$force_sync" != true ] && [ -t 0 ]; then
        echo -n "Continue sync? [y/N] "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Sync cancelled"
            exit 0
        fi
    fi

    sync_files "$no_backup"

    log_success "Sync completed successfully!"
}

main "$@"
