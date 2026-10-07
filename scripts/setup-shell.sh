#!/bin/bash
# Stage: shell - copy the shell modules to ~/.env and wire the basic-env
# import block into ~/.bashrc. Creates an empty ~/.env/.keys (0600) only
# when completely absent; existing .keys/.local are never touched.
set -euo pipefail

case ${BASH_SOURCE[0]} in
    */*) basic_env_script_dir=${BASH_SOURCE[0]%/*} ;;
    *)   basic_env_script_dir=. ;;
esac
basic_env_script_dir="$(cd -- "$basic_env_script_dir" >/dev/null 2>&1 && pwd -P)"
. "$basic_env_script_dir/lib-basic-env.sh"
be_parse_args "$@"

envdir=$HOME/.env
# Public sources carry plain names; they are installed under ~/.env as the
# dotfiles that .setup loads at runtime.
modules=(setup colors aliases prompt)
bashrc=$HOME/.bashrc

block_begin='# >>> basic-env >>>'
block_end='# <<< basic-env <<<'

# Print clean|none|malformed. Only exact full-line markers count; anything
# marker-like but inexact, unbalanced, nested or stray is malformed.
basic_env_bashrc_state() {
    awk -v begin="$block_begin" -v end="$block_end" '
        $0 == begin { if (inside) bad=1; begins++; inside=1; next }
        $0 == end   { if (!inside) bad=1; inside=0; ends++; next }
        index($0, ">>> basic-env") || index($0, "basic-env >>>") ||
        index($0, "<<< basic-env") || index($0, "basic-env <<<") { bad=1 }
        END {
            if (inside) bad=1
            if (bad) print "malformed"
            else if (begins) print "clean"
            else print "none"
        }
    ' "$1"
}

bashrc_state=none
if [ -L "$bashrc" ]; then
    bashrc_state=symlink
elif [ -e "$bashrc" ] && [ ! -f "$bashrc" ]; then
    bashrc_state=notfile
elif [ -f "$bashrc" ]; then
    bashrc_state=$(basic_env_bashrc_state "$bashrc")
fi

# Preflight every target before writing anything so conflicts never leave a
# partially deployed shell setup behind.
conflicts=0
for module in "${modules[@]}"; do
    be_preflight "$BASIC_ENV_REPO_ROOT/shell/$module" "$envdir/.$module" || conflicts=1
done
case $bashrc_state in
    clean|none) ;;
    malformed)
        printf 'basic-env: conflict: %s has malformed basic-env markers; refusing\n' "$bashrc" >&2
        conflicts=1 ;;
    symlink)
        printf 'basic-env: conflict: %s is a symlink; refusing\n' "$bashrc" >&2
        conflicts=1 ;;
    notfile)
        printf 'basic-env: conflict: %s is not a regular file\n' "$bashrc" >&2
        conflicts=1 ;;
esac
[ "$conflicts" -ne 0 ] && be_die "preflight conflicts found; nothing was changed"

for module in "${modules[@]}"; do
    be_install_file "$BASIC_ENV_REPO_ROOT/shell/$module" "$envdir/.$module"
done

# ~/.env/.keys holds machine-local secrets and lives outside this repo.
# Only ever created when absent; never read, copied, chmodded or replaced.
# noclobber guards against a file appearing between check and create.
keysfile=$envdir/.keys
if [ -e "$keysfile" ] || [ -L "$keysfile" ]; then
    be_note "leaving existing $keysfile untouched"
elif [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
    printf '[dry-run] would create empty %s (mode 0600)\n' "$keysfile"
else
    mkdir -p -- "$envdir" || be_die "cannot create $envdir"
    (umask 077; set -o noclobber; : > "$keysfile") \
        || be_die "cannot create $keysfile (appeared or not writable)"
    be_note "created empty $keysfile (mode 0600)"
fi

# --- ~/.bashrc import block -------------------------------------------------

# Build the candidate bashrc: content outside markers preserved verbatim, a
# missing trailing newline is separated, stale/duplicate marked blocks
# collapse, and a file with no markers gets the block appended. Prints the
# temp path (created next to DST so a later mv is atomic). Caller must
# ensure markers, if present, are well-formed (bashrc_state clean|none).
basic_env_build_bashrc() {
    local dst=$1 tmp
    tmp=$(mktemp "$dst.XXXXXXXX") || return 1
    awk -v begin="$block_begin" -v end="$block_end" '
        function emit_block() {
            print begin
            print "# Source the basic-env shell modules if installed."
            print "if [ -f \"$HOME/.env/.setup\" ]; then"
            print "    . \"$HOME/.env/.setup\""
            print "fi"
            print end
        }
        $0 == begin { if (!emitted) { emit_block(); emitted=1 }; inside=1; next }
        inside && $0 == end { inside=0; next }
        inside { next }
        { print }
        END { if (!emitted) emit_block() }
    ' "$dst" > "$tmp" || { rm -f -- "$tmp"; return 1; }
    printf '%s\n' "$tmp"
}

# Decide what to do with ~/.bashrc: create | reuse | append | rewrite
bashrc_action=create
if [ "$bashrc_state" = clean ]; then
    bashrc_action=rewrite
elif [ "$bashrc_state" = none ] && [ -f "$bashrc" ]; then
    if grep -qE '^[[:space:]]*(\.|source)[[:space:]]+.*\.env/\.setup' "$bashrc" 2>/dev/null; then
        bashrc_action=reuse
    else
        bashrc_action=append
    fi
fi

if [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
    case $bashrc_action in
        create)  printf '[dry-run] would create %s with the basic-env import block\n' "$bashrc" ;;
        reuse)   be_note "reusing existing .env/.setup source hook in $bashrc" ;;
        append)  printf '[dry-run] would append the basic-env import block to %s\n' "$bashrc" ;;
        rewrite) printf '[dry-run] would refresh the basic-env import block in %s\n' "$bashrc" ;;
    esac
else
    case $bashrc_action in
        create)
            printf '# >>> basic-env >>>\n# Source the basic-env shell modules if installed.\nif [ -f "$HOME/.env/.setup" ]; then\n    . "$HOME/.env/.setup"\nfi\n# <<< basic-env <<<\n' \
                > "$bashrc" || be_die "cannot write $bashrc"
            be_note "created $bashrc with the basic-env import block"
            ;;
        reuse)
            be_note "reusing existing .env/.setup source hook in $bashrc"
            ;;
        append|rewrite)
            candidate=$(basic_env_build_bashrc "$bashrc") \
                || be_die "failed to build new $bashrc"
            if cmp -s -- "$candidate" "$bashrc"; then
                rm -f -- "$candidate"
                be_note "unchanged: $bashrc already has the import block"
            else
                # Back up before the real content change, then swap atomically.
                bdir=$(be_backup "$bashrc") \
                    || { rm -f -- "$candidate"; be_die "backup failed for $bashrc"; }
                chmod --reference="$bashrc" "$candidate" 2>/dev/null
                mv -- "$candidate" "$bashrc" \
                    || be_die "failed to update $bashrc"
                be_note "updated the basic-env import block in $bashrc (backup: $bdir)"
            fi
            ;;
    esac
fi
