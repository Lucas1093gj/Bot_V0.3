from flask import Blueprint, render_template, request, session, current_app, redirect, url_for, flash, jsonify, Response
import requests
from itertools import groupby
from discord import app_commands
import wavelink
from datetime import datetime
import json

import aiosqlite
from ..utils import get_db_async, run_async, GUILDS_URL
from db_manager import get_db_connection # Correction de l'import

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def home():
    bot = current_app.config['BOT_INSTANCE']
    bot_guilds_count = len(bot.guilds) if bot and bot.is_ready() else 0
    bot_users_count = sum(g.member_count for g in bot.guilds) if bot and bot.is_ready() else 0

    def get_vlog_content():
        async def _get_vlog():
            db = await get_db_async()
            cursor = await db.execute("SELECT value FROM global_settings WHERE key = 'update_vlog_content'")
            vlog_data = await cursor.fetchone()
            await db.close()
            return vlog_data['value'] if vlog_data else None
        return run_async(_get_vlog())
    
    update_vlog_content = get_vlog_content()
    bot_name = bot.user.name if bot and bot.user else "FunBot"
    bot_avatar_url = bot.user.display_avatar.url if bot and bot.user else "https://cdn.discordapp.com/embed/avatars/0.png"

    if 'access_token' not in session:
        return render_template(
            'index.html', 
            logged_in=False,
            bot_name=bot_name,
            bot_avatar_url=bot_avatar_url,
            client_id=current_app.config['CLIENT_ID'],
            bot_guilds_count=bot_guilds_count,
            bot_users_count=bot_users_count,
            redirect_uri=current_app.config['REDIRECT_URI'],
            update_vlog_content=update_vlog_content
        )

    # Si l'utilisateur est connecté, on récupère ses infos et ses serveurs
    headers = {'Authorization': f'Bearer {session["access_token"]}'}
    try:
        user_info = session.get('user_info')
        if not user_info:
             user_info_response = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
             user_info_response.raise_for_status()
             user_info = user_info_response.json()
             session['user_info'] = user_info

        user_guilds_response = requests.get(GUILDS_URL, headers=headers)
        user_guilds_response.raise_for_status()
        all_user_guilds = user_guilds_response.json()
        
        admin_guilds = [g for g in all_user_guilds if int(g['permissions']) & 0x8 == 0x8]
        bot_guild_ids = {g.id for g in bot.guilds}

        shared_guilds = sorted(
            [g for g in admin_guilds if int(g['id']) in bot_guild_ids],
            key=lambda g: g['name'].lower()
        )
        
        owned_servers = [g for g in shared_guilds if g['owner']]
        admin_servers = [g for g in shared_guilds if not g['owner']]
        
        return render_template(
            'index.html', 
            logged_in=True,
            user_info=user_info,
            owned_servers=owned_servers, 
            admin_servers=admin_servers,
            bot_guilds_count=bot_guilds_count,
            bot_users_count=bot_users_count,
            update_vlog_content=update_vlog_content
        )
    except requests.exceptions.RequestException:
        session.clear()
        return redirect(url_for('public.home'))

def get_command_cog_name(command):
    if hasattr(command, 'cog') and command.cog is not None:
        return command.cog.qualified_name.replace("Cog", "")
    return "Sans catégorie"

@public_bp.route('/commands')
def commands_page():
    bot = current_app.config['BOT_INSTANCE']
    search_query = request.args.get('q', '').lower()
    all_commands_raw = bot.tree.get_commands()

    if search_query:
        all_commands_raw = [c for c in all_commands_raw if search_query in c.name.lower() or (c.description and search_query in c.description.lower())]

    all_commands = sorted(all_commands_raw, key=lambda c: get_command_cog_name(c) or 'Sans catégorie')

    grouped_commands = {} 
    for key, group in groupby(all_commands, key=lambda c: get_command_cog_name(c) or 'Sans catégorie'):
        command_list = []
        for cmd in group:
            if isinstance(cmd, app_commands.Group):
                command_list.extend(cmd.commands)
            else:
                command_list.append(cmd)
        grouped_commands[key] = sorted(command_list, key=lambda c: c.name)

    bot_name = bot.user.name if bot and bot.user else "FunBot"
    return render_template('commands.html', grouped_commands=grouped_commands, bot_name=bot_name, search_query=search_query)

