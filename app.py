from flask import Flask, render_template, request, session, redirect, url_for, g, flash, jsonify
import requests
import os
import sqlite3
from dotenv import load_dotenv
from i18n import translator, _
from datetime import datetime

# --- Configuration ---
load_dotenv()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI") # Utilise la variable du .env
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "une-cle-secrete-par-defaut-pour-le-dev")
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_database.db')
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# Vérification critique au démarrage
# On s'assure que les secrets essentiels sont bien présents dans le .env avant de continuer.
if not CLIENT_ID or not CLIENT_SECRET or not BOT_TOKEN:
    raise ValueError("[ERREUR] DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, et DISCORD_TOKEN doivent être définis dans le fichier .env")

TOKEN_URL = "https://discord.com/api/oauth2/token"
GUILDS_URL = "https://discord.com/api/v10/users/@me/guilds"

# -- Configuration de Flask --
app = Flask(__name__, 
            template_folder='web',    # Dossier pour HTML
            static_folder='web')      # Dossier pour CSS/JS
app.config['SECRET_KEY'] = SECRET_KEY

# --- Initialisation de l'internationalisation (i18n) ---
translator.init_app(app)

@app.context_processor
def inject_i18n():
    """Injecte les fonctions de traduction dans le contexte de tous les templates Jinja2."""
    return dict(_=_, get_locale=translator.get_locale)

# --- Gestion de la base de données ---
def get_db():
    """Ouvre une connexion à la base de données pour la requête en cours et la stocke dans le contexte `g` de Flask."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Ferme proprement la connexion à la base de données à la fin de chaque requête pour libérer les ressources."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ===============================================
# Route 1: La Page d'Accueil (gère tout)
# ===============================================
@app.route('/')
def home():
    # Si l'utilisateur n'est pas connecté (pas de token dans sa session), on affiche la page de connexion.
    if 'access_token' not in session:
        return render_template(
            'index.html', 
            servers=None, 
            client_id=CLIENT_ID, 
            redirect_uri=REDIRECT_URI
        )

    # Si l'utilisateur est connecté, on utilise son token pour récupérer ses informations.
    access_token = session['access_token']
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        # On récupère la liste de TOUS les serveurs où l'utilisateur est présent.
        user_guilds_response = requests.get(GUILDS_URL, headers=headers)
        user_guilds_response.raise_for_status()
        all_user_guilds = user_guilds_response.json()
        
        # 1. On filtre pour ne garder que les serveurs où l'utilisateur est admin
        admin_guilds = []
        for guild in all_user_guilds:
            if int(guild['permissions']) & 0x8 == 0x8:
                admin_guilds.append(guild)
        
        # 2. On récupère la liste des serveurs où le BOT est présent (en utilisant le token du bot).
        bot_headers = {'Authorization': f'Bot {BOT_TOKEN}'}
        bot_guilds_response = requests.get(GUILDS_URL, headers=bot_headers)
        bot_guilds_response.raise_for_status()
        bot_guilds = bot_guilds_response.json()
        bot_guild_ids = {g['id'] for g in bot_guilds}

        # 3. On ne garde que les serveurs en commun
        shared_guilds = [g for g in admin_guilds if g['id'] in bot_guild_ids] # noqa
        
        # 4. On récupère les infos de l'utilisateur pour séparer les serveurs qu'il possède de ceux qu'il administre simplement.
        user_info_response = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
        user_info_response.raise_for_status()
        user_info = user_info_response.json()

        owned_servers = [g for g in shared_guilds if g['owner']]
        admin_servers_only = [g for g in shared_guilds if not g['owner']]

        # 5. On affiche la page d'accueil avec toutes les informations nécessaires.
        return render_template('index.html', logged_in=True, user_info=user_info, owned_servers=owned_servers, admin_servers=admin_servers_only, is_bot_admin=user_info['id'] in os.getenv("ADMIN_BOT_IDS", ""))
            
    except requests.exceptions.RequestException as e:
        # Si le token d'accès est expiré ou invalide, on déconnecte l'utilisateur et on l'invite à se reconnecter.
        session.pop('access_token', None)
        return f"Erreur API (token expiré ?) : {e}. <a href='/'>Réessayer de se connecter</a>"

# ===============================================
# Route 2: Le Callback (LA PARTIE CORRIGÉE)
# ===============================================
@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return "Erreur : code manquant.", 400

    # 1. On prépare les données nécessaires pour échanger le `code` d'autorisation contre un `access_token`.
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = { 'Content-Type': 'application/x-www-form-urlencoded' }

    try:
        # 2. On envoie la requête POST à l'API de Discord.
        token_response = requests.post(TOKEN_URL, data=data, headers=headers)
        token_response.raise_for_status()
        token_data = token_response.json()
        
        # 3. On sauvegarde le précieux `access_token` dans la session de l'utilisateur.
        session['access_token'] = token_data.get('access_token')
        
        # 4. On redirige l'utilisateur vers la page d'accueil, où il sera maintenant reconnu comme connecté.
        return redirect(url_for('home'))

    except requests.exceptions.RequestException as e:
        return f"Erreur lors de l'échange de token : {e}", 500

# ===============================================
# Route 3: Déconnexion
# ===============================================
@app.route('/logout')
def logout():
    """Déconnecte l'utilisateur en vidant sa session."""
    session.clear()
    return redirect(url_for('home'))


