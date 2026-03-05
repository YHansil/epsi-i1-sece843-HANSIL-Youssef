"""
SecuByDesign - Mini application web securisee
==============================================
- Inscription avec CAPTCHA (math-based)
- Connexion avec authentification 2FA / OTP (TOTP)
- Mots de passe hashes avec sel unique par utilisateur + poivre
- Credentials DB stockes dans HashiCorp Vault
"""

import time
import os
import hashlib
import secrets
import random
from io import BytesIO
import base64
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
import pymysql
import pyotp
import qrcode
from PIL import Image, ImageDraw, ImageFont
import hvac


# =====================================================
# VAULT CLIENT
# =====================================================

def get_vault_client():
    """Cree une instance du client Vault."""
    return hvac.Client(
        url=os.environ.get('VAULT_ADDR', 'http://vault:8200'),
        token=os.environ.get('VAULT_TOKEN', 'myroot')
    )


def get_vault_secret(path, max_retries=30, delay=2):
    """
    Lit un secret depuis Vault KV v2 avec mecanisme de retry.
    Retourne le dictionnaire de donnees du secret.
    """
    client = get_vault_client()
    for attempt in range(max_retries):
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=path,
                raise_on_deleted_version=True
            )
            return secret['data']['data']
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[Vault] Tentative {attempt + 1}/{max_retries} "
                      f"- Lecture de '{path}': {e}")
                time.sleep(delay)
            else:
                raise Exception(
                    f"Impossible de lire le secret '{path}' depuis Vault "
                    f"apres {max_retries} tentatives: {e}"
                )


# =====================================================
# DATABASE
# =====================================================

# Cache pour eviter d'interroger Vault a chaque requete
_db_config_cache = None
_app_secrets_cache = None


def get_db_config():
    """Recupere la configuration DB depuis Vault (mise en cache)."""
    global _db_config_cache
    if _db_config_cache is None:
        data = get_vault_secret('db')
        _db_config_cache = {
            'host': data['host'],
            'port': int(data['port']),
            'database': data['name'],
            'user': data['user'],
            'password': data['password']
        }
        print(f"[Vault] Config DB chargee: host={_db_config_cache['host']}, "
              f"db={_db_config_cache['database']}")
    return _db_config_cache


def get_app_secrets():
    """Recupere les secrets applicatifs depuis Vault (mise en cache)."""
    global _app_secrets_cache
    if _app_secrets_cache is None:
        _app_secrets_cache = get_vault_secret('app')
        print("[Vault] Secrets applicatifs charges avec succes")
    return _app_secrets_cache


def get_db_connection():
    """Cree une nouvelle connexion a la base de donnees."""
    config = get_db_config()
    return pymysql.connect(
        host=config['host'],
        port=config['port'],
        user=config['user'],
        password=config['password'],
        database=config['database'],
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8mb4'
    )


def init_db():
    """
    Initialise le schema de la base de donnees.
    Cree la table 'users' si elle n'existe pas.
    """
    max_retries = 30
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(512) NOT NULL,
                        salt VARCHAR(128) NOT NULL,
                        otp_secret VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
            conn.commit()
            conn.close()
            print("[DB] Tables initialisees avec succes !")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[DB] Tentative {attempt + 1}/{max_retries} "
                      f"- Initialisation: {e}")
                time.sleep(2)
            else:
                raise Exception(
                    f"Impossible d'initialiser la base apres "
                    f"{max_retries} tentatives: {e}"
                )


# =====================================================
# PASSWORD HASHING (sel unique + poivre)
# =====================================================

def hash_password(password, salt, pepper):
    """
    Hache un mot de passe avec PBKDF2-HMAC-SHA256.

    - salt : sel unique par utilisateur (stocke en DB)
    - pepper : poivre global (stocke dans Vault, PAS en DB)

    Le mot de passe est combine : pepper + password + salt
    puis hache avec 310 000 iterations (recommandation OWASP 2023).
    """
    combined = f"{pepper}{password}{salt}"
    return hashlib.pbkdf2_hmac(
        'sha256',
        combined.encode('utf-8'),
        salt.encode('utf-8'),
        310000
    ).hex()


