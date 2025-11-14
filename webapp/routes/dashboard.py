from flask import Blueprint, render_template, request, session, redirect, url_for, flash, current_app
import requests
from datetime import datetime
import discord

from ..utils import (
    check_admin_permissions, refresh_token, get_guild_details, get_db_async, 
    run_async, fetch_user_details_http, GUILDS_URL, is_valid_url
)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

def dashboard_home():
    """Cette fonction est appelée par la route '/' quand l'utilisateur est connecté."""
    bot = current_app.config['BOT_INSTANCE']
    access_token = session['access_token']
    headers = {'Authorization': f'Bearer {access_token}'}
    
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
            owned_servers=owned_servers, 
            admin_servers=admin_servers,
            user_info=user_info,
            logged_in=True,
            # is_bot_admin est maintenant géré par le context_processor
        )
            
    except requests.exceptions.RequestException:
        session.clear()
        return redirect(url_for('public.home'))


@dashboard_bp.before_request
def before_request_func():
    """Vérifie la session et rafraîchit le token avant chaque requête du dashboard."""
    if 'access_token' not in session:
        return redirect(url_for('public.home'))
    
    if 'expires_at' in session and datetime.now().timestamp() > session['expires_at']:
        if not refresh_token():
            flash("Votre session a expiré. Veuillez vous reconnecter.", "warning")
            return redirect(url_for('public.home'))



