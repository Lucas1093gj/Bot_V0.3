import os
from flask import Flask
from datetime import datetime
# Import du gestionnaire de traductions
from i18n import translator

def create_app(bot):
    """Crée et configure une instance de l'application Flask."""
    # Le chemin de l'application est 'webapp', donc les templates sont dans le dossier parent '../web'
    # et non dans 'webapp/templates'.
    app = Flask(__name__,
                template_folder='../web',  # Remonte d'un niveau pour trouver le dossier 'web'
                static_folder='../web')    # Idem pour les fichiers statiques (CSS, JS)

    # Configuration de base
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'une-cle-secrete-tres-difficile-a-deviner')
    
    # Ajout de l'instance du bot à la configuration de Flask
    app.config['BOT_INSTANCE'] = bot

    # Ajout des configurations manquantes
    app.config['ADMIN_BOT_IDS'] = {s.strip() for s in os.getenv("ADMIN_BOT_IDS", "").split(',') if s.strip()}
    app.config['BOT_TOKEN'] = os.getenv("DISCORD_TOKEN")
    app.config['CLIENT_ID'] = os.getenv("DISCORD_CLIENT_ID")
    app.config['CLIENT_SECRET'] = os.getenv("DISCORD_CLIENT_SECRET")
    # Définition du chemin de la base de données
    app.config['DATABASE_PATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bot_database.db')

    app.config['WEB_BASE_URL'] = os.getenv('WEB_BASE_URL', 'http://127.0.0.1:5000')
    app.config['REDIRECT_URI'] = f"{app.config['WEB_BASE_URL']}/auth/callback"

    # Initialisation du gestionnaire de traductions
    translator.init_app(app)

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
    @app.template_filter('datetimeformat')
    def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
        """Formate une chaîne de date ISO ou un timestamp en un format lisible."""
        if not value:
            return ""
        # Gère les timestamps (int/float) et les chaînes ISO
        try:
            # La base de données stocke des chaînes, donc on privilégie fromisoformat
            dt_object = datetime.fromisoformat(value) if isinstance(value, str) else datetime.fromtimestamp(value)
            return dt_object.strftime(format)
        except (ValueError, TypeError):
            return value # Retourne la valeur originale si le formatage échoue

    @app.context_processor
    def inject_global_variables():
        from .utils import is_bot_admin
        return {
            'current_year': datetime.now().year,
            'is_bot_admin': is_bot_admin(),
            '_': translator.get_text,  # Rend la fonction de traduction `_` disponible
            'get_locale': translator.get_locale # Rend la fonction get_locale disponible
        }

    return app