def verify_password(password, stored_hash, salt, pepper):
    """Verifie un mot de passe contre son hash stocke."""
    return hash_password(password, salt, pepper) == stored_hash


# =====================================================
# CAPTCHA (math-based, genere avec Pillow)
# =====================================================

def generate_captcha():
    """
    Genere un CAPTCHA mathematique sous forme d'image PNG base64.
    Retourne (image_base64, reponse_attendue).
    """
    num1 = random.randint(1, 20)
    num2 = random.randint(1, 10)

    operations = [
        ('+', num1 + num2),
        ('-', num1 - num2),
        ('x', num1 * num2),
    ]
    op_symbol, result = random.choice(operations)
    text = f"{num1} {op_symbol} {num2} = ?"

    # Creer l'image
    width, height = 240, 80
    img = Image.new('RGB', (width, height), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)

    # Bruit : lignes aleatoires
    for _ in range(6):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        color = (
            random.randint(150, 220),
            random.randint(150, 220),
            random.randint(150, 220)
        )
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

    # Bruit : points aleatoires
    for _ in range(300):
        x, y = random.randint(0, width), random.randint(0, height)
        color = (
            random.randint(100, 220),
            random.randint(100, 220),
            random.randint(100, 220)
        )
        draw.point((x, y), fill=color)

    # Police
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32
        )
    except (IOError, OSError):
        font = ImageFont.load_default()

    # Centrer le texte
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2
    y = (height - text_h) // 2

    # Ombre + texte
    draw.text((x + 1, y + 1), text, fill=(120, 120, 120), font=font)
    draw.text((x, y), text, fill=(20, 20, 80), font=font)

    # Convertir en base64
    buf = BytesIO()
    img.save(buf, format='PNG')
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return img_base64, str(result)


# =====================================================
# INITIALISATION FLASK
# =====================================================

print("=" * 55)
print("  SecuByDesign - Demarrage de l'application...")
print("=" * 55)

# Charger les secrets depuis Vault
app_secrets = get_app_secrets()
PEPPER = app_secrets['pepper']

# Creer l'application Flask
app = Flask(__name__)
app.secret_key = app_secrets['secret_key']
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialiser la base de donnees
init_db()

print("=" * 55)
print("  SecuByDesign - Application prete !")
print("  -> http://localhost:5000")
print("=" * 55)


# =====================================================
# DECORATEUR D'AUTHENTIFICATION
# =====================================================

