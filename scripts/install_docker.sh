#!/bin/bash
# =============================================================
# install_docker.sh
# Script d'installation de Docker et Docker Compose
# Compatible Ubuntu et Debian
# =============================================================
set -e

echo "=========================================="
echo " SecuByDesign - Installation de Docker"
echo "=========================================="
echo ""

# ------ Detecter l'OS ------
if [ ! -f /etc/os-release ]; then
    echo "ERREUR: Impossible de detecter l'OS (/etc/os-release manquant)."
    exit 1
fi

. /etc/os-release
OS_ID="$ID"

if [ "$OS_ID" != "ubuntu" ] && [ "$OS_ID" != "debian" ]; then
    echo "ERREUR: Ce script supporte uniquement Ubuntu et Debian."
    echo "OS detecte: $PRETTY_NAME ($OS_ID)"
    exit 1
fi

echo "[*] OS detecte: $PRETTY_NAME"
echo ""

# ------ Supprimer les anciennes versions ------
echo "[1/6] Suppression des anciennes versions de Docker..."
sudo apt-get remove -y \
    docker docker-engine docker.io containerd runc 2>/dev/null || true

# ------ Installer les prerequis ------
echo "[2/6] Installation des prerequis..."
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg

# ------ Ajouter la cle GPG Docker ------
echo "[3/6] Ajout de la cle GPG Docker..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# ------ Ajouter le depot Docker ------
echo "[4/6] Ajout du depot Docker..."
echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$OS_ID \
    $VERSION_CODENAME stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# ------ Installer Docker Engine + Compose ------
echo "[5/6] Installation de Docker Engine et Docker Compose..."
sudo apt-get update
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# ------ Configurer les permissions ------
echo "[6/6] Configuration des permissions..."
sudo usermod -aG docker "$USER"

sudo systemctl enable docker
sudo systemctl start docker

echo ""
echo "=========================================="
echo " Installation terminee avec succes !"
echo "=========================================="
echo ""
echo " Docker version   : $(docker --version)"
echo " Compose version  : $(docker compose version)"
echo ""
echo " IMPORTANT: Deconnectez-vous puis reconnectez-vous"
echo " pour que les permissions Docker prennent effet,"
echo " ou executez la commande : newgrp docker"
echo ""
echo "=========================================="
