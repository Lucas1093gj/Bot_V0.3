# 🤖 Bot Discord Multifonction (v0.3)

Un bot Discord polyvalent et puissant, conçu pour la gestion complète de serveurs, l'animation musicale, la modération avancée et l'engagement communautaire. Ce bot est structuré en cogs (modules) pour une maintenance et une extensibilité faciles.

## ✨ Fonctionnalités Principales

Le bot est organisé en plusieurs modules, chacun offrant un ensemble de commandes spécifiques.

### ⚙️ Créateur de Serveur (`/discordmaker`)

Le module le plus puissant du bot, permettant de construire et gérer un serveur Discord de A à Z.

*   **`/discordmaker setup`**: Ouvre une interface de configuration privée pour choisir les rôles, les salons, la politique de nettoyage et le système de vérification à mettre en place.
*   **`/discordmaker start`**: Lance la construction du serveur selon la configuration définie.
*   **`/discordmaker reset`**: Effectue un nettoyage "intelligent" en ne supprimant que les rôles et salons créés par le bot.
*   **`/discordmaker full-reset`**: (Propriétaire uniquement) Réinitialise **totalement** le serveur (rôles et salons) après une double confirmation et envoie une sauvegarde en message privé.
*   **`/discordmaker restore`**: (Propriétaire uniquement) Restaure la structure d'un serveur à partir d'un fichier de sauvegarde `.json`.
*   **`/discordmaker post-roles`**: Poste un message avec un menu déroulant pour que les membres puissent s'auto-attribuer des rôles (jeux, notifications, etc.).

### 🎵 Musique (`/musique`)

Un système musical complet pour animer vos salons vocaux.

*   **`/musique play [recherche]`**: Joue une musique ou une playlist depuis YouTube ou Spotify.
*   **`/musique playnext [recherche]`**: Ajoute une musique en haut de la file d'attente.
*   **`/musique queue`**: Affiche la liste des musiques à venir.
*   **`/musique loop [mode]`**: Répète la musique actuelle (`track`), la file d'attente (`queue`), ou désactive la répétition.
*   **`/musique shuffle`**: Mélange la file d'attente.
*   **`/musique clear`**: Vide la file d'attente.
*   **Contrôles Interactifs**: Des boutons (Pause/Play, Skip, Stop, etc.) sont affichés avec la musique en cours.
*   **Sauvegarde de la file d'attente**: Si le bot est déconnecté, il propose de restaurer la file d'attente à son retour.

### 🛡️ Modération

Des outils essentiels pour maintenir un environnement sain sur votre serveur.

*   **`/clear [nombre]`**: Supprime un nombre de messages dans un salon.
*   **`/warn [membre] [raison]`**: Avertit un membre et enregistre l'avertissement.
*   **`/warnings [membre]`**: Affiche l'historique des avertissements d'un membre.
*   **`/mute [membre] [durée] [raison]`**: Applique un timeout à un membre pour l'empêcher de communiquer.
*   **`/unmute [membre]`**: Retire le timeout d'un membre.

### 📝 Journal d'Audit (Logger)

Un système de logs discret et respectueux de la vie privée.

*   **Enregistrement automatique**: Loggue les messages supprimés et modifiés dans une base de données.
*   **`/getlog`**: (Admin uniquement) Permet de récupérer un fichier de base de données `.db` contenant l'historique des événements du serveur, envoyé en message privé.

### 🎉 Fun & Utilitaires

*   **`/poll [question] [options...]`**: Crée un sondage simple avec des réactions automatiques.
*   **`/help`**: Affiche un panneau d'aide interactif avec un menu déroulant pour toutes les commandes.
*   **`/serverinfo`**: Affiche des statistiques détaillées sur le serveur.
*   **`/userinfo [membre]`**: Affiche des informations sur un membre Discord.

---

## 🚀 Installation et Lancement

Suivez ces étapes pour héberger votre propre instance du bot.

### 1. Prérequis

*   Python 3.8+
*   FFmpeg (doit être ajouté au PATH de votre système pour le cog musique)
*   Un compte développeur Discord et une application de bot créée.

### 2. Clonage du Projet

```bash
git clone <URL_DU_REPOSITORY>
cd <NOM_DU_DOSSIER>
```

### 3. Installation des Dépendances

Il est recommandé d'utiliser un environnement virtuel.

```bash
# Créer un environnement virtuel
python -m venv venv

# Activer l'environnement
# Sur Windows:
venv\Scripts\activate
# Sur macOS/Linux:
source venv/bin/activate

# Installer les paquets requis
pip install -r requirements.txt
```

*(Note: Un fichier `requirements.txt` devra être créé avec les dépendances du projet, comme `py-cord`, `spotipy`, `yt-dlp`, etc.)*

### 4. Configuration

Créez un fichier `.env` à la racine du projet et remplissez-le avec vos clés d'API et tokens.

```env
# .env

# Token de votre bot Discord
DISCORD_TOKEN="VOTRE_TOKEN_DISCORD_ICI"

# Clés de l'API Spotify pour la fonctionnalité musique
SPOTIFY_CLIENT_ID="VOTRE_ID_CLIENT_SPOTIFY"
SPOTIFY_CLIENT_SECRET="VOTRE_SECRET_CLIENT_SPOTIFY"
```

**Important** : Assurez-vous que votre bot a les **Intents Privilégiés** (`Privileged Gateway Intents`) activés sur le portail développeur de Discord, notamment :
*   `PRESENCE INTENT`
*   `SERVER MEMBERS INTENT`
*   `MESSAGE CONTENT INTENT`

### 5. Lancement du Bot

Une fois la configuration terminée, lancez le bot avec la commande suivante :

```bash
python main.py
```

Le bot devrait se connecter et être prêt à recevoir des commandes. La base de données `bot_database.db` sera créée automatiquement au premier lancement.

---

## 🗺️ Feuille de Route (Roadmap)

Le développement du bot suit une feuille de route ambitieuse, incluant :

*   **v0.4 : Gamification et Engagement** (Systèmes de niveaux, d'économie, de giveaways).
*   **v0.5 : Automatisation et Outils de Staff** (Auto-modération, système de tickets, messages de bienvenue).
*   **v0.6 : Interactions Communautaires** (Clans, profils utilisateurs, suggestions).
*   **v0.7 : Intégrations Externes** (API de météo, traduction, statistiques de jeux).
*   **v0.8+ : Projets Majeurs** (Tableau de bord web, support multilingue, intégration d'IA).

Pour plus de détails, consultez le fichier `future_updates.txt`.

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Si vous souhaitez améliorer le bot, n'hésitez pas à forker le projet, créer une branche pour votre fonctionnalité et soumettre une Pull Request.

---

## 📄 Licence

Ce projet est distribué sous la licence MIT. Voir le fichier `LICENSE` pour plus de détails.