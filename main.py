# Imports principaux de bibliothèques
import discord
import os
import aiosqlite
import asyncio # noqa
import datetime # noqa

#chargement des variables d'environnement depuis le fichier .env (DOIT ÊTRE FAIT AVANT LES AUTRES IMPORTS)
# C'est crucial de charger les variables d'environnement AVANT d'importer les modules qui en dépendent.
from dotenv import load_dotenv
load_dotenv()

# Imports des modules et classes spécifiques au bot
import wavelink
from discord.ext import commands
from discord.ext import tasks
import db_manager # Notre gestionnaire pour la base de données

#chargement des variables d'environnement
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CREATOR_ID = os.getenv("CREATOR_ID")
# On récupère les IDs des admins, on les nettoie (enlève les espaces) et on les stocke dans un set pour une recherche rapide.
ADMIN_BOT_IDS = {s.strip() for s in os.getenv("ADMIN_BOT_IDS", "").split(',') if s.strip()}
# On s'assure que le chemin de la base de données est toujours correct, peu importe d'où le script est lancé.
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_database.db')
# Import des vues persistantes et des fonctions de configuration (après load_dotenv)
from commandes.discordmaker import VerificationView, RoleMenuView, SELF_ASSIGNABLE_ROLES, load_config as load_dm_config
from commandes.music import MusicControls

if not DISCORD_TOKEN:
    print("[ERREUR] Le token Discord n'est pas défini. Veuillez vérifier votre fichier .env.")
    exit()

# L'initialisation de la base de données se fera de manière asynchrone dans `setup_hook`.
print("[Startup] Initialisation de la base de données...")

#initialisation du bot
# On active tous les "Intents" pour que le bot reçoive tous les types d'événements de Discord.
# Pour un bot public à grande échelle, il serait plus optimisé de n'activer que les intents nécessaires.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
# Ce verrou est utilisé pour protéger les opérations critiques (comme la reconstruction d'un serveur)
# afin d'éviter que plusieurs commandes conflictuelles ne s'exécutent en même temps.
bot.critical_operation_lock = asyncio.Lock()

# --- Configuration Lavalink ---
LAVALINK_NODES = [
    # --- Liste de nœuds Lavalink v4 optimisée pour contourner les pare-feu ---
    # On utilise uniquement des serveurs sur le port 80, qui est le port standard du web et rarement bloqué.
    {"host": "lava-v4.ajieblogs.eu.org", "port": 80, "password": "https://dsc.gg/ajidevserver", "secure": False, "region": "AjieDev-EU-Port80"},
    {"host": "lavalinkv4.serenetia.com", "port": 80, "password": "https://dsc.gg/ajidevserver", "secure": False, "region": "Serenetia-EU-Port80"},
]

