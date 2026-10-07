# Vim quickstart

Cheat sheet for the plugins and mappings set up by `./setup_environment.sh all`
(see `vim_plugin_list` and `vimrc`). All mappings are normal-mode unless noted; the
plugin leader is the default `\`.

## File tree - NERDTree (+ tabs)

- `F7` toggles the tree across all tabs (`:NERDTreeTabsToggle`)
- inside the tree: `o` open/toggle a node, `i` open in a horizontal
  split, `s` vertical split, `t` new tab; `j`/`k` move; `Ctrl-w w`
  switches windows

## Symbols - Tagbar

- `F8` toggles the symbol sidebar (`:TagbarToggle`); `Enter` jumps to a
  symbol
- requires Universal Ctags (installed by the install stage)

## Finder - CtrlP

- `Ctrl-p` opens the finder; type to filter
- `Ctrl-j`/`Ctrl-k` move, `Enter` opens, `Ctrl-x` horizontal split,
  `Ctrl-v` vertical split, `Ctrl-t` opens in a tab

## Line numbers - numbers.vim

- `F3` toggles relative/absolute; `F4` toggles the plugin on/off

## Tabs and folds

- `Ctrl-Left` / `Ctrl-Right` previous/next Vim tab
- `Space` toggles the fold under the cursor (`za`)

## Comments - NERDCommenter

- `\cc` comment, `\cu` uncomment, `\c<Space>` toggle
- works on the current line or a visual selection

## Editing helpers

- SuperTab: `Tab`/`Shift-Tab` cycle insert-mode completion
- AutoPairs: automatic matching brackets/quotes, no setup needed
- Airline: the statusline appears automatically

## Bookmarks - vim-bookmarks

- `mm` toggles a bookmark, `mn`/`mp` next/previous, `ma` lists all,
  `mi` adds an annotation (optional)

## Git - Fugitive

- `:Git` status interface, `:Git blame`, `:Gdiffsplit` for diffs
- staging, committing and other write actions change the repo; use them deliberately

## Linting - Syntastic

- `:SyntasticCheck` runs the checkers, `:Errors` lists results
- language checkers (flake8, eslint, ...) are separate executables;
  install the ones you need

## FuzzyFinder (optional)

- `:FufFile`, `:FufBuffer`, `:FufMruFile`
- L9 is its Vimscript library dependency (installed by the plugin
  stage), not a system binary

## More help

`:help NERDTree` / `:help ctrlp` / `:help tagbar` / `:help syntastic`
