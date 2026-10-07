# basic-env

Personal Debian/Ubuntu environment bootstrap: a small modular installer
for a bash shell setup, a curated Vim plugin set, shared git aliases and
a Terminator profile.

## Getting started

Run as your normal user (apt uses sudo internally only when needed):

    ./setup_environment.sh all --dry-run   # preview; changes nothing
    ./setup_environment.sh all             # then install for real

Then open a fresh terminal. The `install` stage apt-installs `git`,
`curl`, `vim`, `terminator`, `eza`, `bat` and `universal-ctags` (missing
ones only), then installs Pathogen and the `vim_plugin_list` plugins; no
third-party apt repositories are added.

## Stages

Each stage can run on its own; `all` runs the three in order:

    ./setup_environment.sh install     # apt packages, Pathogen, plugins
    ./setup_environment.sh shell       # ~/.env modules + ~/.bashrc hook
    ./setup_environment.sh configure   # vimrc, terminator, git include

No arguments prints help and changes nothing; `--dry-run` previews any stage.

## Customization

The visible sources under `shell/` install as dotfiles in `~/.env`
(`setup` -> `.setup`, `colors` -> `.colors`, `aliases` -> `.aliases`,
`prompt` -> `.prompt`). `.setup` is the sole entry point sourced from
`~/.bashrc`; machine-local overrides go in optional `~/.env/.local`.
Secrets belong in `~/.env/.keys` outside git: the installer creates it
empty mode 0600 only when absent, never touching an existing one; the
committed `shell/keys.example` stays empty.

## Important behavior

Installs are idempotent: existing plugin checkouts are skipped (no
auto-pull/reset) and identical configs are left alone. A differing file
is refused unless `--replace-configs` backs it up under
`~/.local/state/basic-env/backups/`; symlinked managed files are always
refused. `configure` installs an identity-free gitconfig snippet to
`~/.config/basic-env/gitconfig` plus one `include.path` in `~/.gitconfig`;
your `[user]` name/email, signing and existing includes are preserved.

## Everyday use

| Command            | What it does                                       |
|--------------------|----------------------------------------------------|
| `ls` `l` `la` `ll` | eza when installed, otherwise plain `ls`           |
| `cat`              | `batcat`/`bat`, no pager; `dcat` is real `cat`     |
| `gva [n]`          | git history graph, default 5 entries               |
| `gp [branch]`      | `git push origin HEAD:<branch>` (default: `master`)|
| `sin <pkg>...`     | `sudo apt-get install` (interactive)               |
| `extract <file>`   | unpack a tar/zip/... archive                       |

## References

- [Vim quickstart](docs/vim-quickstart.md): key bindings and plugin usage
- Regression tests (stdlib only; apt, curl, sudo and clone are stubbed):

      python3 -m unittest discover -s tests -v
