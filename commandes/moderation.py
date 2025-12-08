import discord
from discord.ext import commands
from discord import app_commands
import datetime
import re
import aiosqlite
from db_manager import get_db_connection

def parse_duration(duration_string: str) -> datetime.timedelta | None:
    """
    Convertit une chaîne de durée simple (ex: "1d12h30m5s") en un objet `timedelta` utilisable par Python.
    """
    regex = re.compile(r'(\d+)([smhd])')
    parts = regex.findall(duration_string.lower())
    if not parts:
        return None
    
    time_params = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    unit_map = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    for value, unit in parts:
        time_params[unit_map[unit]] += int(value)
        
    return datetime.timedelta(**time_params)

class ModerationCog(commands.Cog, name="Modération"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Gère l'arrivée d'un nouveau membre, en lui envoyant un message de bienvenue et/ou en lui attribuant un rôle automatique."""
        guild = member.guild

        # Récupérer les paramètres du serveur depuis la base de données
        settings = None
        async with get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT welcome_enabled, welcome_channel_id, welcome_message, autorole_id 
                FROM guild_settings 
                WHERE guild_id = ?
            """, (guild.id,)) as cursor:
                settings = await cursor.fetchone()

        if not settings:
            return # Pas de paramètres pour ce serveur

        # 1. Gestion du message de bienvenue
        if settings['welcome_enabled'] and settings['welcome_channel_id']:
            welcome_channel = guild.get_channel(settings['welcome_channel_id'])
            if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
                
                # On remplace les placeholders comme {user.mention} par les vraies valeurs.
                message = settings['welcome_message'] or "Bienvenue {user.mention} sur {server.name} !"
                formatted_message = message.replace('{user.mention}', member.mention).replace('{user.name}', member.name).replace('{server.name}', guild.name).format(
                    user=member,
                    server=guild,
                    user_mention=member.mention,
                    user_name=member.name,
                    server_name=guild.name
                )

                try:
                    await welcome_channel.send(formatted_message)
                except discord.Forbidden:
                    print(f"Permissions manquantes pour envoyer le message de bienvenue dans {welcome_channel.name} ({guild.name})")

        # 2. Gestion de l'autorole
        if settings['autorole_id']:
            role_to_give = guild.get_role(settings['autorole_id'])
            if role_to_give and role_to_give < guild.me.top_role:
                try:
                    await member.add_roles(role_to_give, reason="Autorole à l'arrivée")
                except discord.Forbidden:
                    print(f"Permissions manquantes pour donner l'autorole {role_to_give.name} ({guild.name})")

    async def _log_action(self, interaction: discord.Interaction, embed: discord.Embed):
        """Fonction interne pour envoyer un embed de log dans le salon de modération configuré pour le serveur."""
        async with get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT mod_log_channel_id FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                record = await cursor.fetchone()
        
        if record and record['mod_log_channel_id']:
            log_channel = self.bot.get_channel(record['mod_log_channel_id'])
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    print(f"Permissions manquantes pour envoyer des logs dans le salon {log_channel.id} du serveur {interaction.guild.id}")
                except discord.HTTPException as e:
                    print(f"Erreur HTTP lors de l'envoi des logs: {e}")

    @app_commands.command(name="clear", description="Supprime un nombre de messages dans le salon.")
    @app_commands.describe(nombre="Le nombre de messages à supprimer (entre 1 et 100).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
        """Supprime un certain nombre de messages dans le salon actuel."""
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"✅ {len(deleted)} messages ont été supprimés.", ephemeral=True)

        # Journalisation de l'action
        log_embed = discord.Embed(
            title="🗑️ Messages Supprimés (Clear)",
            color=discord.Color.light_grey(),
            timestamp=datetime.datetime.now()
        )
        log_embed.add_field(name="Salon", value=interaction.channel.mention, inline=True)
        log_embed.add_field(name="Nombre", value=f"{len(deleted)} messages", inline=True)
        log_embed.add_field(name="Exécuté par", value=interaction.user.mention, inline=True)
        await self._log_action(interaction, log_embed)

    @app_commands.command(name="warn", description="Avertit un membre.")
    @app_commands.describe(membre="Le membre à avertir.", raison="La raison de l'avertissement.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        """Avertit un membre et enregistre l'avertissement dans la base de données."""
        if membre.bot:
            await interaction.response.send_message("❌ Vous ne pouvez pas avertir un bot.", ephemeral=True)
            return
        if membre.id == interaction.user.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas vous avertir vous-même.", ephemeral=True)
            return

        # --- Vérification de la hiérarchie des rôles ---
        # L'auteur de la commande est-il le propriétaire du serveur ? Si oui, il peut tout faire.
        is_owner = interaction.user.id == interaction.guild.owner_id
        
        # 1. On ne peut pas sanctionner quelqu'un avec un rôle supérieur ou égal au sien (sauf si on est propriétaire)
        if not is_owner and membre.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ Vous ne pouvez pas avertir un membre ayant un rôle égal ou supérieur au vôtre.", ephemeral=True)
            return
        # 2. Le bot ne peut pas sanctionner quelqu'un avec un rôle supérieur ou égal au sien
        if membre.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Je ne peux pas avertir ce membre car son rôle est supérieur ou égal au mien. Veuillez remonter mon rôle dans la hiérarchie.", ephemeral=True)
            return

        async with get_db_connection() as conn:
            await conn.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                               (interaction.guild.id, membre.id, interaction.user.id, raison))
            await conn.commit()

        embed = discord.Embed(
            title="Nouvel Avertissement",
            description=f"Vous avez été averti sur le serveur **{interaction.guild.name}**.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Averti par : {interaction.user.display_name}")
        
        try:
            await membre.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(f"✅ {membre.mention} a été averti. (Impossible de lui envoyer un DM)", ephemeral=False)
        else:
            await interaction.response.send_message(f"✅ {membre.mention} a été averti. (DM envoyé)", ephemeral=False)

        # Journalisation de l'action
        log_embed = discord.Embed(
            title="⚖️ Membre Averti",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now()
        )
        log_embed.add_field(name="Membre", value=f"{membre.mention} (`{membre.id}`)", inline=False)
        log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="Raison", value=raison, inline=False)
        await self._log_action(interaction, log_embed)

    @app_commands.command(name="warnings", description="Affiche l'historique des avertissements d'un membre.")
    @app_commands.describe(utilisateur="Le membre (ou son ID) dont vous voulez voir les avertissements.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, utilisateur: str):
        """Affiche l'historique des avertissements d'un membre sur le serveur."""
        try:
            # Essayer de convertir en ID d'entier
            user_id = int(utilisateur)
            target_user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except (ValueError, discord.NotFound):
            # Si ça échoue, essayer de trouver un membre par son nom/mention
            try:
                target_user = await commands.MemberConverter().convert(interaction, utilisateur)
            except commands.MemberNotFound:
                await interaction.response.send_message(f"❌ Utilisateur `{utilisateur}` introuvable.", ephemeral=True)
                return

        records = []
        async with get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC", (interaction.guild.id, target_user.id)) as cursor:
                records = await cursor.fetchall()

        if not records:
            await interaction.response.send_message(f"✅ `{target_user.display_name}` n'a aucun avertissement sur ce serveur.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Historique des avertissements de {target_user.display_name}",
            color=discord.Color.blue()
        )

        for warn_id, mod_id, reason, ts in records[:25]: # On limite à 25 pour ne pas surcharger l'embed.
            moderator = interaction.guild.get_member(mod_id) or f"ID: {mod_id}"
            timestamp = discord.utils.format_dt(datetime.datetime.fromisoformat(ts), style='f')
            embed.add_field(
                name=f"Avertissement ID: {warn_id} (Le {timestamp.split('à')[0]})",
                value=f"**Raison**: {reason}\n**Modérateur**: {moderator}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delwarn", description="Supprime un avertissement par son ID.")
    @app_commands.describe(warn_id="L'ID de l'avertissement à supprimer (visible avec /warnings).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def delwarn(self, interaction: discord.Interaction, warn_id: int):
        """Supprime un avertissement spécifique en utilisant son ID."""
        record = None
        async with get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT user_id FROM warnings WHERE id = ? AND guild_id = ?", (warn_id, interaction.guild.id)) as cursor:
                # On vérifie que l'avertissement existe et qu'il appartient bien à ce serveur.
                record = await cursor.fetchone()

        if not record:
            await interaction.response.send_message(f"❌ Aucun avertissement avec l'ID `{warn_id}` n'a été trouvé sur ce serveur.", ephemeral=True)
            return

        user_id = record['user_id']
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM warnings WHERE id = ?", (warn_id,))
            await conn.commit()

        # On essaie de retrouver l'utilisateur pour afficher un message plus clair.
        try:
            target_user = await self.bot.fetch_user(user_id)
            user_display = target_user.mention
        except discord.NotFound:
            user_display = f"l'utilisateur avec l'ID `{user_id}`"

        embed = discord.Embed(title="🗑️ Avertissement Supprimé", color=discord.Color.green())
        embed.description = f"L'avertissement avec l'ID `{warn_id}` pour {user_display} a été supprimé par {interaction.user.mention}."
        
        await interaction.response.send_message(embed=embed)

        # Journalisation de l'action
        log_embed = discord.Embed(
            title="♻️ Avertissement Supprimé",
            color=discord.Color.dark_green(),
            timestamp=datetime.datetime.now()
        )
        log_embed.description = f"L'avertissement `{warn_id}` pour {user_display} a été supprimé."
        log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
        await self._log_action(interaction, log_embed)

    @app_commands.command(name="mute", description="Empêche un membre de parler pour une durée définie.")
    @app_commands.describe(
        membre="Le membre à rendre muet.",
        duree="La durée du mute (ex: 10s, 5m, 2h, 1d). Max 28 jours.",
        raison="La raison du mute."
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, duree: str, raison: str):
        """Empêche un membre de parler et d'interagir pour une durée définie (timeout)."""
        if membre.id == interaction.user.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas vous rendre muet vous-même.", ephemeral=True)
            return

        # --- Vérification de la hiérarchie des rôles ---
        is_owner = interaction.user.id == interaction.guild.owner_id
        if not is_owner and membre.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ Vous ne pouvez pas rendre muet un membre ayant un rôle égal ou supérieur au vôtre.", ephemeral=True)
            return
        
        if membre.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Je ne peux pas rendre ce membre muet car son rôle est supérieur ou égal au mien. Veuillez remonter mon rôle dans la hiérarchie.", ephemeral=True)
            return

        delta = parse_duration(duree)
        if delta is None:
            await interaction.response.send_message("❌ Format de durée invalide. Utilisez `s`, `m`, `h`, ou `d` (ex: `10m`, `2h30m`).", ephemeral=True)
            return
        
        if delta > datetime.timedelta(days=28):
            await interaction.response.send_message("❌ La durée du mute ne peut pas dépasser 28 jours.", ephemeral=True)
            return

        try:
            await membre.timeout(delta, reason=raison)
            
            embed = discord.Embed(
                title="Membre rendu muet",
                description=f"Vous avez été rendu muet sur le serveur **{interaction.guild.name}**.",
                color=discord.Color.red()
            )
            embed.add_field(name="Raison", value=raison)
            embed.add_field(name="Durée", value=duree)
            await membre.send(embed=embed)

            await interaction.response.send_message(f"✅ {membre.mention} a été rendu muet pour **{duree}**.", ephemeral=False)

            # Journalisation de l'action
            log_embed = discord.Embed(
                title="🔇 Membre Rendu Muet",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            log_embed.add_field(name="Membre", value=f"{membre.mention} (`{membre.id}`)", inline=False)
            log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            log_embed.add_field(name="Durée", value=duree, inline=True)
            log_embed.add_field(name="Raison", value=raison, inline=True)
            await self._log_action(interaction, log_embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour rendre ce membre muet. Mon rôle est-il assez haut ?", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Une erreur est survenue : {e}", ephemeral=True)

    @app_commands.command(name="unmute", description="Retire le mute d'un membre.")
    @app_commands.describe(membre="Le membre dont il faut retirer le mute.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member):
        """Retire le 'timeout' d'un membre, lui permettant de parler à nouveau."""
        if membre.is_timed_out():
            await membre.timeout(None, reason=f"Unmute par {interaction.user.name}")
            await interaction.response.send_message(f"✅ {membre.mention} n'est plus muet.", ephemeral=False)

            # Journalisation de l'action
            log_embed = discord.Embed(
                title="🔊 Mute Retiré",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            log_embed.add_field(name="Membre", value=f"{membre.mention} (`{membre.id}`)", inline=False)
            log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            await self._log_action(interaction, log_embed)
        else:
            await interaction.response.send_message(f"❌ Ce membre n'est pas muet.", ephemeral=True)

    @app_commands.command(name="lock", description="Verrouille un salon, empêchant les membres de parler.")
    @app_commands.describe(salon="Le salon à verrouiller (par défaut, le salon actuel).", raison="Raison du verrouillage.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, salon: discord.TextChannel = None, raison: str = "Aucune raison spécifiée"):
        """Verrouille un salon, empêchant les membres (rôle @everyone) d'y envoyer des messages."""
        target_channel = salon or interaction.channel
        overwrite = target_channel.overwrites_for(interaction.guild.default_role)

        if overwrite.send_messages is False:
            await interaction.response.send_message("🔒 Ce salon est déjà verrouillé.", ephemeral=True)
            return

        overwrite.send_messages = False
        try:
            await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Lock par {interaction.user}: {raison}")
            await interaction.response.send_message(f"🔒 Le salon {target_channel.mention} a été verrouillé.", ephemeral=True)
            await target_channel.send(f"🔒 **SALON VERROUILLÉ** par {interaction.user.mention}.")

            # Journalisation de l'action
            log_embed = discord.Embed(title="🔒 Salon Verrouillé", color=discord.Color.dark_grey(), timestamp=datetime.datetime.now())
            log_embed.add_field(name="Salon", value=target_channel.mention, inline=False)
            log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            log_embed.add_field(name="Raison", value=raison, inline=False)
            await self._log_action(interaction, log_embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour modifier ce salon.", ephemeral=True)

    @app_commands.command(name="unlock", description="Déverrouille un salon, autorisant les membres à parler.")
    @app_commands.describe(salon="Le salon à déverrouiller (par défaut, le salon actuel).", raison="Raison du déverrouillage.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, salon: discord.TextChannel = None, raison: str = "Aucune raison spécifiée"):
        """Déverrouille un salon, autorisant à nouveau les membres à y parler."""
        target_channel = salon or interaction.channel
        overwrite = target_channel.overwrites_for(interaction.guild.default_role)

        if overwrite.send_messages is not False:
            await interaction.response.send_message("🔓 Ce salon n'est pas verrouillé.", ephemeral=True)
            return

        overwrite.send_messages = None  # `None` rétablit la permission par défaut (héritée de la catégorie).
        try:
            await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Unlock par {interaction.user}: {raison}")
            await interaction.response.send_message(f"🔓 Le salon {target_channel.mention} a été déverrouillé.", ephemeral=True)
            await target_channel.send(f"🔓 **SALON DÉVERROUILLÉ**.")

            # Journalisation de l'action
            log_embed = discord.Embed(title="🔓 Salon Déverrouillé", color=discord.Color.from_rgb(124, 252, 0), timestamp=datetime.datetime.now()) # Vert lime
            log_embed.add_field(name="Salon", value=target_channel.mention, inline=False)
            log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=False)
            await self._log_action(interaction, log_embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour modifier ce salon.", ephemeral=True)

    @clear.error
    @warn.error
    @warnings.error
    @delwarn.error
    @mute.error
    @unmute.error
    @lock.error
    @unlock.error
    async def moderation_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Gestionnaire d'erreurs centralisé pour le cog de modération."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous n'avez pas les permissions nécessaires pour cette commande.", ephemeral=True)
        else:
            print(f"Erreur dans ModerationCog: {error}")
            if interaction.response.is_done(): # Si on a déjà répondu (ex: avec defer()), on utilise followup.
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))