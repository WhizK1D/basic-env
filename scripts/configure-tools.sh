#!/bin/bash
# Stage: configure - copy vimrc and the terminator config, install the
# shared gitconfig snippet and add exactly one include.path for it in
# ~/.gitconfig. No network, no package installs.
set -euo pipefail

case ${BASH_SOURCE[0]} in
    */*) basic_env_script_dir=${BASH_SOURCE[0]%/*} ;;
    *)   basic_env_script_dir=. ;;
esac
basic_env_script_dir="$(cd -- "$basic_env_script_dir" >/dev/null 2>&1 && pwd -P)"
. "$basic_env_script_dir/lib-basic-env.sh"
be_parse_args "$@"

vimrc_dst=$HOME/.vimrc
terminator_dst=$HOME/.config/terminator/config
git_snippet_dst=$HOME/.config/basic-env/gitconfig
gitconfig=$HOME/.gitconfig

# Emit the snippet to install: the repo gitconfig minus its [user]
# section (the section header and its entries/comments up to the next
# section). The repo file keeps its original identity; only the
# installed include is identity-free so it can never override the
# machine's own [user] settings. Read-only; prints to stdout.
basic_env_git_snippet() {
    awk '/^[[:space:]]*\[/ { skip = (tolower($0) ~ /^[[:space:]]*\[user([[:space:]]|\])/); }
         !skip { print }' "$BASIC_ENV_REPO_ROOT/gitconfig"
}

git_available=1
type -P git >/dev/null 2>&1 || git_available=0

# Preflight all targets before writing anything. Git is required for the
# include step: a real run with no git fails here, before any file is
# copied; --dry-run may proceed and just print the intended git action.
conflicts=0
be_preflight "$BASIC_ENV_REPO_ROOT/vimrc" "$vimrc_dst" || conflicts=1
be_preflight "$BASIC_ENV_REPO_ROOT/terminator-config" "$terminator_dst" || conflicts=1
# Fresh stream per comparison: process substitutions are single-use.
be_preflight <(basic_env_git_snippet) "$git_snippet_dst" || conflicts=1
if [ -L "$gitconfig" ]; then
    printf 'basic-env: conflict: %s is a symlink; refusing\n' "$gitconfig" >&2
    conflicts=1
elif [ -e "$gitconfig" ] && [ ! -f "$gitconfig" ]; then
    printf 'basic-env: conflict: %s is not a regular file\n' "$gitconfig" >&2
    conflicts=1
elif [ -f "$gitconfig" ] && [ "$git_available" -eq 1 ]; then
    # Existing file must parse as git config before we touch anything.
    if ! git config --file "$gitconfig" --list >/dev/null 2>&1; then
        printf 'basic-env: conflict: %s is not a parseable git config; refusing\n' "$gitconfig" >&2
        conflicts=1
    fi
fi
if [ "$git_available" -eq 0 ] && [ "$BASIC_ENV_DRY_RUN" != "1" ]; then
    printf 'basic-env: conflict: git is required to update %s\n' "$gitconfig" >&2
    conflicts=1
fi
[ "$conflicts" -ne 0 ] && be_die "preflight conflicts found; nothing was changed"

be_install_file "$BASIC_ENV_REPO_ROOT/vimrc" "$vimrc_dst"
be_install_file "$BASIC_ENV_REPO_ROOT/terminator-config" "$terminator_dst"

# The snippet is generated (identity-free), so compare against a fresh
# stream and materialize to a private temp outside the checkout for a
# real install. --dry-run prints intent only; no temp is created.
snippet_status=$(be_file_status <(basic_env_git_snippet) "$git_snippet_dst")
snippet_tmp=
case $snippet_status in
    identical)
        be_note "unchanged: $git_snippet_dst" ;;
    *)
        if [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
            if [ "$snippet_status" = different ]; then
                printf '[dry-run] would back up and replace %s with the generated identity-free snippet\n' "$git_snippet_dst"
            else
                printf '[dry-run] would install the generated identity-free snippet -> %s\n' "$git_snippet_dst"
            fi
        else
            snippet_tmp=$(mktemp) || be_die "mktemp failed for gitconfig snippet"
            trap 'rm -f -- "$snippet_tmp"' EXIT
            chmod 600 "$snippet_tmp"
            basic_env_git_snippet > "$snippet_tmp"                 || be_die "failed to generate gitconfig snippet"
            be_install_file "$snippet_tmp" "$git_snippet_dst"
            rm -f -- "$snippet_tmp"
            snippet_tmp=
            trap - EXIT
        fi ;;
esac

# Add one include.path for the shared snippet, addressed explicitly at
# ~/.gitconfig (--file) so GIT_CONFIG_GLOBAL/XDG selection can never redirect
# the write to an un-preflighted file. --path reads expand a tilde-written
# identical entry so repeats stay idempotent. --add appends: existing
# identity, signing config and other includes are preserved.
include_present=0
if [ "$git_available" -eq 1 ] && [ -f "$gitconfig" ]; then
    if git config --file "$gitconfig" --path --get-all include.path 2>/dev/null \
        | grep -qxF "$git_snippet_dst"; then
        include_present=1
    fi
fi
if [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
    if [ "$include_present" -eq 1 ]; then
        be_note "include.path for $git_snippet_dst already present in $gitconfig"
    else
        printf '[dry-run] would add include.path %s to %s\n' "$git_snippet_dst" "$gitconfig"
    fi
elif [ "$include_present" -eq 1 ]; then
    be_note "unchanged: include.path for $git_snippet_dst already in $gitconfig"
else
    if [ -f "$gitconfig" ]; then
        bdir=$(be_backup "$gitconfig") || be_die "backup failed for $gitconfig"
        be_note "backed up $gitconfig -> $bdir"
    fi
    git config --file "$gitconfig" --add include.path "$git_snippet_dst" \
        || be_die "failed to add include.path to $gitconfig"
    be_note "added include.path $git_snippet_dst to $gitconfig"
fi
