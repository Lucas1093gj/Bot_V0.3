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
    # Ajoutez ici les autres tables au fur et à mesure des besoins

    conn.commit()
    conn.close()
    print("[Database] Base de données initialisée avec succès.")
