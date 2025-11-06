import discord
import sqlite3
import io
import asyncio
from discord.ext import commands, tasks
import os
from discord import app_commands

class LoggerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # File d'attente pour stocker les logs avant de les écrire dans la DB
        self.log_queue = asyncio.Queue()
        # Tâche en arrière-plan pour traiter la file d'attente
        self.db_writer_task.start()

    def cog_unload(self):
        # Arrêter proprement la tâche en arrière-plan
        self.db_writer_task.cancel()

    async def flush_logs(self):
        """Force l'écriture de tous les logs restants dans la file d'attente."""
        await self.db_writer_task()

    @tasks.loop(seconds=5.0)
    async def db_writer_task(self):
        """Tâche qui s'exécute en continu pour écrire les logs dans la base de données."""
        if self.log_queue.empty():
            return

        # Utiliser une nouvelle connexion pour cette tâche pour éviter les conflits
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        
        # Traiter tous les éléments actuellement dans la file d'attente
        logs_to_process = []
        while not self.log_queue.empty():
            logs_to_process.append(await self.log_queue.get())

        cursor.executemany("INSERT INTO message_events (guild_id, channel_id, author_id, event_type, old_content, new_content) VALUES (?, ?, ?, ?, ?, ?)", logs_to_process)
        conn.commit()
        conn.close()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # On ignore les messages du bot et les DMs
        if message.author.bot or message.guild is None:
            return
        # Ajouter l'événement à la file d'attente au lieu d'écrire directement
        await self.log_queue.put((message.guild.id, message.channel.id, message.author.id, 'deleted', message.content, None))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # On ignore les bots, les DMs, et les "fausses" modifications (ex: ajout d'un embed)
        if before.author.bot or before.guild is None or before.content == after.content:
            return

        # Ajouter l'événement à la file d'attente
        await self.log_queue.put((before.guild.id, before.channel.id, before.author.id, 'edited', before.content, after.content))

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