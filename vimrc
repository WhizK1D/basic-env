execute pathogen#infect()
syntax on
filetype plugin indent on

set hlsearch
set whichwrap+=<,>,[,]
set number
set exrc
set secure
set encoding=utf-8

nnoremap <F3> :NumbersToggle<CR>
nnoremap <F4> :NumbersOnOff<CR>

nnoremap <F8> :TagbarToggle<CR>
nnoremap <F7> :NERDTreeTabsToggle<CR>

set statusline+=%#warningmsg#
set statusline+=%{SyntasticStatuslineFlag()}
set statusline+=%*
let g:syntastic_always_populate_loc_list = 1
let g:syntastic_auto_loc_list = 1
let g:syntastic_check_on_open = 1
let g:syntastic_check_on_wq = 0

nnoremap <C-Left> :tabprevious<CR>
nnoremap <C-Right> :tabnext<CR>

let g:ctrlp_map = '<c-p>'
let g:crlp_cmd = "CtrlP"
let g:ctrlp_working_path_mode = 'ra'
nnoremap <space> za

"Octave syntax

augroup filetypedetect
	au! BufRead,BufNewFile *.m,*.oct set filetype=octave
augroup END

"C/C++ doxygen highlighting

augroup project
    autocmd!
    autocmd BufRead,BufNewFile *.h,*.c set filetype=c.doxygen
augroup END

"Soft tabs of width 4
set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab

set colorcolumn=120
highlight ColorColumn ctermbg=darkgray
