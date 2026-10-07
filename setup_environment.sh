#!/bin/bash
# basic-env setup orchestrator.
#
# With no arguments this prints help and changes nothing. Stages run in
# canonical order (install -> shell -> configure) no matter what order they
# are given in. Unknown options or stage names are an error.
set -euo pipefail

case ${BASH_SOURCE[0]} in
    */*) basic_env_self_dir=${BASH_SOURCE[0]%/*} ;;
    *)   basic_env_self_dir=. ;;
esac
BASIC_ENV_REPO_ROOT="$(cd -- "$basic_env_self_dir" >/dev/null 2>&1 && pwd -P)"
export BASIC_ENV_REPO_ROOT
export BASIC_ENV_DRY_RUN=0
export BASIC_ENV_REPLACE_CONFIGS=0

usage() {
    cat <<'EOF'
Usage: setup_environment.sh [--dry-run] [--replace-configs] <stage> [<stage>...]

Stages:
  install     Install apt packages, Pathogen, and vim plugins
              (uses the network and sudo for apt)
  shell       Install shell modules to ~/.env and wire the ~/.bashrc import
  configure   Install vimrc, terminator config and the git include
  all         All of the above, in order

Options:
  --dry-run          Print intended actions without changing anything
  --replace-configs  Back up and replace differing config files instead of
                     refusing them (backups: ~/.local/state/basic-env/backups/)
  -h, --help         Show this help
EOF
}

want_install=0
want_shell=0
want_configure=0

for arg in "$@"; do
    case $arg in
        install)           want_install=1 ;;
        shell)             want_shell=1 ;;
        configure)         want_configure=1 ;;
        all)               want_install=1; want_shell=1; want_configure=1 ;;
        --dry-run)         BASIC_ENV_DRY_RUN=1 ;;
        --replace-configs) BASIC_ENV_REPLACE_CONFIGS=1 ;;
        -h|--help)         usage; exit 0 ;;
        *)
            printf 'setup_environment: unknown argument %s\n\n' "$arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$want_install" -eq 0 ] && [ "$want_shell" -eq 0 ] && [ "$want_configure" -eq 0 ]; then
    usage
    exit 0
fi

# Canonical order; set -e stops the run at the first stage failure.
if [ "$want_install" -eq 1 ]; then
    "$BASIC_ENV_REPO_ROOT/scripts/install-tools.sh"
fi
if [ "$want_shell" -eq 1 ]; then
    "$BASIC_ENV_REPO_ROOT/scripts/setup-shell.sh"
fi
if [ "$want_configure" -eq 1 ]; then
    "$BASIC_ENV_REPO_ROOT/scripts/configure-tools.sh"
fi
