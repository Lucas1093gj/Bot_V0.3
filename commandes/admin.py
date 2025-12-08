import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import threading
from discord.ext import commands
from discord import app_commands

# --- Vérification personnalisée ---
# On récupère la liste des IDs admin depuis le fichier .env
ADMIN_BOT_IDS = {int(s.strip()) for s in os.getenv("ADMIN_BOT_IDS", "").split(',') if s.strip()}

def is_bot_admin():
    """Vérifie si l'utilisateur qui exécute la commande est dans la liste des admins du bot."""
    return app_commands.check(lambda interaction: interaction.user.id in ADMIN_BOT_IDS)

class AdminCog(commands.Cog):
    """Cog pour les commandes réservées aux administrateurs du bot."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="restart", description="[Admin Bot] Redémarre le bot.")
    @is_bot_admin() # On utilise notre nouvelle vérification personnalisée
    async def restart(self, interaction: discord.Interaction):
        """Redémarre le processus du bot."""
        # AVERTISSEMENT : Cette méthode de redémarrage peut être instable sur certains systèmes d'exploitation
        # et n'est pas recommandée en production. Un gestionnaire de processus externe (comme systemd ou un script shell) est plus robuste.
        await interaction.response.send_message("🚀 Le bot va redémarrer dans quelques secondes...", ephemeral=True)
        
        # La logique de redémarrage doit être non-bloquante pour que la réponse Discord soit envoyée.
        # On utilise un thread pour lancer le redémarrage après un court délai.
        def restart_script():
            # Attend 2 secondes avant de redémarrer pour laisser le temps à la réponse d'être envoyée
            threading.Timer(2.0, lambda: os.execv(sys.executable, ['python'] + sys.argv)).start()
        
        restart_thread = threading.Thread(target=restart_script)
        restart_thread.daemon = True
        restart_thread.start()

# Fonction setup essentielle pour que le bot puisse charger ce cog
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
