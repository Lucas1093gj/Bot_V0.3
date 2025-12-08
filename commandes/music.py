import discord
import os
import json
import wavelink
from discord.ext import commands
from discord.ext import tasks
from discord import app_commands
import re
from urllib.parse import urlparse
import spotipy
from datetime import timedelta

# --- Constantes ---
STATE_BACKUP_DIR = "music_state_backups"

# --- Structures de données pour la sauvegarde ---
def is_valid_url(url: str) -> bool:
    """Vérifie si une chaîne est une URL valide."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except (ValueError, AttributeError):
        return False

def track_to_dict(track: wavelink.Playable) -> dict:
    """Convertit un objet piste Wavelink en un dictionnaire simple, facile à sauvegarder en JSON."""
    return { # noqa
        "uri": track.uri,
        "title": track.title,
        "author": track.author,
        "duration": track.length,
        "requester_id": track.extras["requester_id"] if "requester_id" in track.extras else None
    }

# --- Fonctions de gestion de la sauvegarde de la file d'attente ---
async def _save_state(player: wavelink.Player, guild_id: int):
    """Sauvegarde l'état actuel du lecteur (file d'attente, volume, boucle) dans un fichier JSON dédié au serveur."""
    if not os.path.exists(STATE_BACKUP_DIR):
        os.makedirs(STATE_BACKUP_DIR)
    filepath = os.path.join(STATE_BACKUP_DIR, f"{guild_id}.json")
    
    queue_data = [track_to_dict(track) for track in player.queue]
    if player.current:
        queue_data.insert(0, track_to_dict(player.current))

    with open(filepath, 'w', encoding='utf-8') as f:
        state_data = {
            "queue": queue_data,
            "loop_mode": str(player.queue.mode).split('.')[-1].lower(),
            "volume": player.volume,
        }
        json.dump(state_data, f, indent=4)

def _load_state_data(guild_id: int) -> dict | None:
    """Charge les données de l'état sauvegardé pour un serveur, s'il en existe."""
    filepath = os.path.join(STATE_BACKUP_DIR, f"{guild_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            # Si le fichier est corrompu ou ancien format, on le supprime
            os.remove(filepath)
            return None
    return None

def _delete_state_backup(guild_id: int):
    """Supprime le fichier de sauvegarde d'un serveur, généralement après restauration ou si l'utilisateur l'ignore."""
    filepath = os.path.join(STATE_BACKUP_DIR, f"{guild_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)


class MusicControls(discord.ui.View):
    """Définit la vue persistante avec tous les boutons de contrôle pour la musique."""
    def __init__(self, bot: commands.Bot = None):
        super().__init__(timeout=None)

    @discord.ui.button(label="⏯️ Pause/Reprendre", style=discord.ButtonStyle.primary, custom_id="music_pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("❌ Il n'y a aucune musique en cours de lecture ou en pause.", ephemeral=True)
        
        if player.paused:
            await player.pause(False)
            await interaction.response.send_message("▶️ Musique reprise.", ephemeral=True)
        else:
            await player.pause(True)
            await interaction.response.send_message("⏸️ Musique mise en pause.", ephemeral=True)

    @discord.ui.button(label="⏭️ Passer", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.playing:
            await player.skip(force=True)
            await interaction.response.send_message("⏭️ Musique passée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucune musique à passer.", ephemeral=True)

    @discord.ui.button(label="⏹️ Arrêter", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.connected:
            player.queue.clear()
            await player.stop()
            await interaction.response.send_message("⏹️ Lecture arrêtée et file d'attente vidée.", ephemeral=True) # noqa
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

    @discord.ui.button(label="👋 Quitter", style=discord.ButtonStyle.secondary, custom_id="music_leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.connected:
            await _save_state(player, interaction.guild.id)
            await player.disconnect()
            await interaction.response.send_message("👋 Le bot a quitté le salon vocal.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

    @discord.ui.button(label="📜 File d'attente", style=discord.ButtonStyle.secondary, custom_id="music_queue")
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        player: wavelink.Player = interaction.guild.voice_client

        if not player or player.queue.is_empty:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0
        
        for i, track in enumerate(player.queue):
            line = f"`{i+1}.` {track.title}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(player.queue) > displayed_count:
            embed.set_footer(text=f"et {len(player.queue) - displayed_count} autre(s) morceau(x).")

        await interaction.response.send_message(embed=embed, ephemeral=True)

class RestoreQueueView(discord.ui.View): # noqa
    """Vue temporaire qui demande à l'utilisateur s'il veut restaurer une ancienne file d'attente."""
    def __init__(self, music_cog, interaction, query):
        super().__init__(timeout=60) # noqa
        self.music_cog = music_cog
        self.interaction = interaction
        self.query = query
        self.guild_id = interaction.guild.id

    async def on_timeout(self):
        """Si l'utilisateur ne répond pas à temps, on ignore la sauvegarde et on continue."""
        _delete_state_backup(self.guild_id)
        # On retire le serveur de la liste d'attente
        self.music_cog.waiting_for_restore.pop(self.guild_id, None)
        await self.interaction.edit_original_response(content="Délai dépassé. La sauvegarde a été ignorée.", view=None)
        # On pourrait lancer la lecture de la chanson demandée ici si nécessaire

    @discord.ui.button(label="✅ Restaurer la file d'attente", style=discord.ButtonStyle.success)
    async def restore(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        """Restaure la file d'attente, le volume et la boucle depuis le fichier de sauvegarde."""
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        loaded_state_data = _load_state_data(self.guild_id)
        player: wavelink.Player = interaction.guild.voice_client
        
        # Vérification de sécurité : si le bot a été déconnecté entre-temps
        if not player:
            await self.interaction.edit_original_response(content="❌ Le bot n'est plus connecté. Veuillez relancer la commande.", view=None)
            _delete_state_backup(self.guild_id)
            return
        
        if loaded_state_data and loaded_state_data.get("queue"):
            self.music_cog.waiting_for_restore.pop(self.guild_id, None) # On indique que la restauration est gérée.
            # Restaurer le volume et la boucle
            await player.set_volume(loaded_state_data.get("volume", 100))
            loop_mode_str = loaded_state_data.get("loop_mode", "normal").lower() # Utiliser lower()
            player.queue.mode = getattr(wavelink.QueueMode, loop_mode_str, wavelink.QueueMode.normal)

            # On ajoute les anciennes pistes à la file d'attente.
            for track_data in loaded_state_data["queue"]:
                try:
                    # On recherche par URI pour être précis
                    tracks = await wavelink.Playable.search(track_data["uri"])
                    if tracks:
                        track = tracks[0]
                        track.extras = {"requester_id": track_data.get("requester_id")}
                        await player.queue.put_wait(track)
                except Exception:
                    continue # Ignorer les pistes qui ne peuvent pas être restaurées
            
            await self.music_cog._add_song_to_queue(interaction, self.query)
            await self.interaction.edit_original_response(content="✅ État précédent (file d'attente, volume, boucle) restauré ! La lecture va commencer.", view=None)
        else:
            # Si la sauvegarde est vide ou corrompue, on continue normalement
            self.music_cog.waiting_for_restore.pop(self.guild_id, None)
            await self.interaction.edit_original_response(content="❌ Impossible de trouver la sauvegarde. Lancement d'une nouvelle file d'attente.", view=None)
            await self.music_cog._add_song_to_queue(interaction, self.query)
        
        _delete_state_backup(self.guild_id)
        self.stop()

    @discord.ui.button(label="🗑️ Ignorer", style=discord.ButtonStyle.secondary)
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button): # noqa
        """Ignore la sauvegarde et lance une nouvelle file d'attente."""
        await interaction.response.defer()
        _delete_state_backup(self.guild_id)
        self.music_cog.waiting_for_restore.pop(self.guild_id, None)
        await self.interaction.edit_original_response(content="🗑️ Sauvegarde ignorée. Lancement d'une nouvelle file d'attente.", view=None)
        await self.music_cog._add_song_to_queue(self.interaction, self.query)
        self.stop()

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ce dictionnaire permet de savoir pour quels serveurs on attend une réponse de l'utilisateur pour la restauration.
        self.waiting_for_restore = {}
        try:
            spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
            spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
            if spotify_client_id and spotify_client_secret:
                self.sp = spotipy.Spotify(auth_manager=spotipy.SpotifyClientCredentials(client_id=spotify_client_id, client_secret=spotify_client_secret))
            else:
                self.sp = None
        except Exception as e:
            print(f"[Spotify Init Error] Could not initialize Spotipy: {e}")
            self.sp = None
        self.update_now_playing_loop.start()

    def cog_unload(self):
        """Appelé lorsque le cog est déchargé, pour arrêter proprement la boucle de mise à jour."""
        self.update_now_playing_loop.cancel()

    async def cog_load(self):
        """Appelé lorsque le cog est chargé, on en profite pour ajouter la vue persistante des contrôles."""
        self.bot.add_view(MusicControls())

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        """Confirme que la connexion au serveur de musique Lavalink est établie."""
        print(f"[Wavelink] Nœud '{payload.node.identifier}' est prêt.")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        """Lorsqu'une nouvelle musique commence, cette fonction envoie le message 'En cours de lecture'."""
        player = payload.player
        if not player:
            return

        embed = self.build_now_playing_embed(player)
        # On s'assure que l'attribut existe. S'il est déjà défini par une autre opération,
        # on ne l'écrase pas, sinon on l'initialise à None.
        if not hasattr(player, "now_playing_message"):
            player.now_playing_message = None
        player.now_playing_message = await player.home.send(embed=embed, view=MusicControls(self.bot))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Gère la fin d'une piste : supprime l'ancien message et lance la suivante si possible."""
        player = payload.player
        if not player:
            return

        # Nettoyer l'ancien message "En cours de lecture"
        if hasattr(player, "now_playing_message") and player.now_playing_message:
            try:
                await player.now_playing_message.delete()
            except (discord.HTTPException, AttributeError):
                pass

        # Wavelink gère automatiquement le passage à la piste suivante, mais on peut ajouter une logique personnalisée ici.
        if not player.queue.is_empty:
            # La méthode play() va automatiquement prendre la prochaine chanson de la file d'attente
            # si aucune piste n'est fournie.
            next_track = player.queue.get()
            await player.play(next_track)
        # Si la file est vide, on peut déconnecter le bot après un délai.
        elif payload.reason == "FINISHED":
             if player.home:
                 await player.home.send("✅ File d'attente terminée.")
             # On attend un court instant pour que le message soit visible avant de déconnecter.
             await asyncio.sleep(10) # Un délai un peu plus long pour éviter les déconnexions trop rapides
             await player.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_player_destroy(self, player: wavelink.Player):
        """Lorsque le lecteur est détruit (déconnexion), on sauvegarde son état."""
        if not player.queue.is_empty or player.current:
            await _save_state(player, player.guild.id)
            print(f"État de la musique sauvegardé pour le serveur {player.guild.id}")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        """Gère les erreurs qui peuvent survenir pendant la lecture d'une piste (ex: vidéo supprimée)."""
        player = payload.player
        track = payload.track
        exception = payload.exception

        # Log de l'erreur dans la console pour le débogage
        print(f"--- Wavelink Track Exception ---")
        # Il est possible que le lecteur soit détruit au moment où l'exception se produit.
        if player and player.guild:
            print(f"Serveur: {player.guild.name} ({player.guild.id})")
        else:
            print("Serveur: Inconnu (lecteur détruit)")
        print(f"Piste: {track.title if track else 'Piste inconnue'}")
        print(f"Exception: {exception}")
        print(f"---------------------------------")

        # Informer l'utilisateur dans le salon où la commande a été lancée
        if player and player.home:
            await player.home.send(f"❌ Une erreur est survenue lors de la lecture de **{track.title if track else 'la piste'}**. Passage à la suivante si possible.")

    def build_now_playing_embed(self, player: wavelink.Player) -> discord.Embed:
        """Construit l'embed 'En cours de lecture' avec la barre de progression et les informations sur la piste."""
        track = player.current
        if not track:
            return discord.Embed(title="Rien n'est en cours de lecture", color=discord.Color.greyple())

        embed = discord.Embed(title="🎵 En cours de lecture", color=discord.Color.green())
        embed.description = f"**{track.title}**"

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        # Barre de progression
        if track.length > 0:
            position = player.position
            progress = int((position / track.length) * 20)
            bar = '▬' * progress + '🔘' + '▬' * (19 - progress)
            
            def format_duration(seconds):
                m, s = divmod(int(seconds), 60)
                h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

            embed.add_field(name="Progression", value=f"`{format_duration(position / 1000)}` {bar} `{format_duration(track.length / 1000)}`", inline=False)

        # Prochain titre
        next_song_title = "Rien"
        if not player.queue.is_empty:
            next_song_title = player.queue[0].title
        embed.add_field(name="Prochain titre", value=next_song_title, inline=True)

        # Demandé par
        requester_id = track.extras["requester_id"] if "requester_id" in track.extras else None
        requester = self.bot.get_user(requester_id)
        if requester:
            embed.add_field(name="Demandé par", value=requester.mention, inline=True)

        return embed

    def _parse_seek_time(self, time_str: str) -> int | None: # noqa
        """Convertit une chaîne de temps flexible (ex: '1m30s', '1:30', '90') en secondes."""
        # Gère le format "HH:MM:SS" ou "MM:SS"
        if ':' in time_str:
            try:
                parts = list(map(int, time_str.split(':')))
                seconds = 0
                for i, part in enumerate(reversed(parts)):
                    seconds += part * (60**i)
                return seconds
            except ValueError:
                return None # Format invalide comme "1:a"
        
        # Gère le format "1d12h30m5s"
        regex = re.compile(r'(\d+)([smhd])')
        parts = regex.findall(time_str.lower())
        if parts:
            time_params = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
            unit_map = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
            for value, unit in parts:
                time_params[unit_map[unit]] += int(value)
            return int(timedelta(**time_params).total_seconds())

        # Gère un nombre simple de secondes
        try:
            return int(time_str)
        except ValueError:
            return None

    def _clean_search_query(self, artist: str, title: str) -> str:
        """Nettoie le nom de l'artiste et le titre pour optimiser la recherche sur YouTube."""
        # Supprimer les parenthèses, crochets et leur contenu
        title = re.sub(r'[\(\[].*?[\)\]]', '', title)
        # Supprimer les mots-clés courants et "feat."
        title = re.sub(r'(?i)\s*(official|video|audio|lyric|feat|ft)\.?\s*', ' ', title)
        # Supprimer la plupart des caractères spéciaux, en gardant les espaces
        artist = re.sub(r'[^\w\s-]', '', artist)
        title = re.sub(r'[^\w\s-]', '', title)
        return f"ytsearch:{artist.strip()} - {title.strip()}"

    @tasks.loop(seconds=20.0) # Augmentation de l'intervalle pour réduire la charge
    async def update_now_playing_loop(self):
        """Boucle qui s'exécute en arrière-plan pour mettre à jour les messages 'En cours de lecture' et gérer l'inactivité."""
        for node in wavelink.Pool.nodes.values():
            if node.status != wavelink.NodeStatus.CONNECTED:
                continue
            for player in node.players.values():
                # Mise à jour de l'embed "En cours de lecture"
                if player.playing and hasattr(player, "now_playing_message") and player.now_playing_message:
                    try:
                        embed = self.build_now_playing_embed(player)
                        await player.now_playing_message.edit(embed=embed)
                    except (discord.HTTPException, AttributeError):
                        player.now_playing_message = None
                
                # Déconnecte le bot s'il est inactif depuis trop longtemps.
                elif not player.playing and player.connected and player.queue.is_empty and player.guild.id not in self.waiting_for_restore: # noqa
                    # Ajout d'un délai de grâce avant la déconnexion
                    if not hasattr(player, 'inactive_since'):
                        player.inactive_since = discord.utils.utcnow()
                    
                    # Si le bot est inactif depuis plus de 30 secondes, on le déconnecte
                    if (discord.utils.utcnow() - player.inactive_since).total_seconds() > 30:
                        if hasattr(player, 'home') and player.home:
                            await player.home.send("✅ Inactif et file d'attente vide. Déconnexion.")
                        await player.disconnect()
                
                # Si le bot recommence à jouer, on réinitialise le timer d'inactivité
                elif player.playing and hasattr(player, 'inactive_since'):
                    del player.inactive_since



    music_group = app_commands.Group(name="musique", description="Commandes liées à la musique")

    @music_group.command(name="play", description="Joue une musique depuis YouTube/Spotify ou l'ajoute à la liste.")
    async def play(self, interaction: discord.Interaction, recherche: str):
        """Commande principale pour jouer de la musique."""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice:
            await interaction.followup.send("❌ Il faut être dans un salon vocal pour que je puisse vous rejoindre !", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        player: wavelink.Player = interaction.guild.voice_client

        if not player:
            try:
                # Si le bot n'est pas connecté, on le connecte au salon vocal de l'utilisateur.
                player: wavelink.Player = await voice_channel.connect(cls=wavelink.Player, timeout=60)
            except (discord.ClientException, asyncio.TimeoutError, wavelink.exceptions.ChannelTimeoutException):
                await interaction.followup.send("❌ Je suis déjà connecté à un autre salon vocal.")
                return
        elif player.channel != voice_channel:
            if player.playing or player.paused:
                await interaction.followup.send(f"❌ Je suis déjà en train de jouer de la musique dans le salon {player.channel.mention}. Veuillez me stopper ou attendre la fin avant de m'appeler ailleurs.", ephemeral=True)
                return
            await player.move_to(voice_channel)

        # On garde en mémoire le salon où la commande a été lancée pour y envoyer les messages.
        player.home = interaction.channel
        await player.set_volume(30)

        # S'il y a une sauvegarde, on demande à l'utilisateur s'il veut la restaurer.
        saved_state = _load_state_data(interaction.guild.id)
        if saved_state and saved_state.get("queue") and player.queue.is_empty and not player.playing:
            self.waiting_for_restore[interaction.guild.id] = True # Lever le drapeau d'attente
            view = RestoreQueueView(self, interaction, recherche)
            await interaction.followup.send("🔎 J'ai trouvé une file d'attente précédente pour ce serveur. Voulez-vous la restaurer avant d'ajouter votre nouvelle musique ?", view=view, ephemeral=True)
            return

        # On ajoute la chanson demandée à la file d'attente.
        is_first_song = player.queue.is_empty and not player.playing
        added_count = await self._add_song_to_queue(interaction, recherche)

        if added_count == 0:
            return

        # Si ce n'est pas la première chanson, on envoie une confirmation. Sinon, l'événement on_track_start s'en chargera.
        if not is_first_song:
            message = f"✅ {added_count} musique(s) ajoutée(s) à la file d'attente."
            await interaction.followup.send(message, ephemeral=True)

    @music_group.command(name="playnext", description="Joue une musique juste après la piste actuelle.")
    @app_commands.describe(recherche="Le nom de la musique ou l'URL YouTube/Spotify.")
    async def playnext(self, interaction: discord.Interaction, recherche: str):
        """Ajoute une musique en haut de la file d'attente."""
        await interaction.response.defer(ephemeral=True)

        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.connected:
            await interaction.followup.send("❌ Le bot n'est pas connecté. Utilisez `/musique play` d'abord.", ephemeral=True)
            return

        # Si la file est vide, cette commande se comporte comme un /play normal.
        if player.queue.is_empty:
            await interaction.followup.send("ℹ️ La file d'attente était vide, la musique est ajoutée normalement.", ephemeral=True)
            await self._add_song_to_queue(interaction, recherche)
            return
        
        added_count = await self._add_song_to_queue(interaction, recherche, add_to_top=True)
        if added_count > 0:
            await interaction.followup.send(f"✅ {added_count} musique(s) ajoutée(s) en haut de la file d'attente.", ephemeral=True)

    @music_group.command(name="seek", description="Avance ou recule la lecture à un moment précis.")
    @app_commands.describe(temps="Le moment où aller (ex: 1m30s, 90, 1:30).")
    async def seek(self, interaction: discord.Interaction, temps: str): # noqa
        """Permet de se déplacer à un moment précis de la chanson en cours."""
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("❌ Aucune musique n'est en cours de lecture.", ephemeral=True)

        seek_seconds = self._parse_seek_time(temps)
        if seek_seconds is None or seek_seconds < 0:
            return await interaction.response.send_message("❌ Format de temps invalide. Utilisez par exemple `1m30s` ou `90`.", ephemeral=True)

        song_duration_seconds = player.current.length / 1000
        if song_duration_seconds > 0 and seek_seconds >= song_duration_seconds:
            return await interaction.response.send_message("❌ Vous ne pouvez pas avancer au-delà de la fin de la musique.", ephemeral=True)

        await interaction.response.send_message(f"⏩ Avance à `{temps}`...", ephemeral=True)
        await player.seek(seek_seconds * 1000)

    async def _add_song_to_queue(self, interaction: discord.Interaction, query: str, add_to_top: bool = False) -> int:
        """Fonction interne pour rechercher et ajouter une ou plusieurs chansons à la file d'attente. Renvoie le nombre de pistes ajoutées."""
        player: wavelink.Player = interaction.guild.voice_client

        # --- Traitement spécial pour Spotify ---
        if self.sp and "open.spotify.com" in query:
            # On désactive temporairement la fonctionnalité Spotify pour stabiliser le bot.
            await interaction.followup.send(
                "⚠️ Les liens Spotify sont temporairement désactivés pour maintenance. Veuillez utiliser des termes de recherche YouTube (ex: nom de l'artiste - titre de la chanson).",
                ephemeral=True
            )
            return 0 # On arrête le traitement et on indique qu'aucune piste n'a été ajoutée.

        # --- Logique de recherche améliorée ---
        try:
            # 1. Nettoyage de la requête si ce n'est pas une URL
            if not is_valid_url(query):
                # Supprime les (feat. ...), [lyrics] etc. pour une meilleure recherche
                cleaned_query = re.sub(r'[\(\[].*?[\)\]]', '', query)
                # Supprime les mots-clés courants
                cleaned_query = re.sub(r'(?i)\s*(official|video|audio|lyric|feat|ft)\.?\s*', ' ', cleaned_query)
                # On garde que les caractères alphanumériques, espaces et tirets
                cleaned_query = re.sub(r'[^\w\s-]', '', cleaned_query).strip()
                
                search_query = f"scsearch:{cleaned_query}"
            else:
                search_query = query

            # 2. Lancement de la recherche
            tracks: wavelink.Search = await wavelink.Playable.search(search_query)


        except (wavelink.LavalinkException, wavelink.LavalinkLoadException) as e:
            print(f"[Wavelink Search Error] Guild: {interaction.guild.id}, Query: '{query}', Error: {e}")
            await interaction.followup.send("❌ Une erreur est survenue lors de la recherche. La vidéo est peut-être privée, soumise à une restriction d'âge, ou le lien est invalide. Veuillez essayer avec un autre lien ou un autre terme de recherche.", ephemeral=True)
            return 0

        if not tracks:
            await interaction.followup.send(f"❌ Impossible de trouver une correspondance pour `{query.replace('ytsearch:', '')}`.", ephemeral=True)
            return 0

        added_count = 0
        if isinstance(tracks, wavelink.Playlist):
            added_count = len(tracks.tracks)
            for track in tracks.tracks:
                track.extras = {"requester_id": interaction.user.id}
            player.queue.put(tracks.tracks)
        else:
            track = tracks[0]
            track.extras = {"requester_id": interaction.user.id}
            added_count = 1
            if add_to_top:
                player.queue.put_at_front(track)
            else:
                await player.queue.put_wait(track)
        
        if not player.playing:
            await player.play(player.queue.get())

        return added_count

    async def _add_multiple_tracks(self, interaction: discord.Interaction, queries: list[str], add_to_top: bool):
        """Fonction interne pour ajouter une liste de pistes (typiquement depuis une playlist) à la file d'attente."""
        player: wavelink.Player = interaction.guild.voice_client
        added_count = 0
        failed_tracks = []
        
        # Pour ajouter en haut, on doit inverser la liste des requêtes
        track_list_for_queue = []

        for query in queries:
            try:
                await asyncio.sleep(0.2)
                tracks = await wavelink.Playable.search(query) # noqa

                # Stratégie de secours également pour les playlists
                if not tracks and query.startswith("ytsearch:"):
                    parts = query.split(' - ', 1)
                    if len(parts) > 1:
                        simple_query = f"ytsearch:{parts[1].strip()}"
                        tracks = await wavelink.Playable.search(simple_query)

                if tracks:
                    track = tracks[0]
                    track.extras = {"requester_id": interaction.user.id}
                    track_list_for_queue.append(track)
                    added_count += 1
                else:
                    print(f"[Music Search Error] Échec de la recherche pour la piste de playlist : '{query}'")
                    # La recherche n'a rien donné, on note le nom pour le rapport
                    failed_tracks.append(query.replace("ytsearch:", "").strip())
            except Exception as e:
                print(f"[Music Search Error] Failed to process query '{query}': {e}")
                failed_tracks.append(query.replace("ytsearch:", "").strip())
                continue # On ignore les pistes qui ne peuvent pas être trouvées

        if add_to_top:
            player.queue.put_at_front(reversed(track_list_for_queue))
        else:
            player.queue.put(track_list_for_queue)

        if not player.playing and not player.queue.is_empty:
            await player.play(player.queue.get())

        # Envoyer un message de confirmation final
        final_message = f"✅ **{added_count} / {len(queries)}** musiques de la playlist Spotify ont été ajoutées à la file d'attente."
        if failed_tracks:
            failed_list = "\n".join([f"- `{name}`" for name in failed_tracks[:5]]) # Affiche les 5 premiers échecs
            final_message += f"\n\n❌ Impossible de trouver une correspondance pour **{len(failed_tracks)}** musique(s), dont :\n{failed_list}"
            if len(failed_tracks) > 5:
                final_message += f"\n...et {len(failed_tracks) - 5} autres."
        await interaction.channel.send(final_message)

    @music_group.command(name="queue", description="Affiche la file d'attente actuelle")
    async def queue(self, interaction: discord.Interaction):
        """Affiche les 10 prochaines chansons de la file d'attente."""
        player: wavelink.Player = interaction.guild.voice_client # noqa
        if not player or player.queue.is_empty:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0

        for i, track in enumerate(player.queue):
            line = f"`{i+1}.` {track.title}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(player.queue) > displayed_count:
            embed.set_footer(text=f"et {len(player.queue) - displayed_count} autre(s) morceau(x).")

        await interaction.response.send_message(embed=embed)

    @music_group.command(name="clear", description="Vide la file d'attente")
    async def clear(self, interaction: discord.Interaction): # noqa
        """Supprime toutes les chansons de la file d'attente."""
        player: wavelink.Player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("🎶 La file d'attente est déjà vide.", ephemeral=True)
            return
        player.queue.clear()
        await interaction.response.send_message("🧹 La file d'attente a été vidée.")

    @music_group.command(name="shuffle", description="Mélange la file d'attente.")
    async def shuffle(self, interaction: discord.Interaction): # noqa
        """Mélange aléatoirement l'ordre des chansons dans la file d'attente."""
        player: wavelink.Player = interaction.guild.voice_client
        if not player or len(player.queue) < 2:
            await interaction.response.send_message("❌ Il n'y a pas assez de musiques dans la file d'attente pour les mélanger.", ephemeral=True)
            return
        
        player.queue.shuffle()
        await interaction.response.send_message("🔀 La file d'attente a été mélangée !")

    @music_group.command(name="loop", description="Répète la musique ou la file d'attente.")
    @app_commands.describe(mode="Choisissez le mode de répétition.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Musique actuelle (track)", value="track"),
        app_commands.Choice(name="File d'attente (queue)", value="queue"),
        app_commands.Choice(name="Désactivé (off)", value="off"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Définit le mode de répétition : désactivé, piste actuelle, ou toute la file d'attente."""
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

        if mode.value == "off":
            player.queue.mode = wavelink.QueueMode.normal
            await interaction.response.send_message("🔁 Répétition désactivée.")
        elif mode.value == "track":
            player.queue.mode = wavelink.QueueMode.loop
            await interaction.response.send_message(f"🔁 Répétition activée pour : **{mode.name}**.")
        elif mode.value == "queue":
            player.queue.mode = wavelink.QueueMode.loop_all
            await interaction.response.send_message(f"🔁 Répétition activée pour : **{mode.name}**.")

    @music_group.command(name="volume", description="Règle le volume du bot pour la musique (0-100).")
    @app_commands.describe(niveau="Le pourcentage de volume souhaité.")
    async def volume(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 0, 100]):
        """Règle le volume du lecteur de musique."""
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("❌ Le bot n'est connecté à aucun salon vocal.", ephemeral=True)
            return
        
        if not player.playing:
            await interaction.response.send_message("🤔 Aucune lecture en cours pour ajuster le volume.", ephemeral=True)
            return

        await player.set_volume(niveau)
        await interaction.response.send_message(f"🔊 Volume de la musique réglé à **{niveau}%**.")

async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(MusicCog(bot))