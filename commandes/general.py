import discord
from discord import app_commands
from discord.ext import commands
import os

class GeneralCog(commands.Cog, name="General"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dashboard", description="Envoie un lien privé pour accéder au tableau de bord web.")
    async def dashboard(self, interaction: discord.Interaction):
        dashboard_url = os.getenv("WEB_BASE_URL", "http://127.0.0.1:5000")
        embed = discord.Embed(
            title="🌐 Accès au Tableau de Bord",
            description=f"Cliquez sur le bouton ci-dessous pour ouvrir le tableau de bord et gérer vos serveurs.",
            color=discord.Color.green()
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ouvrir le Dashboard", style=discord.ButtonStyle.link, url=dashboard_url))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))