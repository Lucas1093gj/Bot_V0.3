#import
import discord
import os
import asyncio

#import des utilitaires
from discord.ext import commands
from dotenv import load_dotenv
import db_manager # Import du module de base de données

#chargement des variables d'environnement depuis le fichier .env
load_dotenv()

#chargement des variables d'environnement
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
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

    # Créer un état partagé pour les cogs de musique/radio
    bot.music_queues = {}
    bot.bot_volume_levels = {}
    bot.loop_states = {}

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

#lancement du bot
bot.run(DISCORD_TOKEN)