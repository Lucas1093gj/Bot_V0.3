from flask import Blueprint, request, session, redirect, url_for, flash, current_app, render_template
import requests
from datetime import datetime
from ..utils import get_ngrok_url, TOKEN_URL

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return "Erreur : code manquant.", 400

    WEB_BASE_URL = get_ngrok_url() or current_app.config.get("WEB_BASE_URL", "http://127.0.0.1:5000")
    REDIRECT_URI = f"{WEB_BASE_URL}/auth/callback"

    data = {
        'client_id': current_app.config['CLIENT_ID'],
        'client_secret': current_app.config['CLIENT_SECRET'],
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = { 'Content-Type': 'application/x-www-form-urlencoded' }

    try:
        token_response = requests.post(TOKEN_URL, data=data, headers=headers)
        token_response.raise_for_status()
        token_data = token_response.json()
        
        session['access_token'] = token_data.get('access_token')
        session['refresh_token'] = token_data.get('refresh_token')
        session['expires_at'] = datetime.now().timestamp() + token_data.get('expires_in', 0)

        user_headers = {'Authorization': f'Bearer {session["access_token"]}'}
        user_info_response = requests.get("https://discord.com/api/v10/users/@me", headers=user_headers)
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        session['user_info'] = user_info

        return redirect(url_for('public.home'))

    except requests.exceptions.RequestException as e:
        return f"Erreur lors de l'échange de token : {e}", 500

@auth_bp.route('/logout')
def logout():
    """Déconnecte l'utilisateur en vidant la session."""
    session.clear()
    flash("Vous avez été déconnecté avec succès.", "info")
    return redirect(url_for('public.home'))