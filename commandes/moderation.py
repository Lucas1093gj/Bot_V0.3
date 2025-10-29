import discord
import sqlite3
from discord.ext import commands
from discord import app_commands
import datetime
import re

def parse_duration(duration_string: str) -> datetime.timedelta | None:
    """
    Analyse une chaîne de durée (ex: "1d12h30m5s") et la convertit en timedelta.
    Unités supportées : d (jours), h (heures), m (minutes), s (secondes).
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
        self.db_conn = bot.db_conn # Récupère la connexion depuis l'instance du bot

    def cog_unload(self):
        pass # La connexion est maintenant gérée par main.py

    @app_commands.command(name="clear", description="Supprime un nombre de messages dans le salon.")
    @app_commands.describe(nombre="Le nombre de messages à supprimer (entre 1 et 100).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"✅ {len(deleted)} messages ont été supprimés.", ephemeral=True)

    @app_commands.command(name="warn", description="Avertit un membre.")
    @app_commands.describe(membre="Le membre à avertir.", raison="La raison de l'avertissement.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        if membre.bot:
            await interaction.response.send_message("❌ Vous ne pouvez pas avertir un bot.", ephemeral=True)
            return
        if membre.id == interaction.user.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas vous avertir vous-même.", ephemeral=True)
            return

        cursor = self.db_conn.cursor()
        cursor.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                       (interaction.guild.id, membre.id, interaction.user.id, raison))
        self.db_conn.commit()

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

    @app_commands.command(name="warnings", description="Affiche l'historique des avertissements d'un membre.")
    @app_commands.describe(membre="Le membre dont vous voulez voir les avertissements.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, membre: discord.Member):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC",
                       (interaction.guild.id, membre.id))
        records = cursor.fetchall()

        if not records:
            await interaction.response.send_message(f"✅ {membre.display_name} n'a aucun avertissement.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Historique des avertissements de {membre.display_name}",
            color=discord.Color.blue()
        )

        for mod_id, reason, ts in records[:25]: # Limite à 25 pour ne pas surcharger l'embed
            moderator = interaction.guild.get_member(mod_id) or f"ID: {mod_id}"
            timestamp = discord.utils.format_dt(datetime.datetime.fromisoformat(ts), style='f')
            embed.add_field(
                name=f"Le {timestamp.split('à')[0]}",
                value=f"**Raison**: {reason}\n**Modérateur**: {moderator}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="mute", description="Empêche un membre de parler pour une durée définie.")
    @app_commands.describe(
        membre="Le membre à rendre muet.",
        duree="La durée du mute (ex: 10s, 5m, 2h, 1d). Max 28 jours.",
        raison="La raison du mute."
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, duree: str, raison: str):
        if membre.id == interaction.user.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas vous rendre muet vous-même.", ephemeral=True)
            return
        if membre.top_role >= interaction.user.top_role and interaction.guild.owner != interaction.user:
            await interaction.response.send_message("❌ Vous ne pouvez pas rendre muet un membre ayant un rôle égal ou supérieur au vôtre.", ephemeral=True)
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
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour rendre ce membre muet. Mon rôle est-il assez haut ?", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Une erreur est survenue : {e}", ephemeral=True)

    @app_commands.command(name="unmute", description="Retire le mute d'un membre.")
    @app_commands.describe(membre="Le membre dont il faut retirer le mute.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member):
        if membre.is_timed_out():
            await membre.timeout(None, reason=f"Unmute par {interaction.user.name}")
            await interaction.response.send_message(f"✅ {membre.mention} n'est plus muet.", ephemeral=False)
        else:
            await interaction.response.send_message(f"❌ Ce membre n'est pas muet.", ephemeral=True)

    @clear.error
    @warn.error
    @warnings.error
    @mute.error
    @unmute.error
    async def moderation_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous n'avez pas les permissions nécessaires pour cette commande.", ephemeral=True)
        else:
            print(f"Erreur dans ModerationCog: {error}")
            await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))