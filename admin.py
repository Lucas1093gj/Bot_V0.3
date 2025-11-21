from flask import Blueprint, render_template, request, session, redirect, url_for, flash, current_app
import requests
from datetime import datetime
import discord
import os
import sys
import threading
from functools import wraps

from ..utils import get_db_async, run_async, is_bot_admin

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Décorateur pour protéger les routes admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_bot_admin():
            flash("Accès refusé. Vous n'avez pas les permissions nécessaires.", "danger")
            return redirect(url_for('public.home'))
        
        # S'assurer que les infos utilisateur sont bien dans la session
        if 'user_info' not in session:
            try:
                headers = {'Authorization': f'Bearer {session["access_token"]}'}
                user_info_response = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
                user_info_response.raise_for_status()
                session['user_info'] = user_info_response.json()
            except requests.exceptions.RequestException:
                flash("Impossible de vérifier votre identité. Veuillez vous reconnecter.", "warning")
                return redirect(url_for('auth.logout'))
        
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/', methods=['GET', 'POST'])
@admin_required
def dashboard():
    bot = current_app.config['BOT_INSTANCE']

    if request.method == 'POST':
        if 'maintenance_mode_submitted' in request.form:
            maintenance_mode = '1' if 'maintenance_mode' in request.form else '0'
            run_async(get_db_async().then(lambda db: db.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES ('maintenance_mode', ?)", (maintenance_mode,)).then(db.commit).then(db.close)))
            flash("Mode maintenance mis à jour.", "success")

        elif 'update_vlog_submitted' in request.form:
            vlog_content = request.form.get('update_vlog_content', '').strip()
            admin_user_info = session.get('user_info', {})
            admin_id = admin_user_info.get('id', 'Inconnu')
            admin_name = admin_user_info.get('username', 'Inconnu')
            
            async def _set_vlog():
                db = await get_db_async()
                cursor = await db.execute("SELECT value FROM global_settings WHERE key = 'update_vlog_content'")
                old_vlog_data = await cursor.fetchone()
                old_content = old_vlog_data['value'] if old_vlog_data else ""
                await db.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES ('update_vlog_content', ?)", (vlog_content,))
                await db.execute("INSERT INTO update_vlog_history (timestamp, admin_user_id, admin_user_name, old_content, new_content) VALUES (?, ?, ?, ?, ?)", (datetime.now().isoformat(), admin_id, admin_name, old_content, vlog_content))
                await db.execute("DELETE FROM update_vlog_history WHERE id NOT IN (SELECT id FROM update_vlog_history ORDER BY timestamp DESC LIMIT 5)")
                await db.commit()
                await db.close()
            run_async(_set_vlog())
            flash("Journal des mises à jour sauvegardé.", "success")

        elif 'broadcast_message' in request.form:
            message_content = request.form.get('broadcast_message')
            if not message_content:
                flash("Le message ne peut pas être vide.", "warning")
            else:
                async def broadcast_announcement_async(content):
                    embed = discord.Embed(title="📢 Annonce de l'équipe du Bot", description=content, color=discord.Color.blurple(), timestamp=datetime.now())
                    embed.set_footer(text=f"Envoyé par {bot.user.name}")
                    db = await get_db_async()
                    cursor = await db.execute("SELECT guild_id FROM guild_settings WHERE receive_broadcasts = 0")
                    opt_out_guilds = {row['guild_id'] for row in await cursor.fetchall()}
                    await db.close()
                    
                    sent_to_owners = set() # Ensemble pour suivre les propriétaires déjà contactés
                    success_count, failure_count = 0, 0
                    for guild in bot.guilds:
                        if guild.id in opt_out_guilds: continue
                        
                        # Si le propriétaire a déjà reçu le message, on passe au suivant
                        if guild.owner_id in sent_to_owners:
                            continue

                        owner = guild.owner or await bot.fetch_user(guild.owner_id)
                        if owner:
                            try:
                                await owner.send(embed=embed)
                                sent_to_owners.add(owner.id) # On ajoute l'ID au set
                                success_count += 1
                            except (discord.Forbidden, discord.HTTPException):
                                failure_count += 1
                    return success_count, failure_count
                
                success, failure = run_async(broadcast_announcement_async(message_content))
                flash(f"Annonce envoyée avec succès à {success} propriétaire(s) unique(s). Échec pour {failure} tentative(s).", "success")

        return redirect(url_for('admin.dashboard'))

    # --- GET Request ---
    def get_admin_stats():
        async def _get_stats():
            db = await get_db_async()
            pop_cmds_cursor = await db.execute("SELECT command_name, COUNT(id) as count FROM command_logs GROUP BY command_name ORDER BY count DESC LIMIT 5")
            popular_commands = await pop_cmds_cursor.fetchall()
            active_guilds_cursor = await db.execute("SELECT guild_id, COUNT(id) as count FROM command_logs WHERE guild_id IS NOT NULL GROUP BY guild_id ORDER BY count DESC LIMIT 10")
            active_guilds_data = await active_guilds_cursor.fetchall()
            logs_cursor = await db.execute("SELECT * FROM command_logs ORDER BY timestamp DESC LIMIT 100")
            command_logs = await logs_cursor.fetchall()
            maint_cursor = await db.execute("SELECT value FROM global_settings WHERE key = 'maintenance_mode'")
            maintenance_mode = await maint_cursor.fetchone()
            vlog_cursor = await db.execute("SELECT value FROM global_settings WHERE key = 'update_vlog_content'")
            update_vlog_content = await vlog_cursor.fetchone()
            vlog_history_cursor = await db.execute("SELECT * FROM update_vlog_history ORDER BY timestamp DESC LIMIT 5")
            vlog_history = await vlog_history_cursor.fetchall()
            await db.close()
            
            active_guilds = [{'name': (bot.get_guild(int(g['guild_id'])) or f"Serveur Inconnu ({g['guild_id']})").name, 'count': g['count']} for g in active_guilds_data]
            return popular_commands, active_guilds, command_logs, (maintenance_mode and maintenance_mode['value'] == '1'), (update_vlog_content['value'] if update_vlog_content else ""), vlog_history
        return run_async(_get_stats())

    popular_commands, active_guilds, command_logs, maintenance_mode_on, update_vlog_content, vlog_history = get_admin_stats()

    return render_template(
        'admin_dashboard.html',
        bot_guilds_count=len(bot.guilds),
        popular_commands=popular_commands,
        active_guilds=active_guilds,
        command_logs=command_logs,
        maintenance_mode_on=maintenance_mode_on,
        update_vlog_content=update_vlog_content,
        vlog_history=vlog_history
    )

@admin_bp.route('/user-lookup')
@admin_required
def user_lookup():
    user_id = request.args.get('user_id', type=int)
    if not user_id: return redirect(url_for('admin.dashboard'))
    
    bot = current_app.config['BOT_INSTANCE']
    user = bot.get_user(user_id)
    shared_guilds = [g for g in bot.guilds if g.get_member(user_id)] if user else []
    return render_template('admin_user_lookup.html', user=user, shared_guilds=shared_guilds)

@admin_bp.route('/restart', methods=['POST'])
@admin_required
def restart():
    flash("🚀 Le bot va redémarrer dans quelques secondes...", "info")
    def restart_script():
        threading.Timer(2.0, lambda: os.execv(sys.executable, ['python'] + sys.argv)).start()
    
    restart_thread = threading.Thread(target=restart_script)
    restart_thread.daemon = True
    restart_thread.start()
    return redirect(url_for('admin.dashboard'))