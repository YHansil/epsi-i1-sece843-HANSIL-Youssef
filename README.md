# SecuByDesign

Mini-application web sécurisée — Projet **Sécurité By Design** (EPSI I1 EISI)

> **Auteur** : HANSIL Youssef

---

## Présentation

Ce projet met en pratique les notions de sécurité applicative vues en cours :

- **HashiCorp Vault** pour le stockage des secrets (credentials DB, poivre, clé de session)
- **Hachage renforcé** des mots de passe (PBKDF2 + sel unique + poivre)
- **Authentification 2FA** avec OTP (TOTP, compatible Google Authenticator)
- **CAPTCHA** sur le formulaire d'inscription pour lutter contre les bots
- **Conteneurisation Docker** avec réseau isolé

---

## Architecture

```
┌──────────────┐     ┌──────────────────────┐     ┌──────────────┐
│  Navigateur  │────▶│  Flask App :5000     │────▶│ MariaDB :3306│
│              │     │                      │     │              │
└──────────────┘     │  - CAPTCHA texte     │     │  Table users │
                     │  - 2FA / OTP         │     │  (hash + sel)│
                     │  - Sessions sécurisées│     └──────────────┘
                     │                      │
                     │     ┌────────────┐   │
                     │     │   Vault    │   │
                     │     │   :8200    │◀──│ Lecture des secrets
                     │     └────────────┘   │ au démarrage
                     └──────────────────────┘
```

### Services Docker

| Service | Image | Port | Rôle |
|---|---|---|---|
| `mariadb` | mariadb:10.11 | 3307 (ext) → 3306 (int) | Base de données |
| `vault` | hashicorp/vault:1.15 | 8200 | Coffre-fort de secrets |
| `vault-init` | hashicorp/vault:1.15 | — | Injecte les secrets dans Vault puis s'arrête |
| `app` | Build local (Python 3.11) | 5000 | Application Flask |

---

## Fonctionnalités

### 1. Inscription avec CAPTCHA

- Formulaire : nom d'utilisateur + mot de passe + confirmation + CAPTCHA
- **CAPTCHA texte** généré via la librairie `captcha` (caractères déformés avec bruit et courbes)
- Vérification insensible à la casse

### 2. Politique de mot de passe forte

Le mot de passe doit respecter :

| Critère | Exigence |
|---|---|
| Longueur | 20 caractères minimum |
| Minuscules | Au moins 3 |
| Majuscules | Au moins 3 |
| Chiffres | Au moins 3 |
| Caractères spéciaux | Au moins 3 |

### 3. Hachage sécurisé (sel + poivre)

```
hash = PBKDF2-HMAC-SHA256(
    clé        = poivre + mot_de_passe + sel,
    sel        = sel_unique_par_utilisateur (256 bits),
    itérations = 310 000
)
```

- **Sel** : généré aléatoirement, unique par utilisateur, stocké en base
- **Poivre** : secret global, stocké dans Vault (**jamais en base de données**)
- Même si la BDD est compromise, les hash ne sont pas exploitables sans le poivre

### 4. Connexion avec 2FA / OTP

- **Étape 1** : saisie identifiant + mot de passe → vérification contre le hash
- **Étape 2** : saisie du code OTP à 6 chiffres (TOTP, RFC 6238)
- Compatible : Google Authenticator, Microsoft Authenticator, Authy, FreeOTP
- QR code affiché à l'inscription pour configurer l'application 2FA

### 5. Page d'accueil

- Accessible uniquement après authentification complète (identifiants + OTP)
- Affiche le nom d'utilisateur et un message de bienvenue
- Bouton de déconnexion

---

## Gestion des secrets avec Vault

**Aucun credential n'est écrit en clair dans le code source de l'application.** Seul le `VAULT_TOKEN` est stocké dans le `.env`. Tous les autres secrets sont définis dans `scripts/init_vault.sh` et injectés dans Vault au démarrage :

| Chemin Vault | Clés | Description |
|---|---|---|
| `secret/db` | `host`, `port`, `name`, `user`, `password` | Connexion à MariaDB |
| `secret/app` | `pepper`, `secret_key` | Poivre (hachage) + clé de session Flask |

L'application Flask récupère **tous** ses secrets depuis Vault au démarrage — elle ne lit jamais le `.env` directement.

---

## Sécurités implémentées