@dashboard_bp.route('/<server_id>') # Renamed from 'dashboard' to avoid conflict with blueprint name
def server_home(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild:
        return redirect(url_for('public.home'))

    guild_details = get_guild_details(server_id)
    
    def get_dashboard_stats():
        async def _get_stats():
            db = await get_db_async()
            first_day_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            warns_cursor = await db.execute("SELECT COUNT(id) FROM warnings WHERE guild_id = ? AND timestamp >= ?", (server_id, first_day_of_month))
            monthly_warnings = await warns_cursor.fetchone()
            leaderboard_cursor = await db.execute("SELECT user_id, xp, level FROM user_levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 1", (server_id,))
            top_member_data = await leaderboard_cursor.fetchone()
            logs_cursor = await db.execute("SELECT user_id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 5", (server_id,))
            recent_logs_data = await logs_cursor.fetchall()
            await db.close()
            return monthly_warnings[0] if monthly_warnings else 0, top_member_data, recent_logs_data
        return run_async(_get_stats())

    monthly_warnings_count, top_member, recent_logs = get_dashboard_stats()

    user_ids_to_fetch = set()
    if top_member: user_ids_to_fetch.add(top_member['user_id'])
    for log in recent_logs:
        user_ids_to_fetch.add(log['user_id'])
        user_ids_to_fetch.add(log['moderator_id'])

    user_details = fetch_user_details_http(user_ids_to_fetch)
    top_member_details = user_details.get(str(top_member['user_id'])) if top_member else None

    enriched_logs = []
    for log in recent_logs:
        enriched_log = dict(log)
        enriched_log['user_details'] = user_details.get(str(log['user_id']))
        enriched_log['moderator_details'] = user_details.get(str(log['moderator_id']))
        enriched_logs.append(enriched_log)

    return render_template('dashboard.html', server=target_guild, guild_details=guild_details, monthly_warnings=monthly_warnings_count, top_member=top_member_details, recent_logs=enriched_logs, dashboard_endpoint='dashboard.server_home')


@dashboard_bp.route('/<server_id>/warnings')
def warnings(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    guild_details = get_guild_details(server_id)
    
    def get_warnings():
        async def _get_warnings():
            db = await get_db_async()
            cursor = await db.execute("SELECT id, user_id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? ORDER BY timestamp DESC", (server_id,))
            warnings = await cursor.fetchall()
            await db.close()
            return warnings
        return run_async(_get_warnings())
    
    all_warnings = get_warnings()
    user_ids = {warn['user_id'] for warn in all_warnings} | {warn['moderator_id'] for warn in all_warnings}
    user_details = fetch_user_details_http(user_ids)

    enriched_warnings = []
    for warn in all_warnings:
        enriched_warn = dict(warn)
        enriched_warn['user_details'] = user_details.get(str(warn['user_id']), {"name": "N/A", "avatar_url": ""})
        enriched_warn['moderator_details'] = user_details.get(str(warn['moderator_id']), {"name": "N/A", "avatar_url": ""})
        if isinstance(enriched_warn['timestamp'], str):
            enriched_warn['timestamp'] = datetime.fromisoformat(enriched_warn['timestamp'])
        enriched_warnings.append(enriched_warn)

    return render_template('dashboard_warnings.html', server=target_guild, warnings=enriched_warnings, guild_details=guild_details)

@dashboard_bp.route('/<server_id>/messagelogs')
def messagelogs(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    guild_details = get_guild_details(server_id)

    def get_logs():
        async def _get_logs():
            db = await get_db_async()
            cursor = await db.execute(
                "SELECT author_id, channel_id, event_type, old_content, new_content, timestamp FROM message_events WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 100",
                (server_id,)
            )
            logs = await cursor.fetchall()
            await db.close()
            return logs
        return run_async(_get_logs())

    logs = get_logs()
    author_ids = {log['author_id'] for log in logs}
    user_details = fetch_user_details_http(author_ids)

    # Récupérer les noms des salons via l'API
    headers_bot = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}
    channel_details = {}
    try:
        channels_response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers_bot)
        if channels_response.status_code == 200:
            channel_details = {c['id']: c['name'] for c in channels_response.json()}
    except requests.exceptions.RequestException:
        flash("Impossible de récupérer les noms des salons.", "warning")

    enriched_logs = []
    for log in logs:
        enriched_log = dict(log)
        enriched_log['author_details'] = user_details.get(str(log['author_id']), {"name": "N/A"})
        enriched_log['channel_name'] = channel_details.get(str(log['channel_id']), "Salon inconnu")
        if isinstance(enriched_log['timestamp'], str):
            enriched_log['timestamp'] = datetime.fromisoformat(enriched_log['timestamp'])
        enriched_logs.append(enriched_log)

    return render_template('dashboard_logs.html', server=target_guild, logs=enriched_logs, guild_details=guild_details)

@dashboard_bp.route('/<server_id>/settings', methods=['GET', 'POST'])
def settings(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    guild_details = get_guild_details(server_id)

    if request.method == 'POST':
        form_data = {
            'mod_log_channel_id': request.form.get('mod_log_channel_id') or None,
            'ticket_category_id': request.form.get('ticket_category_id') or None,
            'welcome_enabled': 1 if 'welcome_enabled' in request.form else 0,
            'welcome_channel_id': request.form.get('welcome_channel_id') or None,
            'welcome_message': request.form.get('welcome_message', 'Bienvenue {user.mention} sur {server.name} !'),
            'autorole_id': request.form.get('autorole_id') or None,
            'antispam_invites_enabled': 1 if 'antispam_invites_enabled' in request.form else 0,
            'leveling_enabled': 1 if 'leveling_enabled' in request.form else 0,
            'xp_rate': request.form.get('xp_rate', '15-25'),
            'xp_cooldown': request.form.get('xp_cooldown', 60, type=int),
            'leveling_blacklisted_channels': ",".join(request.form.getlist('blacklisted_channels'))
        }

        def save_settings():
            async def _save():
                db = await get_db_async()
                await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (server_id,))
                await db.execute("""
                    UPDATE guild_settings SET 
                        mod_log_channel_id = :mod_log_channel_id, ticket_category_id = :ticket_category_id,
                        welcome_enabled = :welcome_enabled, welcome_channel_id = :welcome_channel_id,
                        welcome_message = :welcome_message, autorole_id = :autorole_id,
                        antispam_invites_enabled = :antispam_invites_enabled, leveling_enabled = :leveling_enabled,
                        xp_rate = :xp_rate, xp_cooldown = :xp_cooldown,
                        leveling_blacklisted_channels = :leveling_blacklisted_channels
                    WHERE guild_id = :server_id
                """, {'server_id': server_id, **form_data})
                await db.commit()
                await db.close()
            run_async(_save())
        
        save_settings()
        flash("Paramètres sauvegardés avec succès !", "success")
        return redirect(url_for('dashboard.settings', server_id=server_id))

    # --- GET Request ---
    def get_settings():
        async def _get():
            db = await get_db_async()
            cursor = await db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (server_id,))
            settings = await cursor.fetchone()
            await db.close()
            return settings
        return run_async(_get())
    
    current_settings = get_settings()

    headers = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}
    text_channels, category_channels, all_roles = [], [], []
    try:
        response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers)
        if response.status_code == 200:
            all_channels = response.json()
            text_channels = [c for c in all_channels if c['type'] == 0]
            category_channels = [c for c in all_channels if c['type'] == 4]
        else:
            flash(f"Erreur API Discord ({response.status_code}) en récupérant les salons.", "danger")
        
        # La route /dashboard/<id> ne fournit pas les roles, il faut les fetcher
        roles_response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/roles", headers=headers)
        if roles_response.status_code == 200:
            all_roles = sorted(roles_response.json(), key=lambda r: r['position'], reverse=True)
        else:
            flash(f"Erreur API Discord ({roles_response.status_code}) en récupérant les rôles.", "danger")

    except requests.exceptions.RequestException as e:
        flash(f"Erreur de connexion réseau : {e}", "danger")

    return render_template(
        'dashboard_settings.html', server=target_guild, settings=current_settings,
        text_channels=text_channels, category_channels=category_channels, all_roles=all_roles,
        guild_details=guild_details
    )

