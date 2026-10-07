# ~/.bashrc: executed by bash(1) for non-login shells.
# Minimal bootstrap: the distro defaults live in /etc/skel/.bashrc; this file
# only wires in the modular basic-env setup under ~/.env.

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# Source the basic-env shell modules (colors, aliases, prompt, optional local
# keys and machine-local overrides) if they are installed.
if [ -f "$HOME/.env/.setup" ]; then
    . "$HOME/.env/.setup"
fi
