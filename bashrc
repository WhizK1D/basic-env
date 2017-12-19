alias v="vim -c \"colorscheme 256-grayvim\""
alias c="clear"
alias d="cd ~/Desktop/"
alias g="git"
alias l="ls"
alias la="ls -a"
alias ll="ls -l"

gva()
{
	if [ $# -eq 0 ]; then
		git view --all -n 5
	else
		# Call git view with no of arguments as input
		git view --all -n $1
	fi
}