# --- Fonctions utilitaires pour la base de données (copiées de main2.py) ---
async def get_db_async():
    """Ouvre une connexion asynchrone à la base de données SQLite."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db

# --- Tâche de nettoyage des logs ---
@tasks.loop(hours=24)
async def cleanup_old_logs():
    """
    Tâche de fond qui s'exécute une fois par jour pour supprimer les logs de plus de 12 mois,
    conformément à la politique de confidentialité.
    """
    try:
        # Calcule la date d'il y a 12 mois
        twelve_months_ago = datetime.datetime.now() - datetime.timedelta(days=365)
        timestamp_threshold = twelve_months_ago.strftime('%Y-%m-%d %H:%M:%S')

        async with db_manager.get_db_connection() as db:
            cursor = await db.execute("DELETE FROM message_events WHERE timestamp < ?", (timestamp_threshold,))
            rows_deleted = cursor.rowcount
            await db.commit()
            if rows_deleted > 0:
                print(f"[Log Cleanup] Tâche de nettoyage terminée. {rows_deleted} log(s) de message de plus de 12 mois ont été supprimés.")
    except Exception as e:
        print(f"[ERREUR - Log Cleanup] Une erreur est survenue lors du nettoyage des anciens logs : {e}")



@bot.event
async def on_wavelink_inactive_node(node: wavelink.Node):
    """Gère le cas où un nœud Lavalink (pour la musique) devient subitement inactif."""
    print(f"[Lavalink - ERREUR] Le nœud '{node.identifier}' est devenu inactif. Wavelink tentera de se reconnecter.")
    if CREATOR_ID:
        creator = await bot.fetch_user(int(CREATOR_ID))
        if creator:
            await creator.send(f"⚠️ **Alerte Bot** ⚠️\nLe nœud Lavalink `{node.identifier}` est déconnecté ou ne répond plus.")

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    """Confirme dans la console qu'un nœud Lavalink est bien connecté et prêt à l'emploi."""
    node = payload.node
    print(f"[Lavalink - INFO] Le nœud '{node.identifier}' est prêt. Session ID: {payload.session_id}")


@bot.event
async def setup_hook():
    """Cette fonction spéciale est appelée par discord.py avant que le bot ne soit complètement en ligne.
    C'est l'endroit idéal pour initialiser les services asynchrones comme la base de données et Lavalink."""
    await db_manager.initialize_database()
    print("[Startup] Base de données initialisée.")
    
    # On prépare la connexion à tous les nœuds Lavalink définis dans la configuration.
    # Wavelink gérera ensuite la répartition de la charge et les reconnexions.
    nodes = []
    for config in LAVALINK_NODES:
        nodes.append(wavelink.Node(
            uri=f"{'https' if config['secure'] else 'http'}://{config['host']}:{config['port']}",
            password=config['password'],
            identifier=config.get('region', config['host']) # Utilise la région comme identifiant pour plus de clarté
        ))
    await wavelink.Pool.connect(nodes=nodes, client=bot, cache_capacity=100)

    # On charge toutes les extensions (cogs) qui se trouvent dans le dossier 'commandes'.
    print("[Startup] Chargement des Cogs...")
    for filename in os.listdir('./commandes'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'commandes.{filename[:-3]}')
                print(f"-> Cog '{filename[:-3]}' chargé.")
            except Exception as e:
                print(f"[ERREUR] Échec du chargement du cog {filename[:-3]}: {e}")
    
    # On synchronise les commandes slash avec Discord pour qu'elles apparaissent dans l'interface.
    synced = await bot.tree.sync()
    print(f"[Startup] {len(synced)} commande(s) synchronisée(s) globalement.")

@bot.tree.interaction_check
async def maintenance_check(interaction: discord.Interaction):
    """Ce 'check' est exécuté avant chaque commande slash pour vérifier si le mode maintenance est actif."""
    # Ne s'applique pas aux interactions de composants (boutons, menus) pour que les vues persistantes continuent de fonctionner
    # C'est important pour que les boutons de musique ou de rôles marchent même en mode maintenance.
    if interaction.type != discord.InteractionType.application_command:
        return True

    try:
        db = await get_db_async()
        cursor = await db.execute("SELECT value FROM global_settings WHERE key = 'maintenance_mode'")
        maintenance_mode = await cursor.fetchone()
        await db.close()

        if maintenance_mode and maintenance_mode['value'] == '1':
            # Vérifie si l'utilisateur est un admin du bot
            user_id_str = str(interaction.user.id) # On compare des chaînes pour éviter les erreurs de type
            if user_id_str in ADMIN_BOT_IDS:
                return True  # Les admins peuvent utiliser le bot
            else:
                await interaction.response.send_message("🔧 Le bot est actuellement en maintenance. Veuillez réessayer plus tard.", ephemeral=True)
                return False  # Bloque la commande pour les autres
        return True
    except Exception as e:
        print(f"[ERREUR] Échec de la vérification du mode maintenance : {e}")
        # En cas d'erreur (ex: DB inaccessible), on autorise la commande par sécurité pour ne pas bloquer tout le bot.
        return True

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Ce gestionnaire global est principalement destiné aux interactions qui ne sont pas des commandes slash,
    comme les clics sur des boutons ou les sélections dans un menu.
    """
    if interaction.type == discord.InteractionType.application_command:
        return # On laisse les commandes slash être gérées par leurs propres fonctions.

    # Logique pour les boutons de Rôle-Réaction (ceux qui ne sont pas dans une vue persistante dédiée)
    if interaction.type == discord.InteractionType.component and interaction.data.get("component_type") == 2: # 2 = Bouton
        custom_id = interaction.data.get("custom_id")
        if custom_id and custom_id.startswith("reaction_role_button:"):
            try:
                role_id = int(custom_id.split(":")[1])
                guild = interaction.guild
                member = interaction.user

                role = guild.get_role(role_id)
                if not role:
                    await interaction.response.send_message("❌ Ce rôle n'existe plus.", ephemeral=True)
                    return

                if role in member.roles:
                    await member.remove_roles(role, reason="Rôle-Réaction")
                    await interaction.response.send_message(f"✅ Le rôle **{role.name}** vous a été retiré.", ephemeral=True)
                else:
                    await member.add_roles(role, reason="Rôle-Réaction")
                    await interaction.response.send_message(f"✅ Vous avez obtenu le rôle **{role.name}** !", ephemeral=True)

            except (ValueError, IndexError, discord.Forbidden, discord.HTTPException) as e:
                await interaction.response.send_message(f"❌ Une erreur est survenue. Il est possible que je n'aie pas les permissions nécessaires. Erreur: {e}", ephemeral=True)

