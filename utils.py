from flask import session, current_app, flash
import requests
import asyncio
from datetime import datetime
import aiosqlite

# URL de l'API Discord
TOKEN_URL = "https://discord.com/api/oauth2/token"
GUILDS_URL = "https://discord.com/api/v10/users/@me/guilds"

def get_ngrok_url():
    """Interroge l'API locale de ngrok pour trouver l'URL publique du tunnel https."""
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels")
        response.raise_for_status()
        tunnels = response.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel.get("proto") == "https" and "public_url" in tunnel:
                return tunnel["public_url"]
    except requests.exceptions.RequestException:
        return None
    return None

def is_bot_admin():
    """Vérifie si l'utilisateur connecté est un admin du bot."""
    if 'user_info' in session:
        return session['user_info'].get('id') in current_app.config['ADMIN_BOT_IDS']
    return False

async def get_db_async():
    """Ouvre une connexion aiosqlite."""
    db = await aiosqlite.connect(current_app.config['DATABASE_PATH'])
    db.row_factory = aiosqlite.Row
    return db

def run_async(coro):
    """Exécute une coroutine dans la boucle d'événements du bot."""
    bot = current_app.config['BOT_INSTANCE']
    future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return future.result()

def check_admin_permissions(server_id):
    """Vérifie si l'utilisateur connecté est admin du serveur demandé."""
    if 'access_token' not in session:
        return None
    headers = {'Authorization': f'Bearer {session["access_token"]}'}
    try:
        guilds_response = requests.get(GUILDS_URL, headers=headers)
        guilds_response.raise_for_status()
        all_guilds = guilds_response.json()
        return next((g for g in all_guilds if g['id'] == server_id and (int(g['permissions']) & 0x8 == 0x8)), None)
    except requests.exceptions.RequestException:
        session.pop('access_token', None)
        return None

def refresh_token():
    """Tente de rafraîchir le token d'accès."""
    with current_app.token_refresh_lock:
        if 'expires_at' in session and datetime.now().timestamp() < session['expires_at']:
            return True
        if 'refresh_token' not in session:
            return False

        data = {
            'client_id': current_app.config['CLIENT_ID'],
            'client_secret': current_app.config['CLIENT_SECRET'],
            'grant_type': 'refresh_token',
            'refresh_token': session['refresh_token']
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            response = requests.post(TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            new_token_data = response.json()
            session['access_token'] = new_token_data['access_token']
            session['refresh_token'] = new_token_data['refresh_token']
            session['expires_at'] = datetime.now().timestamp() + new_token_data['expires_in']
            flash("Votre session a été rafraîchie automatiquement.", "info")
            return True
        except requests.exceptions.RequestException:
            session.clear()
            return False

def get_guild_details(server_id: str) -> dict:
    """Récupère les détails étendus d'un serveur via l'API avec le token du bot."""
    headers_bot = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}
    try:
        response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}?with_counts=true", headers=headers_bot)
        return response.json() if response.status_code == 200 else {}
    except requests.exceptions.RequestException:
        return {}

def fetch_user_details_http(user_ids: set) -> dict:
    """Récupère les détails des utilisateurs via l'API HTTP."""
    user_details = {}
    headers = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}
    for user_id in user_ids:
        if not user_id: continue
        try:
            response = requests.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                user_details[str(user_id)] = {
                    "name": user_data.get('global_name', f"{user_data['username']}#{user_data['discriminator']}"),
                    "global_name": f"{user_data['username']}#{user_data['discriminator']}",
                    "avatar_url": f"https://cdn.discordapp.com/avatars/{user_id}/{user_data['avatar']}.png" if user_data.get('avatar') else "https://cdn.discordapp.com/embed/avatars/0.png"
                }
            else:
                user_details[str(user_id)] = {"name": f"Utilisateur introuvable ({user_id})", "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"}
        except requests.exceptions.RequestException:
            user_details[str(user_id)] = {"name": f"Erreur API ({user_id})", "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"}
    return user_details