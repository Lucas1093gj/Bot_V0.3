import aiosqlite
import os

DB_FILE = "bot_database.db"

def get_db_connection():
    """Crée et retourne une connexion à la base de données centrale."""
    # On retourne directement la coroutine de connexion.
    # 'async with' se chargera de l'await.
    # On ne peut pas définir row_factory ici, on le fera après la connexion.
    return aiosqlite.connect(DB_FILE)

async def initialize_database():
    """
    Initialise toutes les tables nécessaires pour le bot si elles n'existent pas.
    Cette fonction est appelée une seule fois au démarrage du bot.
    """
    async with get_db_connection() as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.cursor() # noqa

        # Table pour les avertissements (du cog Moderation)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

        # Table pour les logs de messages (du cog Logger)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            event_type TEXT NOT NULL, -- 'deleted' ou 'edited'
            old_content TEXT,
            new_content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

        # Table pour les configurations spécifiques au serveur (ex: salon de logs)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            mod_log_channel_id INTEGER,
            ticket_category_id INTEGER,
            welcome_channel_id INTEGER,
            welcome_message TEXT,
            welcome_enabled INTEGER DEFAULT 0,
            autorole_id INTEGER,
            antispam_invites_enabled INTEGER DEFAULT 0,
            antispam_links_enabled INTEGER DEFAULT 0,
            antispam_burst_enabled INTEGER DEFAULT 0,
            receive_broadcasts INTEGER DEFAULT 1 NOT NULL,
            leveling_enabled INTEGER DEFAULT 0,
            xp_cooldown INTEGER DEFAULT 60,
            leveling_blacklisted_channels TEXT DEFAULT '',
            xp_rate TEXT DEFAULT '15-25'
        )
    ''')

        # --- MIGRATIONS : Vérification et ajout des colonnes manquantes ---
        await cursor.execute("PRAGMA table_info(guild_settings)")
        columns = [col[1] for col in await cursor.fetchall()]
        
        # Dictionnaire des colonnes à vérifier et à ajouter si elles manquent
        columns_to_add = {
            "welcome_channel_id": "INTEGER",
            "welcome_message": "TEXT",
            "welcome_enabled": "INTEGER DEFAULT 0",
            "autorole_id": "INTEGER",
            "antispam_invites_enabled": "INTEGER DEFAULT 0",
            "antispam_links_enabled": "INTEGER DEFAULT 0",
            "antispam_burst_enabled": "INTEGER DEFAULT 0",
            "receive_broadcasts": "INTEGER DEFAULT 1 NOT NULL",
            "leveling_enabled": "INTEGER DEFAULT 0",
            "xp_cooldown": "INTEGER DEFAULT 60",
            "leveling_blacklisted_channels": "TEXT DEFAULT ''",
            "xp_rate": "TEXT DEFAULT '15-25'"
        }

        for col_name, col_type in columns_to_add.items():
            if col_name not in columns:
                print(f"[DB Migration] Ajout de la colonne '{col_name}' à la table 'guild_settings'...")
                await cursor.execute(f"ALTER TABLE guild_settings ADD COLUMN {col_name} {col_type}")



        # Table pour suivre les éléments créés par le bot (pour un reset infaillible)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS created_elements (
            guild_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            element_type TEXT NOT NULL, -- 'role', 'channel', 'category'
            PRIMARY KEY (guild_id, element_id)
        )
    ''')

        # Table pour le système de niveaux (leveling)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_levels (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            last_message_timestamp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')
        
        # Vérifier si la colonne last_message_timestamp existe et l'ajouter si ce n'est pas le cas
        await cursor.execute("PRAGMA table_info(user_levels)")
        columns = [col[1] for col in await cursor.fetchall()]
        if 'last_message_timestamp' not in columns:
            await cursor.execute("ALTER TABLE user_levels ADD COLUMN last_message_timestamp INTEGER DEFAULT 0")

        # Table pour les logs de commandes (pour le panel admin)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER NOT NULL,
            command_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            success INTEGER NOT NULL,
            error_message TEXT
        )
        ''')

        # Table pour les paramètres globaux (pour le panel admin)
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS global_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')
        # Initialiser la valeur par défaut du mode maintenance s'il n'existe pas
        await cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('maintenance_mode', '0')")

        # NOUVEAU : Table pour l'historique du journal des mises à jour
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS update_vlog_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            admin_user_id TEXT NOT NULL,
            admin_user_name TEXT NOT NULL,
            old_content TEXT,
            new_content TEXT NOT NULL
        )
        ''')


        await conn.commit()
        print("[Database] Base de données initialisée avec succès.")
