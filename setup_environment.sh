#!/bin/bash

export REPO_ROOT=$(pwd)

setup_vim_plugins()
{

    for plugin in `cat vim_plugin_list`; do
        plugin_name=`echo $plugin | awk -F',' '{print $1}'`;
        plugin_URL=`echo $plugin | awk -F',' '{print $2}'`;
        echo "Installing $plugin_name from $plugin_URL"
        cd ~/.vim/bundle
        git clone $plugin_URL
        cd $REPO_ROOT
    done

}

setup_vimrc()
{
    cp $REPO_ROOT/vimrc ~/.vimrc
}

setup_local_git_config()
{
    cp $REPO_ROOT/gitconfig ~/.gitconfig
}

configure_bashrc()
{
    cat bashrc >> ~/.bashrc
}

install_pathogen()
{
    mkdir -p ~/.vim/autoload ~/.vim/bundle && \
    curl -LSso ~/.vim/autoload/pathogen.vim https://tpo.pe/pathogen.vim
}

install_vim()
{
    sudo apt-get install vim
}

which vim
 if [ $? -ne 0 ]; then
     echo "vim not found installed on the system! Installing vim...\nsudo password maybe required"
     install_vim
 else
     echo "vim found installed, continuing..."
 fi

echo "Setting up Pathogen plugin manager for vim"
install_pathogen

echo "Setting up .vimrc"
setup_vimrc

echo "Setting up vim plugins"
setup_vim_plugins

echo "Setting up .gitconfig"
echo "WARNING: Your current local config will be over-written! Press Ctrl-C to quit this script here"
read
setup_local_git_config

echo "Configuring bash aliases"
configure_bashrc
