import discord
from discord import app_commands
from discord.ext import commands
import db_manager

class BotSettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Création d'un groupe de commandes pour /botannonce
    botannonce_group = app_commands.Group(name="botannonce", description="Gère les annonces globales du bot pour ce serveur.")

    @botannonce_group.command(name="start", description="Réactive la réception des annonces globales du bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reactivate_announcements(self, interaction: discord.Interaction):
        """Permet à un admin de réactiver les annonces globales."""
        guild_id = interaction.guild.id
        async with db_manager.get_db_connection() as db:
            # Utilisation de ON CONFLICT pour gérer les cas où la ligne existe déjà ou non
            await db.execute("""
                INSERT INTO guild_settings (guild_id, receive_broadcasts) VALUES (?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET receive_broadcasts = 1;
            """, (guild_id,))
            await db.commit()
        
        await interaction.response.send_message("✅ Vous recevrez de nouveau les annonces globales du bot.", ephemeral=True)

    @botannonce_group.command(name="stop", description="Désactive la réception des annonces globales du bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def deactivate_announcements(self, interaction: discord.Interaction):
        """Permet à un admin de désactiver les annonces globales."""
        guild_id = interaction.guild.id
        async with db_manager.get_db_connection() as db:
            await db.execute("""
                INSERT INTO guild_settings (guild_id, receive_broadcasts) VALUES (?, 0)
                ON CONFLICT(guild_id) DO UPDATE SET receive_broadcasts = 0;
            """, (guild_id,))
            await db.commit()

        await interaction.response.send_message("❌ Vous ne recevrez plus les annonces globales du bot. Vous pouvez les réactiver à tout moment avec `/botannonce start`.", ephemeral=True)

    @reactivate_announcements.error
    @deactivate_announcements.error
    async def on_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous devez être administrateur du serveur pour utiliser cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message("Une erreur inattendue est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotSettingsCog(bot))