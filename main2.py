import os
import sys
import threading
import waitress

# --- Imports du Bot ---
# On importe l'instance du bot depuis main.py
from main import bot, DISCORD_TOKEN as BOT_TOKEN

# --- NOUVEAU : Import de la factory d'application Flask ---
from webapp import create_app

# Vérification critique au démarrage
if not os.getenv("DISCORD_CLIENT_ID") or not os.getenv("DISCORD_CLIENT_SECRET") or not BOT_TOKEN:
    raise ValueError("[ERREUR] DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, et DISCORD_TOKEN doivent être définis dans le .env")

# ===============================================
# Initialisation du Site Web (Flask)
# ===============================================
app = create_app(bot)

# --- NOUVEAU : Affichage des URLs depuis la configuration de l'app ---
print("="*50)
print(f"[INFO] L'application web est configurée pour tourner sur : {app.config['WEB_BASE_URL']}")
print(f"[INFO] La REDIRECT_URI pour Discord OAuth2 est : {app.config['REDIRECT_URI']}")
print("="*50)

@app.route('/routes') # NOUVEAU : Route de débogage
def list_routes():
    """Liste toutes les routes de l'application pour le débogage."""
    output = "<h1>Endpoints de l'application Flask</h1>"
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.endpoint):
        output += f"<b>{rule.endpoint}</b> ({', '.join(rule.methods)}) &rarr; <code>{rule.rule}</code><br>"
    return f"<div style='font-family: sans-serif; line-height: 1.6;'>{output}</div>"


# --- Démarrage ---
def run_bot():
    """Fonction pour lancer le bot dans un thread."""
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"[ERREUR CRITIQUE BOT] Le bot s'est arrêté : {e}", flush=True)

if __name__ == '__main__':
    # 1. Lancer le bot dans un thread d'arrière-plan
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    print("[Main Thread] Le thread du bot a été lancé.")

    # 2. Lancer le serveur Flask (MODE PRODUCTION)
    print("[Main Thread] Lancement du serveur web de production sur http://0.0.0.0:8000")
    waitress.serve(app, host='0.0.0.0', port=8000)