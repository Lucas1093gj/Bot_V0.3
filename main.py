#import
import discord
import os
import asyncio # noqa
from dotenv import load_dotenv

#chargement des variables d'environnement depuis le fichier .env (DOIT ÊTRE FAIT AVANT LES AUTRES IMPORTS)
load_dotenv()

#import des utilitaires
from discord.ext import commands

import db_manager # Import du module de base de données

#chargement des variables d'environnement depuis le fichier .env
load_dotenv()

#chargement des variables d'environnement
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Import des vues persistantes et des fonctions de configuration (après load_dotenv)
from commandes.discordmaker import VerificationView, RoleMenuView, SELF_ASSIGNABLE_ROLES, load_config as load_dm_config
from commandes.music import MusicControls

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not DISCORD_TOKEN:
    print("[ERREUR] Le token Discord n'est pas défini. Veuillez vérifier votre fichier .env.")
    exit()

# Initialisation de la base de données avant de lancer le bot
print("[Startup] Initialisation de la base de données...")
db_manager.initialize_database()

#initialisation du bot
# On active tous les intents pour plus de simplicité, mais en production,
# il est recommandé de n'activer que ceux qui sont strictement nécessaires.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

#événement de démarrage
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    
    # Attacher la connexion DB au bot pour un accès global
    bot.db_conn = db_manager.get_db_connection()

    # Créer un état partagé pour le cog de musique.
    bot.music_states = {}
    
    # Verrou pour les opérations critiques qui ne doivent pas être interrompues
    bot.critical_operation_lock = asyncio.Lock()

    # --- Ré-enregistrement des vues persistantes ---
    print("[Startup] Ré-enregistrement des vues persistantes...")
    # Vue pour la vérification et les rôles de DiscordMaker
    for guild in bot.guilds:
        dm_config = load_dm_config(guild.id)
        if dm_config.get("verification_system") == "enabled":
            bot.add_view(VerificationView())
        
        assignable_roles = [role for role in dm_config.get("roles", []) if role in SELF_ASSIGNABLE_ROLES]
        if assignable_roles:
            bot.add_view(RoleMenuView(assignable_roles, bot))

    # Vues pour le contrôle de la musique
    bot.add_view(MusicControls(bot.get_cog("MusicCog")))

    try:
        # Charger toutes les extensions (Cogs) du dossier 'commandes'
        for filename in os.listdir('./commandes'):
            if filename.endswith('.py'):
                await bot.load_extension(f'commandes.{filename[:-3]}')
                print(f"-> Cog '{filename[:-3]}' chargé.")
        
        synced = await bot.tree.sync()
        print(f"{len(synced)} commande(s) synchronisée(s) globalement.")
    except Exception as e:
        print(f"Erreur lors du chargement/synchronisation : {e}")

# On s'assure de fermer la connexion à la DB quand le bot s'arrête
@bot.event
async def close(): # L'événement 'close' est plus fiable que 'on_disconnect'
    if hasattr(bot, 'db_conn') and bot.db_conn:
        bot.db_conn.close()
        print("[Shutdown] Connexion à la base de données fermée.")


print("Le bot démarre...")

#lancement du bot
bot.run(DISCORD_TOKEN)