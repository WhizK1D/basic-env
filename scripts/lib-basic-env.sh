#!/bin/bash
# Shared helpers for the basic-env stage scripts. Source this file; it is
# not meant to be executed directly.
#
# Reads BASIC_ENV_DRY_RUN and BASIC_ENV_REPLACE_CONFIGS (0/1), defaulting to 0,
# and BASIC_ENV_REPO_ROOT (derived from this file's location if unset).

: "${BASIC_ENV_DRY_RUN:=0}"
: "${BASIC_ENV_REPLACE_CONFIGS:=0}"
case ${BASH_SOURCE[0]} in
    */*) basic_env_lib_dir=${BASH_SOURCE[0]%/*} ;;
    *)   basic_env_lib_dir=. ;;
esac
: "${BASIC_ENV_REPO_ROOT:=$(cd -- "$basic_env_lib_dir/.." >/dev/null 2>&1 && pwd -P)}"

be_die() { printf 'basic-env: %s\n' "$*" >&2; exit 1; }
be_note() { printf 'basic-env: %s\n' "$*"; }

# be_run CMD... - execute, or just print under --dry-run.
be_run() {
    if [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
        printf '[dry-run]'; printf ' %q' "$@"; printf '\n'
        return 0
    fi
    "$@"
}

# be_parse_args "$@" - honour --dry-run/--replace-configs/--help on stage
# scripts too; anything else is an error.
be_parse_args() {
    local arg
    for arg in "$@"; do
        case $arg in
            --dry-run)         BASIC_ENV_DRY_RUN=1 ;;
            --replace-configs) BASIC_ENV_REPLACE_CONFIGS=1 ;;
            -h|--help)
                printf 'usage: %s [--dry-run] [--replace-configs]\n' "${0##*/}"
                exit 0
                ;;
            *)
                printf 'basic-env: unknown argument %s\n' "$arg" >&2
                exit 2
                ;;
        esac
    done
}

# be_file_status SRC DST -> absent|identical|different|symlink|dangling-symlink|not-a-regular-file
be_file_status() {
    local src=$1 dst=$2
    if [ -L "$dst" ]; then
        if [ -e "$dst" ]; then printf 'symlink'; else printf 'dangling-symlink'; fi
    elif [ ! -e "$dst" ]; then
        printf 'absent'
    elif [ ! -f "$dst" ]; then
        printf 'not-a-regular-file'
    elif cmp -s -- "$src" "$dst"; then
        printf 'identical'
    else
        printf 'different'
    fi
}

# be_preflight SRC DST -> 0 if installable, 1 (with message) on conflict.
be_preflight() {
    local status
    status=$(be_file_status "$1" "$2")
    case $status in
        absent|identical) return 0 ;;
        different)
            [ "$BASIC_ENV_REPLACE_CONFIGS" = "1" ] && return 0
            printf 'basic-env: conflict: %s exists and differs (use --replace-configs to back up and overwrite)\n' "$2" >&2
            return 1
            ;;
        *)
            printf 'basic-env: conflict: %s is %s; refusing\n' "$2" "$status" >&2
            return 1
            ;;
    esac
}

# be_backup FILE - copy FILE into a fresh private backup dir (0700 dir,
# 0600 file) under ~/.local/state/basic-env/backups/ and print the dir.
be_backup() {
    local file=$1 base dir
    base=$HOME/.local/state/basic-env/backups
    dir=$base/$(date +%Y%m%d-%H%M%S)-$$
    mkdir -p -- "$dir" || return 1
    chmod 700 "$base" "$dir" 2>/dev/null || return 1
    cp -p -- "$file" "$dir/" || return 1
    chmod 600 "$dir/${file##*/}" || return 1
    printf '%s\n' "$dir"
}

# be_install_file SRC DST - copy with skip-if-identical / refuse-or-backup-
# and-replace semantics. Preflight first when installing several files.
be_install_file() {
    local src=$1 dst=$2 status bdir
    status=$(be_file_status "$src" "$dst")
    case $status in
        identical) be_note "unchanged: $dst"; return 0 ;;
        absent|different) ;;
        *) be_die "refusing to install over $status target $dst" ;;
    esac
    if [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
        if [ "$status" = different ]; then
            printf '[dry-run] would back up and replace %s with %s\n' "$dst" "$src"
        else
            printf '[dry-run] would install %s -> %s\n' "$src" "$dst"
        fi
        return 0
    fi
    mkdir -p -- "${dst%/*}" || be_die "cannot create ${dst%/*}"
    if [ "$status" = different ]; then
        bdir=$(be_backup "$dst") || be_die "backup failed for $dst"
        be_note "backed up $dst -> $bdir"
    fi
    cp -- "$src" "$dst" || be_die "failed to install $dst"
    be_note "installed $dst"
}