@public_bp.route('/status')
def status_page():
    bot = current_app.config['BOT_INSTANCE']
    bot_is_ready = bot and bot.is_ready()
    bot_status = {"status": "ok", "text": "En ligne"} if bot_is_ready else {"status": "error", "text": "Hors ligne"}
    bot_latency = bot.latency * 1000 if bot_is_ready else -1
    guild_count = len(bot.guilds) if bot_is_ready else 0

    def check_db():
        try:
            async def _db_test():
                db = await get_db_async()
                await db.close()
            run_async(_db_test())
            return {"status": "ok", "text": "Opérationnelle"}
        except Exception:
            return {"status": "error", "text": "Erreur"}
    db_status = check_db()

    lavalink_nodes_status = []
    all_nodes_ok = True
    if bot_is_ready and hasattr(wavelink.Pool, 'nodes') and wavelink.Pool.nodes:
        for node in wavelink.Pool.nodes.values():
            is_connected = node.status == wavelink.NodeStatus.CONNECTED
            if not is_connected: all_nodes_ok = False
            lavalink_nodes_status.append({"identifier": node.identifier, "status": "ok" if is_connected else "error", "text": "Connecté" if is_connected else "Déconnecté", "heartbeat": node.heartbeat if node.heartbeat != -1 else None})
    else:
        all_nodes_ok = False
        lavalink_nodes_status.append({"identifier": "Aucun nœud", "status": "error", "text": "Non configuré", "heartbeat": -1})

    overall_status = "ok" if bot_is_ready and db_status['status'] == 'ok' and all_nodes_ok else "error"

    return render_template('status.html', bot_name=bot.user.name if bot_is_ready else "FunBot", overall_status=overall_status, last_checked=datetime.now().strftime('%H:%M:%S UTC'), bot_status=bot_status, bot_latency=bot_latency, guild_count=guild_count, db_status=db_status, lavalink_nodes=lavalink_nodes_status)

@public_bp.route('/privacy-policy')
def privacy_policy_page():
    """Affiche la page de politique de confidentialité."""
    bot = current_app.config['BOT_INSTANCE']
    return render_template('privacy_policy.html', bot_name=bot.user.name if bot and bot.user else "FunBot")

@public_bp.route('/terms-of-service')
def terms_of_service_page():
    """Affiche la page des conditions d'utilisation."""
    bot = current_app.config['BOT_INSTANCE']
    return render_template('terms_of_service.html', bot_name=bot.user.name if bot and bot.user else "FunBot")

@public_bp.route('/settings')
def settings_page():
    return render_template('settings.html')

@public_bp.route('/set-language', methods=['POST'])
def set_language():
    """
    Route pour changer la langue de l'utilisateur et la stocker en session.
    """
    data = request.get_json()
    lang = data.get('lang')

    # On importe le traducteur global et on vérifie que la langue est supportée
    from i18n import translator
    if lang and lang in translator.translations.keys():
        session['lang'] = lang
        return jsonify({'status': 'success', 'message': f'Langue changée en {lang}.'})
    
    return jsonify({'status': 'error', 'message': 'Langue non valide.'}), 400

@public_bp.route('/settings/request-data', methods=['POST'])
def request_data():
    """Exporte les données de l'utilisateur au format JSON."""
    if 'user_info' not in session:
        flash("Vous devez être connecté pour effectuer cette action.", "warning")
        return redirect(url_for('public.home'))

    user_id = session['user_info']['id']

    async def _get_user_data():
        user_data = {
            'user_id': user_id,
            'requested_at': datetime.utcnow().isoformat() + 'Z',
            'data': {}
        }
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row # Ajouter cette ligne pour obtenir des dictionnaires
            # Récupérer les avertissements
            warns_cursor = await db.execute("SELECT guild_id, moderator_id, reason, timestamp FROM warnings WHERE user_id = ?", (user_id,))
            user_data['data']['warnings'] = [dict(row) for row in await warns_cursor.fetchall()]

            # Récupérer les niveaux
            levels_cursor = await db.execute("SELECT guild_id, xp, level FROM user_levels WHERE user_id = ?", (user_id,))
            user_data['data']['levels'] = [dict(row) for row in await levels_cursor.fetchall()]

            # Récupérer les logs de messages (en tant qu'auteur)
            logs_cursor = await db.execute("SELECT guild_id, channel_id, event_type, old_content, new_content, timestamp FROM message_events WHERE author_id = ? LIMIT 1000", (user_id,))
            user_data['data']['message_logs'] = [dict(row) for row in await logs_cursor.fetchall()]

        return user_data

    data_to_export = run_async(_get_user_data()) # On appelle la fonction pour créer la coroutine
    
    return Response(
        json.dumps(data_to_export, indent=4, ensure_ascii=False),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment;filename=user_data_{user_id}.json'}
    )

@public_bp.route('/settings/delete-account', methods=['POST'])
def delete_account():
    """Supprime toutes les données de l'utilisateur de la base de données."""
    if 'user_info' not in session:
        flash("Vous devez être connecté pour effectuer cette action.", "warning")
        return redirect(url_for('public.home'))

    user_id = session['user_info']['id']

    async def _delete_user_data():
        async with get_db_connection() as db:
            await db.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM user_levels WHERE user_id = ?", (user_id,))
            # On ne supprime pas les logs de messages pour préserver l'intégrité de la modération
            await db.commit()

    run_async(_delete_user_data())
    flash("Votre demande de suppression a été traitée. Vos données personnelles (niveaux, avertissements) ont été supprimées. Les logs de modération sont conservés pour la sécurité du serveur.", "success")
    return redirect(url_for('public.settings_page'))