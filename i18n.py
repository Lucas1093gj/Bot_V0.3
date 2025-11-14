import os
import json
from flask import request, session

class TranslationManager:
    """
    Gère le chargement et l'accès aux traductions depuis des fichiers JSON.
    """
    def __init__(self, app=None):
        self.translations = {}
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialise le gestionnaire avec l'application Flask."""
        locales_dir = os.path.join(app.root_path, 'locales')
        print("[i18n] Chargement des traductions...")
        if not os.path.exists(locales_dir):
            print(f"[i18n-WARN] Le dossier '{locales_dir}' n'existe pas. Aucune traduction ne sera chargée.")
            return

        for filename in os.listdir(locales_dir):
            if filename.endswith('.json'):
                lang_code = filename.split('.')[0]
                filepath = os.path.join(locales_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                        print(f"  -> Traduction '{lang_code}' chargée.")
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[i18n-ERROR] Impossible de charger le fichier de traduction '{filename}': {e}")

    def get_locale(self):
        """
        Détecte la langue de l'utilisateur.
        Priorité : session['lang'] > en-tête Accept-Language > 'fr' par défaut.
        """
        # 1. Vérifier si la langue est forcée dans la session
        if 'lang' in session and session['lang'] in self.translations:
            return session['lang']

        # 2. Essayer de trouver une langue correspondante dans les en-têtes du navigateur
        if request.accept_languages:
            best_match = request.accept_languages.best_match(self.translations.keys())
            if best_match:
                return best_match
        
        # 3. Utiliser la langue par défaut
        return 'fr'

    def get_text(self, key, **kwargs):
        """
        Récupère la traduction pour une clé donnée dans la langue actuelle.
        Si des arguments nom-valeur sont fournis, ils sont utilisés pour formater la chaîne.
        """
        locale = self.get_locale()
        # Recherche la clé dans le JSON de la langue.
        # Si la clé ou la langue n'existe pas, retourne la clé elle-même.
        text = self.translations.get(locale, {}).get(key, key)

        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text # En cas d'erreur de formatage, retourne le texte brut.
        return text

# --- Initialisation globale ---
# On crée une instance qui sera importée par d'autres modules.
translator = TranslationManager()

# On crée un alias `_` pour un accès plus facile dans les templates.
_ = translator.get_text
