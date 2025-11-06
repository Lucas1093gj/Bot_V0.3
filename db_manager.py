import aiosqlite
import os

DB_FILE = "bot_database.db"

async def get_db_connection():
    """Crée et retourne une connexion à la base de données centrale."""
    conn = await aiosqlite.connect(DB_FILE)
    # Permet d'accéder aux colonnes par leur nom
    conn.row_factory = aiosqlite.Row
    return conn

async def initialize_database():
    """
    Initialise toutes les tables nécessaires pour le bot si elles n'existent pas.
    Cette fonction est appelée une seule fois au démarrage du bot.
    """
    async with get_db_connection() as conn:
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
            ticket_category_id INTEGER
        )
    ''')

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

        await conn.commit()
        print("[Database] Base de données initialisée avec succès.")