# --- Fonctions utilitaires pour le Dashboard ---
def check_admin_permissions(server_id):
    """
    Vérifie si l'utilisateur actuellement connecté a bien les permissions d'administrateur sur le serveur demandé.
    Retourne les informations du serveur s'il a la permission, sinon None.
    """
    if 'access_token' not in session:
        return None

    access_token = session['access_token']
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        guilds_response = requests.get(GUILDS_URL, headers=headers)
        guilds_response.raise_for_status()
        all_guilds = guilds_response.json()
        return next((g for g in all_guilds if g['id'] == server_id and (int(g['permissions']) & 0x8 == 0x8)), None)
    except requests.exceptions.RequestException:
        session.pop('access_token', None) # Le token est probablement invalide, on le supprime.
        return None

# ===============================================
# Routes du Dashboard
# ===============================================
@app.route('/dashboard/<server_id>')
def dashboard(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild:
        return redirect(url_for('home'))
        
    # C'est une page "hub" qui sert de point d'entrée pour le dashboard d'un serveur.
    return render_template('dashboard.html', server=target_guild)

@app.route('/dashboard/<server_id>/warnings')
def dashboard_warnings(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild:
        return redirect(url_for('home'))

    db = get_db()
    cursor = db.execute(
        "SELECT id, user_id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? ORDER BY timestamp DESC",
        (server_id,)
    )
    warnings = cursor.fetchall()

    # Pour afficher les noms et avatars, on doit "enrichir" les données de la DB avec des infos de l'API Discord.
    user_ids = {warn['user_id'] for warn in warnings} | {warn['moderator_id'] for warn in warnings}
    user_details = {}
    
    # On utilise le token du bot pour récupérer les infos, car il a accès à tous les utilisateurs des serveurs où il se trouve.
    headers = {'Authorization': f'Bot {BOT_TOKEN}'}

    for user_id in user_ids:
        if not user_id: continue
        try:
            user_response = requests.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers)
            if user_response.status_code == 200:
                user_data = user_response.json()
                user_details[str(user_id)] = {
                    "name": f"{user_data['username']}#{user_data['discriminator']}",
                    "avatar_url": f"https://cdn.discordapp.com/avatars/{user_id}/{user_data['avatar']}.png" if user_data.get('avatar') else "https://cdn.discordapp.com/embed/avatars/0.png"
                }
            else:
                user_details[str(user_id)] = {"name": f"Utilisateur introuvable ({user_id})", "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"}
        except requests.exceptions.RequestException:
            user_details[str(user_id)] = {"name": f"Erreur API ({user_id})", "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"}

    # On crée une nouvelle liste de warnings, cette fois avec les détails de l'utilisateur inclus.
    enriched_warnings = []
    for warn in warnings:
        enriched_warn = dict(warn) # Copie du dictionnaire original
        enriched_warn['user_details'] = user_details.get(str(warn['user_id']), {"name": "N/A", "avatar_url": ""})
        enriched_warn['moderator_details'] = user_details.get(str(warn['moderator_id']), {"name": "N/A", "avatar_url": ""})
        # --- CORRECTION : Conversion du timestamp ---
        if isinstance(enriched_warn['timestamp'], str):
            enriched_warn['timestamp'] = datetime.fromisoformat(enriched_warn['timestamp'])
        enriched_warnings.append(enriched_warn)

    return render_template('dashboard_warnings.html', server=target_guild, warnings=enriched_warnings)

@app.route('/dashboard/<server_id>/messagelogs')
def dashboard_messagelogs(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild:
        return redirect(url_for('home'))

    db = get_db()
    cursor = db.execute(
        "SELECT author_id, channel_id, event_type, old_content, new_content, timestamp FROM message_events WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 100",
        (server_id,)
    )
    logs = cursor.fetchall()

    # Comme pour les warnings, on enrichit les logs avec les noms des auteurs et des salons.
    author_ids = {log['author_id'] for log in logs}
    user_details = {}
    channel_details = {}

    headers_bot = {'Authorization': f'Bot {BOT_TOKEN}'}

    # 1. Récupérer les détails des auteurs
    for user_id in author_ids:
        if not user_id: continue
        try:
            user_response = requests.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers_bot)
            if user_response.status_code == 200:
                user_data = user_response.json()
                user_details[str(user_id)] = {"name": f"{user_data['username']}#{user_data['discriminator']}"}
            else:
                user_details[str(user_id)] = {"name": f"Utilisateur introuvable ({user_id})"}
        except requests.exceptions.RequestException:
            user_details[str(user_id)] = {"name": f"Erreur API ({user_id})"}

    # 2. Récupérer les détails de tous les salons du serveur en une seule requête API pour optimiser.
    try:
        channels_response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers_bot)
        if channels_response.status_code == 200:
            all_channels = channels_response.json()
            channel_details = {c['id']: c['name'] for c in all_channels}
    except requests.exceptions.RequestException:
        flash("Impossible de récupérer les noms des salons.", "warning")

    # 3. On assemble le tout pour créer la liste de logs enrichis à afficher.
    enriched_logs = []
    for log in logs:
        enriched_log = dict(log)
        enriched_log['author_details'] = user_details.get(str(log['author_id']), {"name": "N/A"})
        enriched_log['channel_name'] = channel_details.get(str(log['channel_id']), "Salon inconnu")
        # Conversion du timestamp
        if isinstance(enriched_log['timestamp'], str):
            enriched_log['timestamp'] = datetime.fromisoformat(enriched_log['timestamp'])
        enriched_logs.append(enriched_log)

    return render_template('dashboard_logs.html', server=target_guild, logs=enriched_logs)