@dashboard_bp.route('/<server_id>/reaction-roles', methods=['GET', 'POST'])
def reaction_roles(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    bot = current_app.config['BOT_INSTANCE']
    headers = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}

    if request.method == 'POST':
        channel_id = request.form.get('channel_id')
        embed_title = request.form.get('embed_title')
        embed_description = request.form.get('embed_description')
        role_ids = request.form.getlist('role_ids')

        if not all([channel_id, embed_title, role_ids]):
            flash("Le salon, le titre et au moins un rôle sont requis.", "danger")
            return redirect(url_for('dashboard.reaction_roles', server_id=server_id))

        async def send_reaction_role_message_async():
            try:
                channel = bot.get_channel(int(channel_id))
                if not isinstance(channel, discord.TextChannel): return False, "Salon introuvable."

                embed = discord.Embed(title=embed_title, description=embed_description, color=discord.Color.blurple())
                view = discord.ui.View(timeout=None)
                guild_roles = await channel.guild.fetch_roles()
                roles_map = {str(r.id): r for r in guild_roles}

                for role_id in role_ids:
                    role = roles_map.get(role_id)
                    if role:
                        view.add_item(discord.ui.Button(label=role.name, style=discord.ButtonStyle.secondary, custom_id=f"reaction_role_button:{role.id}"))

                await channel.send(embed=embed, view=view)
                return True, None
            except Exception as e:
                return False, str(e)

        success, error = run_async(send_reaction_role_message_async())
        if success:
            flash("Le panneau de rôle-réaction a été créé avec succès !", "success")
        else:
            flash(f"Erreur lors de la création du panneau : {error}", "danger")
        return redirect(url_for('dashboard.reaction_roles', server_id=server_id))

    # --- GET Request ---
    guild_details = get_guild_details(server_id)
    text_channels, all_roles = [], []
    try:
        response_channels = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers)
        if response_channels.ok:
            text_channels = sorted([c for c in response_channels.json() if c['type'] == 0], key=lambda c: c['name'].lower())
        
        response_roles = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/roles", headers=headers)
        if response_roles.ok:
            bot_member_response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/members/{bot.user.id}", headers=headers)
            bot_top_role_position = 0
            if bot_member_response.ok:
                bot_roles_ids = bot_member_response.json().get('roles', [])
                bot_roles_on_server = [r for r in response_roles.json() if r['id'] in bot_roles_ids]
                if bot_roles_on_server:
                    bot_top_role_position = max(r['position'] for r in bot_roles_on_server)

            all_roles = sorted(
                [r for r in response_roles.json() if not r['managed'] and r['name'] != '@everyone' and r['position'] < bot_top_role_position],
                key=lambda r: r['position'], reverse=True
            )
            for role in all_roles:
                color_int = role.get('color', 0)
                role['rgb_color'] = {'r': (color_int >> 16) & 0xFF, 'g': (color_int >> 8) & 0xFF, 'b': color_int & 0xFF}
    except requests.exceptions.RequestException as e:
        flash(f"Erreur réseau : {e}", "danger")

    return render_template('dashboard_reaction_roles.html', server=target_guild, guild_details=guild_details, text_channels=text_channels, all_roles=all_roles, reaction_role_panels=[])


