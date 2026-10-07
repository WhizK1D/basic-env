#!/bin/bash
# Stage: install - apt packages, Pathogen, and vim plugins under ~/.vim.
# Network and sudo happen only here; nothing in this stage touches configs.
set -euo pipefail

case ${BASH_SOURCE[0]} in
    */*) basic_env_script_dir=${BASH_SOURCE[0]%/*} ;;
    *)   basic_env_script_dir=. ;;
esac
basic_env_script_dir="$(cd -- "$basic_env_script_dir" >/dev/null 2>&1 && pwd -P)"
. "$basic_env_script_dir/lib-basic-env.sh"
be_parse_args "$@"

# --- apt packages -----------------------------------------------------------
# Packages we want; each is skipped when its command already exists.
# bat is satisfied by either the bat or batcat binary name; universal-ctags
# only by a ctags that actually identifies as Universal Ctags.
basic_env_packages='git curl vim terminator eza bat universal-ctags'

basic_env_pkg_commands() {
    case $1 in
        git)             printf 'git\n' ;;
        curl)            printf 'curl\n' ;;
        vim)             printf 'vim\n' ;;
        terminator)      printf 'terminator\n' ;;
        eza)             printf 'eza\n' ;;
        bat)             printf 'bat batcat\n' ;;
        universal-ctags) printf 'ctags\n' ;;
        *)               return 1 ;;
    esac
}

basic_env_pkg_satisfied() {
    local cmd found=0
    for cmd in $(basic_env_pkg_commands "$1"); do
        if type -P "$cmd" >/dev/null 2>&1; then
            found=1
            break
        fi
    done
    [ "$found" -eq 0 ] && return 1
    if [ "$1" = universal-ctags ]; then
        # An installed ctags is not enough: it must be Universal Ctags,
        # not Exuberant/BSD or some other implementation.
        LC_ALL=C ctags --version 2>/dev/null | grep -q 'Universal Ctags'
    fi
}

missing=()
for pkg in $basic_env_packages; do
    if basic_env_pkg_satisfied "$pkg"; then
        be_note "present: $pkg"
        continue
    fi
    if ! type -P apt-cache >/dev/null 2>&1 || ! type -P apt-get >/dev/null 2>&1; then
        be_die "missing '$pkg' and this system has no apt-get/apt-cache; install it manually"
    fi
    candidate=$(LC_ALL=C apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/ {print $2; exit}')
    if [ -z "$candidate" ] || [ "$candidate" = "(none)" ]; then
        be_die "no apt installation candidate for '$pkg'; enable the repository that provides it or install it manually"
    fi
    missing+=("$pkg")
done

if [ "${#missing[@]}" -gt 0 ]; then
    be_note "installing: ${missing[*]}"
    # Interactive apt confirmation; sudo only when not already root.
    if [ "$EUID" -eq 0 ]; then
        be_run apt-get install "${missing[@]}" || be_die "apt-get install failed"
    else
        be_run sudo apt-get install "${missing[@]}" || be_die "apt-get install failed"
    fi
fi

# --- Pathogen ---------------------------------------------------------------
pathogen_url='https://raw.githubusercontent.com/tpope/vim-pathogen/master/autoload/pathogen.vim'
pathogen_dst=$HOME/.vim/autoload/pathogen.vim
if [ -L "$pathogen_dst" ]; then
    be_die "conflict: $pathogen_dst is a symlink; refusing"
elif [ -e "$pathogen_dst" ] && [ ! -f "$pathogen_dst" ]; then
    be_die "conflict: $pathogen_dst exists but is not a regular file"
elif [ -f "$pathogen_dst" ]; then
    be_note "Pathogen already present: $pathogen_dst"
elif [ "$BASIC_ENV_DRY_RUN" = "1" ]; then
    printf '[dry-run] would download %s -> %s\n' "$pathogen_url" "$pathogen_dst"
else
    mkdir -p -- "${pathogen_dst%/*}" || be_die "cannot create ${pathogen_dst%/*}"
    pathogen_tmp=$(mktemp) || be_die "mktemp failed"
    if curl --fail --location -o "$pathogen_tmp" "$pathogen_url"; then
        mv -- "$pathogen_tmp" "$pathogen_dst"
        be_note "installed Pathogen -> $pathogen_dst"
    else
        rm -f -- "$pathogen_tmp"
        be_die "Pathogen download failed"
    fi
fi

# --- vim plugins -------------------------------------------------------------
# vim_plugin_list rows: Name,url[,pinned-commit]. Target dir is the URL
# basename minus any .git suffix. Existing real git checkouts (including
# linked worktrees, whose .git is a file) are left alone with no pull/reset;
# anything else occupying the path is a hard error.
bundle_dir=$HOME/.vim/bundle

# A directory is a real checkout only if it has its own .git entry AND git
# agrees the work-tree top level is exactly that directory (a plain subdir
# of some parent repo must not masquerade as an installed plugin).
basic_env_is_checkout() {
    local target=$1 top
    [ -e "$target/.git" ] || return 1
    top=$(git -C "$target" rev-parse --show-toplevel 2>/dev/null) || return 1
    [ "$top" = "$target" ]
}

while IFS=, read -r plugin_name plugin_url plugin_pin || [ -n "$plugin_name" ]; do
    case $plugin_name in ''|'#'*) continue ;; esac
    plugin_base=${plugin_url##*/}
    plugin_base=${plugin_base%.git}
    plugin_target=$bundle_dir/$plugin_base
    if [ -L "$plugin_target" ]; then
        be_die "conflict: $plugin_target is a symlink; refusing"
    elif basic_env_is_checkout "$plugin_target"; then
        be_note "plugin already cloned: $plugin_target"
    elif [ -e "$plugin_target" ]; then
        be_die "conflict: $plugin_target exists but is not a git checkout"
    else
        be_run mkdir -p -- "$bundle_dir"
        be_run git clone "$plugin_url" "$plugin_target" \
            || be_die "clone failed for $plugin_name ($plugin_url)"
        if [ -n "${plugin_pin:-}" ]; then
            be_run git -C "$plugin_target" checkout "$plugin_pin" \
                || be_die "pin checkout failed for $plugin_name ($plugin_pin)"
        fi
    fi
    # Helptags in a vim that never reads the user's vimrc, plugins or
    # viminfo. Docs are best-effort: failure must not abort the install.
    if [ "$BASIC_ENV_DRY_RUN" != "1" ] && [ -d "$plugin_target/doc" ]; then
        BASIC_ENV_PLUGIN_DOC="$plugin_target/doc" \
            vim --noplugin -Nu NONE -n -es -i NONE \
                -c 'execute "helptags " . fnameescape($BASIC_ENV_PLUGIN_DOC)' \
                -c 'qa!' </dev/null >/dev/null 2>&1 \
            || printf 'basic-env: warning: helptags failed for %s\n' "$plugin_base" >&2
    fi
done < "$BASIC_ENV_REPO_ROOT/vim_plugin_list"
