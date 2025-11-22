from flask import Flask, session, g, render_template
import os
from dotenv import load_dotenv
from datetime import datetime
import threading

def create_app(bot_instance):
    """Crée et configure l'instance de l'application Flask."""
    
    # --- Configuration de Flask ---
    app = Flask("webapp", # Nommer explicitement l'application
                template_folder='../web',    # Remonte d'un niveau pour trouver le dossier web
                static_folder='../web')      # Idem pour les fichiers statiques

    load_dotenv()
    app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "une-cle-secrete-par-defaut-pour-le-dev")
    app.config['BOT_INSTANCE'] = bot_instance
    app.config['ADMIN_BOT_IDS'] = {s.strip() for s in os.getenv("ADMIN_BOT_IDS", "").split(',') if s.strip()}
    app.config['BOT_TOKEN'] = os.getenv("DISCORD_TOKEN")
    app.config['CLIENT_ID'] = os.getenv("DISCORD_CLIENT_ID")
    app.config['CLIENT_SECRET'] = os.getenv("DISCORD_CLIENT_SECRET")
    app.config['DATABASE_PATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bot_database.db')

    # --- NOUVEAU : Centralisation de la configuration de l'URL ---
    # On charge l'URL depuis le .env, avec une valeur par défaut pour le développement local.
    app.config['WEB_BASE_URL'] = os.getenv("WEB_BASE_URL", "http://127.0.0.1:8000")
    app.config['REDIRECT_URI'] = os.getenv("REDIRECT_URI", f"{app.config['WEB_BASE_URL']}/auth/callback")

    # --- NOUVEAU : Verrou pour éviter les race conditions sur le refresh token ---
    app.token_refresh_lock = threading.Lock()

    # Importer et enregistrer les Blueprints
    from .routes.public import public_bp
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.admin import admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    # Enregistrer les filtres et processeurs de contexte Jinja2
    # Il est préférable de les définir dans une fonction séparée ou directement ici
    # pour la clarté et pour s'assurer qu'ils sont enregistrés sur la bonne instance d'app.

    @app.template_filter('datetimeformat')
    def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
        """Formate une chaîne de date ISO ou un timestamp en un format lisible."""
        if not value:
            return ""
        # Gère les timestamps (int/float) et les chaînes ISO
        dt_object = datetime.fromisoformat(value) if isinstance(value, str) else datetime.fromtimestamp(value)
        return dt_object.strftime(format)

    @app.context_processor
    def inject_global_variables():
        from .utils import is_bot_admin
        return {
            'current_year': datetime.now().year,
            'is_bot_admin': is_bot_admin()
        }

    return app