@dashboard_bp.route('/<server_id>/announcement', methods=['GET', 'POST'])
def announcement(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    bot = current_app.config['BOT_INSTANCE']
    guild_details = get_guild_details(server_id)

    # On récupère les salons ici pour qu'ils soient disponibles pour le GET et le POST en cas d'erreur
    headers = {'Authorization': f'Bot {current_app.config["BOT_TOKEN"]}'}
    text_channels = []
    try:
        response = requests.get(f"https://discord.com/api/v10/guilds/{server_id}/channels", headers=headers)
        if response.ok:
            text_channels = [c for c in response.json() if c['type'] == 0]
    except requests.exceptions.RequestException as e:
        flash(f"Erreur réseau : {e}", "danger")

    if request.method == 'POST':
        channel_id = request.form.get('channel_id')
        title = request.form.get('embed_title')
        description = request.form.get('embed_description')
        color_hex = request.form.get('embed_color', '#5865F2')
        image_url = request.form.get('embed_image_url')

        if not channel_id or not (title or description):
            flash("Le salon et un titre/description sont requis.", "danger")
            # On re-render le template avec les données déjà saisies
            return render_template(
                'dashboard_announcement.html', server=target_guild, 
                guild_details=guild_details, text_channels=text_channels, 
                form_data=request.form
            )

        # --- NOUVELLE VALIDATION EN AMONT ---
        # On vérifie l'URL de l'image avant même d'essayer d'envoyer l'embed.
        if image_url and not is_valid_url(image_url):
            flash("L'URL de l'image n'est pas valide. Assurez-vous que c'est un lien direct vers une image (commençant par http:// ou https://).", "danger")
            # On retourne le template avec les données pour ne pas les perdre
            return render_template(
                'dashboard_announcement.html', server=target_guild, 
                guild_details=guild_details, text_channels=text_channels, 
                form_data=request.form
            )

        try:
            color_int = int(color_hex.lstrip('#'), 16)
        except ValueError:
            flash("Couleur hexadécimale invalide.", "danger")
            return render_template(
                'dashboard_announcement.html', server=target_guild, 
                guild_details=guild_details, text_channels=text_channels, 
                form_data=request.form
            )

        # Création d'une exception personnalisée pour la clarté
        class AnnouncementError(Exception):
            pass

        async def send_announcement_async():
            try:
                channel = bot.get_channel(int(channel_id))
                if not isinstance(channel, discord.TextChannel):
                    raise AnnouncementError("Le salon est introuvable ou n'est pas un salon textuel.")
                
                embed = discord.Embed(title=title, description=description, color=color_int)
                if image_url:
                    embed.set_image(url=image_url)
                
                await channel.send(embed=embed)
                return True
            except discord.errors.HTTPException as e:
                raise AnnouncementError(f"Erreur de l'API Discord : {e.text}") # Gère les autres erreurs API (ex: permissions manquantes)

        try:
            if run_async(send_announcement_async()):
                flash("Annonce envoyée avec succès !", "success")
                # Si l'envoi est réussi, on redirige pour vider le formulaire (pattern PRG)
                return redirect(url_for('dashboard.announcement', server_id=server_id))
        except ValueError:
            # Ce bloc est maintenant redondant car la validation se fait en amont, mais on le garde par sécurité.
            flash("Une erreur de valeur s'est produite.", "danger")
        except Exception as e:
            flash(f"Une erreur est survenue : {e}", "danger")

        # Si une erreur se produit (sauf succès), on ré-affiche le formulaire avec les données.
        return render_template('dashboard_announcement.html', server=target_guild, guild_details=guild_details, text_channels=text_channels, form_data=request.form)

    return render_template('dashboard_announcement.html', server=target_guild, guild_details=guild_details, text_channels=text_channels)


@dashboard_bp.route('/<server_id>/leaderboard')
def leaderboard(server_id):
    target_guild = check_admin_permissions(server_id)
    if not target_guild: return redirect(url_for('public.home'))

    guild_details = get_guild_details(server_id)
    
    def get_leaderboard():
        async def _get():
            db = await get_db_async()
            cursor = await db.execute("SELECT user_id, xp, level FROM user_levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 50", (server_id,))
            data = await cursor.fetchall()
            await db.close()
            return data
        return run_async(_get())
    
    leaderboard_data = get_leaderboard()
    user_ids = {user['user_id'] for user in leaderboard_data}
    user_details = fetch_user_details_http(user_ids)

    enriched_leaderboard = []
    for i, user_row in enumerate(leaderboard_data):
        details = user_details.get(str(user_row['user_id']), {"name": "N/A", "avatar_url": ""})
        enriched_leaderboard.append({
            'rank': i + 1, 'level': user_row['level'], 'xp': user_row['xp'],
            'name': details['name'], 'avatar_url': details['avatar_url']
        })

    return render_template('dashboard_leaderboard.html', server=target_guild, leaderboard=enriched_leaderboard, guild_details=guild_details)