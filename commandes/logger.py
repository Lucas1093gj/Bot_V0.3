import discord
import sqlite3
import io
from discord.ext import commands
import os
from discord import app_commands

class LoggerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_conn = bot.db_conn # Récupère la connexion depuis l'instance du bot

    def cog_unload(self):
        pass # La connexion est maintenant gérée par main.py

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # On ignore les messages du bot et les DMs
        if message.author.bot or message.guild is None:
            return

        cursor = self.db_conn.cursor()
        cursor.execute("INSERT INTO message_events (guild_id, channel_id, author_id, event_type, old_content) VALUES (?, ?, ?, ?, ?)",
                       (message.guild.id, message.channel.id, message.author.id, 'deleted', message.content))
        self.db_conn.commit()

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # On ignore les bots, les DMs, et les "fausses" modifications (ex: ajout d'un embed)
        if before.author.bot or before.guild is None or before.content == after.content:
            return

        cursor = self.db_conn.cursor()
        cursor.execute("INSERT INTO message_events (guild_id, channel_id, author_id, event_type, old_content, new_content) VALUES (?, ?, ?, ?, ?, ?)",
                       (before.guild.id, before.channel.id, before.author.id, 'edited', before.content, after.content))
        self.db_conn.commit()

    @app_commands.command(name="getlog", description="Récupère l'historique des messages modifiés/supprimés.")
    @app_commands.checks.has_permissions(administrator=True)
    async def getlog(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT author_id, channel_id, event_type, old_content, new_content, timestamp FROM message_events WHERE guild_id = ? ORDER BY timestamp ASC", (guild.id,))
        logs = cursor.fetchall()

        if not logs:
            await interaction.followup.send("Aucun message supprimé ou modifié n'a été enregistré pour ce serveur.", ephemeral=True)
            return

        # Création d'un fichier de base de données temporaire
        db_filename = f"logs-{guild.name.replace(' ', '_')}.db"
        
        try:
            temp_conn = sqlite3.connect(db_filename)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute('''
                CREATE TABLE event_logs (
                    timestamp DATETIME,
                    event_type TEXT,
                    channel_name TEXT,
                    author_name TEXT,
                    old_content TEXT,
                    new_content TEXT
                )
            ''')

            for author_id, channel_id, event_type, old_content, new_content, timestamp in logs:
                author = guild.get_member(author_id) or await self.bot.fetch_user(author_id)
                author_name = str(author) if author else f"Utilisateur inconnu (ID: {author_id})"
                
                channel = guild.get_channel(channel_id)
                channel_name = f"#{channel.name}" if channel else f"Salon inconnu (ID: {channel_id})"

                temp_cursor.execute("INSERT INTO event_logs (timestamp, event_type, channel_name, author_name, old_content, new_content) VALUES (?, ?, ?, ?, ?, ?)",
                                   (timestamp, event_type, channel_name, author_name, old_content, new_content))

            temp_conn.commit()
            temp_conn.close()

            # Envoi du fichier .db
            await interaction.followup.send(
                "Voici l'historique des messages du serveur. Vous pouvez l'ouvrir avec un logiciel comme 'DB Browser for SQLite'.",
                file=discord.File(db_filename),
                ephemeral=True
            )

        finally:
            # Nettoyage : suppression du fichier temporaire après envoi
            if os.path.exists(db_filename):
                os.remove(db_filename)

    @getlog.error
    async def getlog_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Une erreur est survenue: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))