- [x] Mots de passe hachés avec **sel unique** par utilisateur
- [x] **Poivre** (pepper) stocké hors de la base de données (dans Vault)
- [x] Authentification **2FA** via TOTP (RFC 6238)
- [x] **CAPTCHA texte** sur le formulaire d'inscription
- [x] **Politique de mot de passe** stricte (20 car., complexité)
- [x] Credentials DB dans **HashiCorp Vault** (pas en clair dans les fichiers de config)
- [x] `.env` minimaliste : seul le **VAULT_TOKEN** y figure
- [x] Cookies de session **HttpOnly** + **SameSite=Lax**
- [x] Requêtes SQL **paramétrées** (protection injection SQL)
- [x] Application conteneurisée avec **réseau Docker isolé**

---

## Prérequis

- **OS** : Ubuntu 20.04+ ou Debian 11+ (ou Windows/macOS avec Docker Desktop)
- **Docker** : Docker Engine 24+ et Docker Compose V2

---

## Installation et lancement

### 1. Installer Docker (Ubuntu/Debian uniquement, si pas déjà installé)

```bash
chmod +x scripts/install_docker.sh
./scripts/install_docker.sh
# Puis se déconnecter/reconnecter ou : newgrp docker
```

### 2. Créer le fichier `.env`

```bash
echo "VAULT_TOKEN=myroot" > .env
```

Le `.env` ne contient que le **`VAULT_TOKEN`** (token root Vault en mode développement). Tous les autres secrets (credentials DB, poivre, clé de session) sont définis dans `scripts/init_vault.sh` et injectés directement dans Vault.

### 3. Lancer l'application

```bash
docker compose up --build -d
```

Docker Compose démarre automatiquement dans l'ordre :
1. **MariaDB** (attend d'être healthy)
2. **Vault** en mode développement
3. **vault-init** injecte les secrets dans Vault
4. **Application Flask** (récupère les secrets depuis Vault)

### 4. Accéder à l'application

Ouvrir : **http://localhost:5000**

---

## Utilisation

1. **Créer un compte** sur `/register` (remplir le CAPTCHA, respecter la politique de mdp)
2. **Scanner le QR code** avec Google Authenticator / Authy / Microsoft Authenticator
3. **Se connecter** sur `/login` avec ses identifiants
4. **Entrer le code OTP** à 6 chiffres de l'application 2FA
5. **Page d'accueil** avec message de bienvenue

---

## Structure du projet

```
ESPI_SecuByDesign/
├── docker-compose.yml          # Orchestration des 4 services
├── Dockerfile                  # Image Docker de l'app Flask
├── .env                        # VAULT_TOKEN uniquement (exclu de Git, à créer)
├── .gitignore                  # Exclut .env du dépôt
│
├── src/                        # Code source
│   ├── app.py                  # Application Flask principale
│   ├── requirements.txt        # Dépendances Python
│   ├── templates/              # Templates HTML (Jinja2)
│   │   ├── base.html
│   │   ├── register.html       # Inscription + CAPTCHA
│   │   ├── login.html          # Connexion (étape 1)
│   │   ├── otp_setup.html      # Configuration 2FA (QR code)
│   │   ├── otp_verify.html     # Vérification OTP (étape 2)
│   │   └── home.html           # Accueil (après authentification)
│   └── static/
│       └── style.css
│
├── scripts/
│   ├── install_docker.sh       # Installation Docker (Ubuntu/Debian)
│   └── init_vault.sh           # Injection des secrets dans Vault
│
└── README.md
```

---

## Commandes utiles

```bash
# Démarrer tous les services
docker compose up --build -d

# Voir les logs de l'application
docker compose logs -f app

# Arrêter les services
docker compose down

# Reset complet (supprime la BDD)
docker compose down -v

# Vérifier les secrets dans Vault
docker compose exec vault vault kv get secret/db
docker compose exec vault vault kv get secret/app
```

---

## Stack technique

| Composant | Technologie |
|---|---|
| Backend | Python 3.11 + Flask |
| Base de données | MariaDB 10.11 |
| Secrets | HashiCorp Vault 1.15 |
| Hachage | PBKDF2-HMAC-SHA256 (310 000 itérations) |
| 2FA / OTP | PyOTP (TOTP - RFC 6238) |
| CAPTCHA | Librairie `captcha` (texte déformé) |
| QR Code | qrcode (Python) |
| Conteneurisation | Docker + Docker Compose |
