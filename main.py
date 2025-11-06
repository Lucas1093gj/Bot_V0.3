#import
import discord
import os
import asyncio # noqa
import datetime

#chargement des variables d'environnement depuis le fichier .env (DOIT ÊTRE FAIT AVANT LES AUTRES IMPORTS)
from dotenv import load_dotenv
load_dotenv()

#import des utilitaires
import wavelink
from discord.ext import commands

from discord.ext import tasks
import db_manager # Import du module de base de données

#chargement des variables d'environnement depuis le fichier .env
load_dotenv()

#chargement des variables d'environnement
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CREATOR_ID = os.getenv("CREATOR_ID")
# Import des vues persistantes et des fonctions de configuration (après load_dotenv)
from commandes.discordmaker import VerificationView, RoleMenuView, SELF_ASSIGNABLE_ROLES, load_config as load_dm_config
from commandes.music import MusicControls

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
bot.critical_operation_lock = asyncio.Lock()

# --- Configuration Lavalink ---
LAVALINK_NODES = [
    # Utilisation d'adresses IP directes pour contourner les problèmes de DNS sur le Raspberry Pi.
    # Ces serveurs sont compatibles v4.
    # Nœuds convertis en IP pour une meilleure compatibilité avec le Raspberry Pi.
    {"host": "135.148.14.16", "port": 80, "password": "youshallnotpass", "secure": False, "region": "LavaLink-EU-IP"},
    {"host": "154.53.56.226", "port": 80, "password": "DevamOP", "secure": False, "region": "DevamOP-IN-IP"},
    {"host": "194.163.189.229", "port": 80, "password": "horizxon.studio", "secure": False, "region": "Horizxon-US-IP"},
    {"host": "5.39.63.207", "port": 8893, "password": "https://discord.gg/mjS5J2K3ep", "secure": False, "region": "AneFaiz-EU-IP"},
]

@bot.event
async def on_wavelink_inactive_node(node: wavelink.Node):
    """Événement déclenché lorsqu'un nœud Lavalink devient inactif."""
    print(f"[Lavalink - ERREUR] Le nœud '{node.identifier}' est devenu inactif. Wavelink tentera de se reconnecter.")
    if CREATOR_ID:
        creator = await bot.fetch_user(int(CREATOR_ID))
        if creator:
            await creator.send(f"⚠️ **Alerte Bot** ⚠️\nLe nœud Lavalink `{node.identifier}` est déconnecté ou ne répond plus.")

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    """Événement déclenché quand un nœud Lavalink est prêt."""
    node = payload.node
    print(f"[Lavalink - INFO] Le nœud '{node.identifier}' est prêt. Session ID: {payload.session_id}")


@bot.event
async def setup_hook():
    """Ce hook est appelé avant on_ready, idéal pour initialiser des services."""
    # Connexion à la base de données
    bot.db_conn = db_manager.get_db_connection()
    print("[Startup] Connexion à la base de données établie.")
    
    # Création et connexion initiale aux noeuds Lavalink
    nodes = []
    for config in LAVALINK_NODES:
        nodes.append(wavelink.Node(
            uri=f"{'https' if config['secure'] else 'http'}://{config['host']}:{config['port']}",
            password=config['password'],
            identifier=config.get('region', config['host']) # Utilise la région comme identifiant pour plus de clarté
        ))
    await wavelink.Pool.connect(nodes=nodes, client=bot, cache_capacity=100)

    # Chargement des Cogs (extensions)
    print("[Startup] Chargement des Cogs...")
    for filename in os.listdir('./commandes'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'commandes.{filename[:-3]}')
                print(f"-> Cog '{filename[:-3]}' chargé.")
            except Exception as e:
                print(f"[ERREUR] Échec du chargement du cog {filename[:-3]}: {e}")
    
    # Synchronisation des commandes slash
    synced = await bot.tree.sync()
    print(f"[Startup] {len(synced)} commande(s) synchronisée(s) globalement.")

#événement de démarrage
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

    # --- Ré-enregistrement des vues persistantes ---
    print("[Startup] Ré-enregistrement des vues persistantes...")
    # Vue pour la vérification et les rôles de DiscordMaker
    for guild in bot.guilds:
        dm_config = load_dm_config(guild.id)
        if dm_config.get("verification_system") == "enabled":
            bot.add_view(VerificationView())
        
        assignable_roles = [role for role in dm_config.get("roles", []) if role in SELF_ASSIGNABLE_ROLES] # noqa
        if assignable_roles:
            bot.add_view(RoleMenuView(assignable_roles))

    # La vue MusicControls est déjà persistante et ajoutée dans le cog music.
    # La ré-ajouter ici peut causer des doublons de listeners.
    # Si elle est bien définie avec un custom_id et ajoutée dans le cog_load du cog musique,
    # cette ligne n'est pas nécessaire. Pour plus de sécurité, on peut la laisser.
    bot.add_view(MusicControls())

# On s'assure de fermer la connexion à la DB quand le bot s'arrête
@bot.event
async def close():
    # Vider la file d'attente du logger une dernière fois
    logger_cog = bot.get_cog("LoggerCog")
    if logger_cog:
        print("[Shutdown] Écriture des logs restants...")
        await logger_cog.flush_logs()

    # Nettoyer les connexions
    if hasattr(bot, 'db_conn') and bot.db_conn:
        bot.db_conn.close()
        print("[Shutdown] Connexion à la base de données fermée.")
    # Fermeture propre de la connexion aux noeuds Lavalink
    await wavelink.Pool.close()
    print("[Shutdown] Connexions aux noeuds Lavalink et à la DB fermées.")

print("Le bot démarre... 123")
#lancement du bot
bot.run(DISCORD_TOKEN)