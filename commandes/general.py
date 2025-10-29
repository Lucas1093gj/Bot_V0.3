import discord
import os
import sys
from discord.ext import commands
from discord import app_commands
import asyncio # NOUVEAU: Souvent implicitement nécessaire pour wait_until_ready

class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.CREATOR_ID = int(os.getenv("CREATOR_ID")) if os.getenv("CREATOR_ID") else None
        
        # --- LANCEMENT DE LA TÂCHE DE FOND ---
        self.keep_alive_loop.start()

    # --- COMMANDE 1 : /ping ---
    @app_commands.command(name="ping", description="Vérifie la latence du bot")
    async def ping(self, interaction: discord.Interaction):
        latency = self.bot.latency * 1000
        await interaction.response.send_message(f"🏓 Latence du bot : {latency:.2f} ms")

    # --- COMMANDE 2 : /restart ---
    @app_commands.command(name="restart", description="[DANGER] Redémarre le processus du bot (créateur uniquement).")
    async def restart(self, interaction: discord.Interaction):
        if interaction.user.id == self.CREATOR_ID:
            await interaction.response.send_message("Redémarrage du bot...", ephemeral=True)
            print(f"[Restart] {interaction.user} a redémarré le bot.")
            await self.bot.close()
            # os.execv est une manière propre de redémarrer le script
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            await interaction.response.send_message("❌ Vous n'avez pas la permission d'exécuter cette commande.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))