@bot.event
async def on_ready():
    """Cet événement est déclenché lorsque le bot est entièrement connecté et prêt à fonctionner."""
    print(f"Connecté en tant que {bot.user}")

    # Envoi d'une notification de démarrage au créateur du bot pour confirmer que tout va bien.
    if CREATOR_ID:
        try:
            creator = await bot.fetch_user(int(CREATOR_ID))
            if creator:
                # Compter les cogs chargés avec succès
                loaded_cogs_count = len(bot.cogs)
                total_cogs = len([f for f in os.listdir('./commandes') if f.endswith('.py')])

                embed = discord.Embed(
                    title="✅ Démarrage Réussi",
                    description=f"Le bot **{bot.user.name}** est en ligne et pleinement fonctionnel.",
                    color=0x57F287, # Vert Discord
                    timestamp=datetime.datetime.now()
                )
                if bot.user.avatar:
                    embed.set_thumbnail(url=bot.user.avatar.url)
                
                embed.add_field(name="📊 Statistiques", value=f"**Serveurs**: {len(bot.guilds)}\n**Latence**: {bot.latency * 1000:.2f} ms", inline=True)
                embed.add_field(name="⚙️ Modules", value=f"**Cogs**: {loaded_cogs_count}/{total_cogs}\n**Commandes**: {len(bot.tree.get_commands())}", inline=True)
                
                node_status = "🟢 Connecté" if wavelink.Pool.get_node().status == wavelink.NodeStatus.CONNECTED else "🔴 Déconnecté"
                embed.add_field(name="🎵 Musique (Lavalink)", value=f"**Statut**: {node_status}", inline=True)
                embed.set_footer(text=f"Version de discord.py : {discord.__version__}")
                await creator.send(embed=embed)
                print(f"[Startup] Notification de redémarrage envoyée à {creator.name}.")
        except (discord.NotFound, discord.Forbidden, ValueError) as e:
            print(f"[ERREUR] Impossible d'envoyer la notification de redémarrage au créateur (ID: {CREATOR_ID}). Erreur: {e}")

    # Ré-enregistre les "vues" (ensembles de boutons/menus) persistantes au démarrage.
    # C'est ce qui permet aux boutons de fonctionner même après un redémarrage du bot.
    print("[Startup] Ré-enregistrement des vues persistantes...")
    for guild in bot.guilds:
        dm_config = load_dm_config(guild.id)
        if dm_config.get("verification_system") == "enabled":
            bot.add_view(VerificationView())
        
        assignable_roles = [role for role in dm_config.get("roles", []) if role in SELF_ASSIGNABLE_ROLES] # noqa
        if assignable_roles:
            bot.add_view(RoleMenuView(assignable_roles, bot))

    # La vue pour les contrôles musicaux est également persistante.
    # Elle est ajoutée ici pour s'assurer qu'elle est toujours active.
    bot.add_view(MusicControls())

    # On lance la tâche de nettoyage des logs en arrière-plan.
    cleanup_old_logs.start()

@bot.event
async def close():
    """Cette fonction est appelée lorsque le bot s'arrête, pour un nettoyage propre."""
    # On s'assure que tous les logs en attente sont bien écrits dans la base de données.
    logger_cog = bot.get_cog("LoggerCog")
    if logger_cog:
        print("[Shutdown] Écriture des logs restants...")
        await logger_cog.flush_logs()
    
    await wavelink.Pool.close()
    print("[Shutdown] Connexions aux noeuds Lavalink fermées.")