#!/bin/bash

echo "Instalando dependencias nativas do sistema..."
sudo pacman -S --needed python lsof python-gobject libappindicator-gtk3 libayatana-appindicator

echo "Criando Ambiente Virtual..."
python3 -m venv venv
sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' venv/pyvenv.cfg

echo "Instalando dependencias do Python..."
./venv/bin/pip install -r requirements.txt

echo "Criando atalho no menu..."
mkdir -p ~/.local/share/applications
cat <<APP > ~/.local/share/applications/gw2rpc.desktop
[Desktop Entry]
Name=GW2 RPC
Comment=Discord Rich Presence for Guild Wars 2
Exec=/home/porco/GW2RPC_fork/venv/bin/python /home/porco/GW2RPC_fork/run.py
Icon=/home/porco/GW2RPC_fork/icon.png
Terminal=false
Type=Application
Categories=Game;Utility;
APP
update-desktop-database ~/.local/share/applications

echo "Instalacao finalizada com sucesso!"