@app.route('/dashboard/<server_id>/settings', methods=['GET', 'POST'])
def dashboard_settings(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild:
        return redirect(url_for('home'))

    db = get_db()

    if request.method == 'POST':
        # Si le formulaire est soumis, on met à jour la base de données.
        log_channel_id = request.form.get('mod_log_channel_id') or None
        ticket_category_id = request.form.get('ticket_category_id') or None

        db.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, mod_log_channel_id, ticket_category_id) VALUES (?, ?, ?)",
            (server_id, log_channel_id, ticket_category_id)
        )
        db.commit()
        flash("Paramètres sauvegardés avec succès !", "success")
        return redirect(url_for('dashboard_settings', server_id=server_id))

    # Si c'est une requête GET, on récupère les paramètres actuels pour pré-remplir le formulaire.
    cursor = db.execute("SELECT mod_log_channel_id, ticket_category_id FROM guild_settings WHERE guild_id = ?", (server_id,))
    settings = cursor.fetchone()

    # Récupérer les salons et catégories du serveur via l'API Discord
    headers = {'Authorization': f'Bot {BOT_TOKEN}'}
    try:
        response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers)

        if response.status_code == 200:
            all_channels = response.json()
        else:
            # Si l'API renvoie une erreur, on essaie de l'afficher pour faciliter le débogage.
            try:
                error_details = response.json()
                error_message = error_details.get('message', 'Aucun détail fourni.')
            except requests.exceptions.JSONDecodeError:
                error_message = response.text # Si ce n'est pas du JSON, on affiche le texte brut
            flash(f"Erreur API Discord ({response.status_code}): {error_message}", "danger")
            all_channels = []

        text_channels = [c for c in all_channels if c['type'] == 0]
        category_channels = [c for c in all_channels if c['type'] == 4]

    except requests.exceptions.RequestException as e:
        flash(f"Erreur de connexion réseau : {e}", "danger")
        text_channels = []
        category_channels = []

    return render_template(
        'dashboard_settings.html',
        server=target_guild,
        settings=settings,
        text_channels=text_channels,
        category_channels=category_channels
    )

# --- Démarrage ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)