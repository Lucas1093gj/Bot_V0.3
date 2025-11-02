import sqlite3
import os

DB_FILE = "bot_database.db"

def get_db_connection():
    """Crée et retourne une connexion à la base de données centrale."""
    conn = sqlite3.connect(DB_FILE)
    # Permet d'accéder aux colonnes par leur nom
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """
    Initialise toutes les tables nécessaires pour le bot si elles n'existent pas.
    Cette fonction est appelée une seule fois au démarrage du bot.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table pour les avertissements (du cog Moderation)
    cursor.execute('''
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
    cursor.execute('''
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            mod_log_channel_id INTEGER,
            ticket_category_id INTEGER
        )
    ''')

    # Table pour suivre les éléments créés par le bot (pour un reset infaillible)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS created_elements (
            guild_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            element_type TEXT NOT NULL, -- 'role', 'channel', 'category'
            PRIMARY KEY (guild_id, element_id)
        )
    ''')

    # Table pour le système de niveaux (leveling)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_levels (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("[Database] Base de données initialisée avec succès.")
