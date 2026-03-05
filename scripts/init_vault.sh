#!/bin/sh
# =============================================================
# init_vault.sh
# Script d'injection des parametres de connexion DB et des
# secrets applicatifs dans HashiCorp Vault
#
# Utilise par :
#   - Le service docker-compose 'vault-init' (automatiquement)
#   - Ou manuellement : ./scripts/init_vault.sh
#
# Variables d'environnement utilisees (avec valeurs par defaut) :
#   VAULT_ADDR, VAULT_TOKEN,
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
#   APP_PEPPER, APP_SECRET_KEY
# =============================================================
set -e

echo "=========================================="
echo " SecuByDesign - Initialisation de Vault"
echo "=========================================="

# ------ Variables avec valeurs par defaut ------
VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-myroot}"

DB_HOST="${DB_HOST:-mariadb}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-secubydesign}"
DB_USER="${DB_USER:-secuby}"
DB_PASSWORD="${DB_PASSWORD:-Sec7By9Des!gn@2024#Xk3}"

APP_PEPPER="${APP_PEPPER:-X9kPz2mQvR7wYjN4uFhB3sLp8dE6cT1a}"
APP_SECRET_KEY="${APP_SECRET_KEY:-FlaskSuperSecretKey2024SecuByDesign!}"

export VAULT_ADDR
export VAULT_TOKEN

echo "[*] Vault address: $VAULT_ADDR"
echo ""

# ------ Attendre que Vault soit pret ------
echo "[1/3] Attente de Vault..."
MAX_RETRIES=30
RETRY=0
until vault status > /dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        echo "ERREUR: Vault n'est pas disponible apres $MAX_RETRIES tentatives."
        exit 1
    fi
    echo "     Tentative $RETRY/$MAX_RETRIES..."
    sleep 2
done
echo "     Vault est pret !"
echo ""

# ------ Injecter les credentials DB ------
echo "[2/3] Injection des credentials de base de donnees..."
vault kv put secret/db \
    host="$DB_HOST" \
    port="$DB_PORT" \
    name="$DB_NAME" \
    user="$DB_USER" \
    password="$DB_PASSWORD"
echo "     -> secret/db OK"
echo ""

# ------ Injecter les secrets applicatifs ------
echo "[3/3] Injection des secrets applicatifs..."
vault kv put secret/app \
    pepper="$APP_PEPPER" \
    secret_key="$APP_SECRET_KEY"
echo "     -> secret/app OK"
echo ""

# ------ Verification ------
echo "=========================================="
echo " Verification des secrets injectes"
echo "=========================================="
echo ""
echo "--- secret/db ---"
vault kv get secret/db
echo ""
echo "--- secret/app ---"
vault kv get secret/app
echo ""
echo "=========================================="
echo " Tous les secrets ont ete injectes !"
echo "=========================================="