def login_required(f):
    """Decorateur : redirige vers /login si non authentifie."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour acceder a cette page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# =====================================================
# ROUTES
# =====================================================

@app.route('/')
@login_required
def home():
    """Page d'accueil (authentification requise)."""
    return render_template('home.html', username=session.get('username'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Formulaire de creation de compte avec CAPTCHA."""
    if request.method == 'GET':
        captcha_img, captcha_answer = generate_captcha()
        session['captcha_answer'] = captcha_answer
        return render_template('register.html', captcha_img=captcha_img)

    # --- POST : traitement de l'inscription ---
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    password_confirm = request.form.get('password_confirm', '')
    captcha_input = request.form.get('captcha', '').strip()

    # Validation du CAPTCHA
    if captcha_input != session.get('captcha_answer'):
        flash('CAPTCHA incorrect. Veuillez reessayer.', 'danger')
        captcha_img, captcha_answer = generate_captcha()
        session['captcha_answer'] = captcha_answer
        return render_template('register.html',
                               captcha_img=captcha_img, username=username)

    # Validation des champs
    errors = []
    if not username or len(username) < 3:
        errors.append(
            "Le nom d'utilisateur doit contenir au moins 3 caracteres.")
    if len(username) > 50:
        errors.append(
            "Le nom d'utilisateur ne peut pas depasser 50 caracteres.")
    if not password or len(password) < 8:
        errors.append(
            'Le mot de passe doit contenir au moins 8 caracteres.')
    if password != password_confirm:
        errors.append('Les mots de passe ne correspondent pas.')

    if errors:
        for error in errors:
            flash(error, 'danger')
        captcha_img, captcha_answer = generate_captcha()
        session['captcha_answer'] = captcha_answer
        return render_template('register.html',
                               captcha_img=captcha_img, username=username)

    # Generer le sel unique et hacher le mot de passe
    salt = secrets.token_hex(32)  # 64 chars hex = 256 bits
    password_hash = hash_password(password, salt, PEPPER)

    # Generer le secret OTP pour la 2FA
    otp_secret = pyotp.random_base32()

    # Inserer l'utilisateur en base
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO users (username, password_hash, salt, otp_secret) '
                'VALUES (%s, %s, %s, %s)',
                (username, password_hash, salt, otp_secret)
            )
        conn.commit()

        # Stocker les infos pour la configuration OTP
        session['otp_setup_secret'] = otp_secret
        session['otp_setup_username'] = username

        flash('Compte cree avec succes ! Configurez maintenant '
              'votre authentification 2FA.', 'success')
        return redirect(url_for('otp_setup'))

    except pymysql.err.IntegrityError:
        flash("Ce nom d'utilisateur est deja pris. "
              "Choisissez-en un autre.", 'danger')
        captcha_img, captcha_answer = generate_captcha()
        session['captcha_answer'] = captcha_answer
        return render_template('register.html',
                               captcha_img=captcha_img, username=username)
    finally:
        conn.close()


@app.route('/otp-setup')
def otp_setup():
    """Page de configuration OTP apres inscription."""
    otp_secret = session.get('otp_setup_secret')
    username = session.get('otp_setup_username')

    if not otp_secret or not username:
        flash('Session expiree. Veuillez vous reinscrire.', 'warning')
        return redirect(url_for('register'))

    # Generer l'URI de provisioning et le QR code
    totp = pyotp.TOTP(otp_secret)
    provisioning_uri = totp.provisioning_uri(
        name=username, issuer_name='SecuByDesign'
    )

    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    # Nettoyer la session
    session.pop('otp_setup_secret', None)
    session.pop('otp_setup_username', None)

    return render_template(
        'otp_setup.html',
        qr_code=qr_base64,
        otp_secret=otp_secret,
        username=username
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Formulaire de connexion (etape 1 : identifiants)."""
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if not username or not password:
        flash('Veuillez remplir tous les champs.', 'danger')
        return render_template('login.html')

    # Rechercher l'utilisateur en base
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT * FROM users WHERE username = %s', (username,)
            )
            user = cursor.fetchone()
    finally:
        conn.close()

    if not user:
        flash('Identifiants incorrects.', 'danger')
        return render_template('login.html')

    # Verifier le mot de passe
    if not verify_password(password, user['password_hash'],
                           user['salt'], PEPPER):
        flash('Identifiants incorrects.', 'danger')
        return render_template('login.html')

    # Mot de passe OK -> verification OTP
    session['pending_user_id'] = user['id']
    session['pending_username'] = user['username']
    session['pending_otp_secret'] = user['otp_secret']

    return redirect(url_for('otp_verify'))


@app.route('/otp-verify', methods=['GET', 'POST'])
def otp_verify():
    """Verification du code OTP (etape 2 de la connexion)."""
    if 'pending_user_id' not in session:
        flash("Veuillez d'abord entrer vos identifiants.", 'warning')
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template(
            'otp_verify.html',
            username=session.get('pending_username')
        )

    otp_code = request.form.get('otp_code', '').strip()
    otp_secret = session.get('pending_otp_secret')

    totp = pyotp.TOTP(otp_secret)

    if totp.verify(otp_code, valid_window=1):
        # OTP valide ! Creer la session authentifiee
        session['user_id'] = session.pop('pending_user_id')
        session['username'] = session.pop('pending_username')
        session.pop('pending_otp_secret', None)

        flash(f'Bienvenue, {session["username"]} ! '
              'Connexion reussie.', 'success')
        return redirect(url_for('home'))
    else:
        flash('Code OTP invalide. Veuillez reessayer.', 'danger')
        return render_template(
            'otp_verify.html',
            username=session.get('pending_username')
        )


@app.route('/logout')
def logout():
    """Deconnexion de l'utilisateur."""
    session.clear()
    flash('Vous avez ete deconnecte avec succes.', 'info')
    return redirect(url_for('login'))


# =====================================================
# POINT D'ENTREE
# =====================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
