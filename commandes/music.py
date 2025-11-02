import discord
import os
import spotipy
from dataclasses import asdict
from dataclasses import dataclass, field
import json
import asyncio
import random, time
import yt_dlp
from discord.ext import commands # noqa
from discord.ext import tasks
from discord import app_commands
from spotipy.oauth2 import SpotifyClientCredentials

# --- Constantes ---
STATE_BACKUP_DIR = "music_state_backups"
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

# Initialisation de l'API Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
spotify_auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
spotify = spotipy.Spotify(auth_manager=spotify_auth_manager)

# --- Structure de données pour l'état de la musique par serveur ---
@dataclass
class GuildMusicState:
    """Classe pour stocker l'état de la musique pour un serveur spécifique."""
    queue: list = field(default_factory=list)
    loop_mode: str | None = None
    volume: float = 0.15
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    text_channel_id: int | None = None
    now_playing_message: discord.Message | None = None
    disconnect_timer: asyncio.Task | None = None
    song_start_time: float = 0.0
    now_playing_info: dict | None = None

    def to_dict(self) -> dict:
        """Convertit l'état en un dictionnaire sérialisable en JSON."""
        return {
            "queue": self.queue,
            "loop_mode": self.loop_mode,
            "volume": self.volume,
            "text_channel_id": self.text_channel_id,
            # On exclut volontairement lock, now_playing_message, disconnect_timer, etc.
        }


# --- Fonctions de gestion de la sauvegarde de la file d'attente ---
def _save_state(guild_id: int, state: GuildMusicState):
    """Sauvegarde l'état complet de la musique d'un serveur dans un fichier JSON."""
    if not os.path.exists(STATE_BACKUP_DIR):
        os.makedirs(STATE_BACKUP_DIR)
    filepath = os.path.join(STATE_BACKUP_DIR, f"{guild_id}.json")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        # Utiliser notre méthode personnalisée pour la sérialisation
        json.dump(state.to_dict(), f, indent=4)

def _load_state(guild_id: int) -> dict | None:
    """Charge l'état de la musique d'un serveur depuis un fichier JSON, si il existe."""
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
    """Supprime le fichier de sauvegarde de la file d'attente d'un serveur."""
    filepath = os.path.join(STATE_BACKUP_DIR, f"{guild_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)


# --- Vue avec les boutons de contrôle ---
class MusicControls(discord.ui.View):
    def __init__(self, music_cog):
        super().__init__(timeout=None)
        # On passe directement les instances nécessaires pour éviter de stocker l'interaction
        self.music_cog = music_cog

    @discord.ui.button(label="⏯️ Pause/Reprendre", style=discord.ButtonStyle.primary, custom_id="music_pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        # Correction : On vérifie si le bot n'est ni en train de jouer, ni en pause.
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await interaction.response.send_message("❌ Il n'y a aucune musique en cours de lecture ou en pause.", ephemeral=True)
        
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Musique reprise.", ephemeral=True)
        else:
            vc.pause()
            await interaction.response.send_message("⏸️ Musique mise en pause.", ephemeral=True)

    @discord.ui.button(label="⏭️ Passer", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Musique passée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucune musique à passer.", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            state = self.music_cog.get_guild_state(interaction.guild.id)
            async with state.lock:
                state.queue.clear()
                _save_state(interaction.guild.id, state)
            vc.stop()
            await interaction.response.send_message("⏹️ Lecture arrêtée et file d'attente vidée.", ephemeral=True) # noqa
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

    @discord.ui.button(label="👋 Quitter", style=discord.ButtonStyle.secondary, custom_id="music_leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            state = self.music_cog.get_guild_state(interaction.guild.id)
            # La sauvegarde est maintenant automatique, mais on peut la forcer ici pour être sûr
            _save_state(interaction.guild.id, state)
            await vc.disconnect()
            await interaction.response.send_message("👋 Le bot a quitté le salon vocal.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

    @discord.ui.button(label="📜 File d'attente", style=discord.ButtonStyle.secondary, custom_id="music_queue")
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.music_cog.get_guild_state(interaction.guild.id)

        if not state.queue:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0

        for i, song in enumerate(state.queue):
            line = f"`{i+1}.` {song['title']}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(state.queue) > displayed_count:
            embed.set_footer(text=f"et {len(state.queue) - displayed_count} autre(s) morceau(x).")

        await interaction.response.send_message(embed=embed, ephemeral=True)

class RestoreQueueView(discord.ui.View):
    def __init__(self, music_cog, interaction: discord.Interaction, query: str):
        super().__init__(timeout=60)
        self.music_cog = music_cog
        self.interaction = interaction
        self.query = query
        self.guild_id = interaction.guild.id

    async def on_timeout(self):
        """Si l'utilisateur ne répond pas, on supprime la sauvegarde et on continue normalement."""
        _delete_state_backup(self.guild_id)
        await self.interaction.edit_original_response(content="Délai dépassé. La sauvegarde a été ignorée.", view=None)
        # On pourrait lancer la lecture de la chanson demandée ici si nécessaire

    @discord.ui.button(label="✅ Restaurer la file d'attente", style=discord.ButtonStyle.success)
    async def restore(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Sécurisation : désactiver les boutons immédiatement pour éviter les double-clics
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        loaded_state_data = _load_state(self.guild_id)
        state = self.music_cog.get_guild_state(self.guild_id)
        
        if loaded_state_data and loaded_state_data.get("queue"):
            async with state.lock:
                # Restaurer l'état complet
                state.queue = loaded_state_data.get("queue", [])
                state.loop_mode = loaded_state_data.get("loop_mode")
                state.volume = loaded_state_data.get("volume", 0.15)
                
                # Ajouter la nouvelle chanson demandée
                await self.music_cog._add_song_to_queue(self.interaction, self.query, from_restore=True)
            
            await self.interaction.edit_original_response(content="✅ État précédent (file d'attente, volume, boucle) restauré ! La lecture va commencer.", view=None)
        else:
            # Si la sauvegarde est vide ou corrompue, on continue normalement
            await self.interaction.edit_original_response(content="❌ Impossible de trouver la sauvegarde. Lancement d'une nouvelle file d'attente.", view=None)
            await self.music_cog._add_song_to_queue(self.interaction, self.query)
        
        _delete_state_backup(self.guild_id)
        self.stop()

    @discord.ui.button(label="🗑️ Ignorer", style=discord.ButtonStyle.secondary)
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        _delete_state_backup(self.guild_id)
        await self.interaction.edit_original_response(content="🗑️ Sauvegarde ignorée. Lancement d'une nouvelle file d'attente.", view=None)
        await self.music_cog._add_song_to_queue(self.interaction, self.query)
        self.stop()

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Démarrer la boucle de mise à jour de l'affichage
        self.update_now_playing_loop.start()

    def get_guild_state(self, guild_id: int) -> GuildMusicState:
        """Récupère ou crée l'état de la musique pour un serveur."""
        if guild_id not in self.bot.music_states:
            self.bot.music_states[guild_id] = GuildMusicState()
        return self.bot.music_states[guild_id]

    def cog_unload(self):
        """Arrête la boucle de mise à jour lorsque le cog est déchargé."""
        self.update_now_playing_loop.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Gère la déconnexion automatique et la sauvegarde de la file d'attente."""
        # Ignore les mises à jour qui ne concernent pas le bot
        if not member.guild:
            return

        vc = member.guild.voice_client
        if not vc:
            return

        guild_id = member.guild.id
        state = self.get_guild_state(guild_id)

        # Si le bot est déconnecté manuellement, on sauvegarde la file d'attente
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            async with state.lock:
                _save_state(guild_id, state)
            return

        # Si le bot est seul dans le salon, on lance un timer de déconnexion
        if len(vc.channel.members) == 1 and vc.channel.members[0].id == self.bot.user.id:
            if state.disconnect_timer is None or state.disconnect_timer.done():
                state.disconnect_timer = self.bot.loop.create_task(self.auto_disconnect(guild_id, vc))

        # Si un utilisateur rejoint le salon où le bot est seul, on annule le timer
        elif len(vc.channel.members) > 1 and state.disconnect_timer and not state.disconnect_timer.done():
            state.disconnect_timer.cancel()
            state.disconnect_timer = None

    async def auto_disconnect(self, guild_id: int, vc: discord.VoiceClient):
        """Tâche qui déconnecte le bot après une période d'inactivité."""
        await asyncio.sleep(180)  # Attend 3 minutes
        await asyncio.sleep(30)  # Attend 30 secondes
        state = self.get_guild_state(guild_id)
        if vc.is_connected() and len(vc.channel.members) == 1:
            text_channel = self.bot.get_channel(state.text_channel_id)
            if text_channel:
                await text_channel.send("👋 Déconnexion pour inactivité.", delete_after=30)
            await vc.disconnect()
            # La sauvegarde se fera via l'événement on_voice_state_update

    def _search_yt(self, query):
        """Recherche sur YouTube. C'est une fonction bloquante, à lancer dans un executor."""
        ydl_opts_search = {'format': 'bestaudio', 'noplaylist': 'True', 'default_search': 'ytsearch1', 'quiet': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info and info['entries']:
                    video = info['entries'][0]
                    return {
                        'url': video.get('webpage_url'),
                        'title': video.get('title', 'Titre inconnu'),
                        'duration': video.get('duration', 0),
                        'thumbnail': video.get('thumbnail'),
                        'requester_id': None # Sera ajouté plus tard
                    }
        except Exception as e:
            print(f"Erreur yt-dlp pour '{query}': {e}")
        return None

    async def _process_spotify_playlist(self, tracks, state: GuildMusicState, guild_id: int, requester_id: int):
        """Cherche et ajoute les pistes d'une playlist Spotify à la file d'attente."""
        for item in tracks:
            track = item['track']
            if not track or not track.get('artists'):
                continue

            artist_name = track['artists'][0]['name'] if track['artists'] else ''
            search_query = f"{track['name']} {artist_name}"
            song_info = await self.bot.loop.run_in_executor(None, self._search_yt, search_query)
            if song_info:
                song_info['requester_id'] = requester_id
                state.queue.append(song_info)
        # Sauvegarder la file d'attente après l'ajout de toute la playlist
        _save_state(guild_id, state)

    async def play_next(self, guild_id: int, last_song_info: dict = None):
        state = self.get_guild_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        if not guild: return

        vc = guild.voice_client
        if not vc:
            return

        async with state.lock:
            # Gérer la boucle avant de passer à la suivante
            if last_song_info:
                if state.loop_mode == 'track':
                    state.queue.insert(0, last_song_info)
                elif state.loop_mode == 'queue':
                    state.queue.append(last_song_info)

            if not state.queue:
                # La file d'attente est vide, on réinitialise l'état de la boucle
                state.loop_mode = None
                if state.now_playing_message:
                    try:
                        await state.now_playing_message.delete()
                    except discord.HTTPException:
                        pass
                    state.now_playing_message = None
                return

            # La file d'attente n'est pas vide, on joue la suivante
            song_info = state.queue.pop(0)
            state.now_playing_info = song_info
            video_url = state.now_playing_info['url']

        # La recherche de stream peut être longue, on la sort du verrou
        stream_url = await self._get_stream_url(video_url) # Appel de la nouvelle fonction
        if not stream_url:
            text_channel = self.bot.get_channel(state.text_channel_id)
            if text_channel:
                await text_channel.send(f"❌ Erreur lors de la lecture de **{state.now_playing_info['title']}**. Passage à la suivante.")
            # On tente de passer à la suivante
            self.bot.loop.create_task(self.play_next(guild_id))
            return

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), volume=state.volume)
        
        # Enregistrer l'heure de début
        state.song_start_time = time.time()
        
        vc.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild_id, last_song_info=state.now_playing_info)))

        # Créer le message "En cours de lecture" initial
        text_channel = self.bot.get_channel(state.text_channel_id)
        if text_channel:
            if state.now_playing_message:
                try:
                    await state.now_playing_message.delete()
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass
            
            embed = self.build_now_playing_embed(state)
            state.now_playing_message = await text_channel.send(embed=embed, view=MusicControls(self))

    def build_now_playing_embed(self, state: GuildMusicState) -> discord.Embed:
        """Construit l'embed dynamique 'En cours de lecture'."""
        song = state.now_playing_info
        if not song:
            return discord.Embed(title="Rien n'est en cours de lecture", color=discord.Color.greyple())

        embed = discord.Embed(title="🎵 En cours de lecture", color=discord.Color.green())
        embed.description = f"**[{song['title']}]({song['url']})**"

        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])

        # Barre de progression
        if state.song_start_time > 0 and song['duration'] > 0:
            elapsed = time.time() - state.song_start_time
            progress = int((elapsed / song['duration']) * 20)
            bar = '▬' * progress + '🔘' + '▬' * (19 - progress)
            
            def format_duration(seconds):
                m, s = divmod(int(seconds), 60)
                h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

            embed.add_field(name="Progression", value=f"`{format_duration(elapsed)}` {bar} `{format_duration(song['duration'])}`", inline=False)

        # Prochain titre
        next_song_title = "Rien"
        if state.queue:
            next_song_title = state.queue[0]['title']
        embed.add_field(name="Prochain titre", value=next_song_title, inline=True)

        # Demandé par
        requester = self.bot.get_user(song.get('requester_id'))
        if requester:
            embed.add_field(name="Demandé par", value=requester.mention, inline=True)

        return embed

    async def _get_stream_url(self, video_url: str) -> str | None:
        """Extrait l'URL de streaming directe d'une URL de vidéo (YouTube, etc.)."""
        ydl_opts_stream = {'format': 'bestaudio/best', 'quiet': True}
        try:
            # Exécute la fonction bloquante dans un thread pour ne pas bloquer le bot
            with yt_dlp.YoutubeDL(ydl_opts_stream) as ydl:
                info = await self.bot.loop.run_in_executor(
                    None, lambda: ydl.extract_info(video_url, download=False)
                )
                return info['url']
        except Exception as e:
            print(f"Erreur lors de l'extraction de l'URL de stream pour {video_url}: {e}")
            return None

    def _parse_seek_time(self, time_str: str) -> int | None:
        """Convertit une chaîne de temps comme '1m30s' ou '1:30' en secondes."""
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
        import re
        regex = re.compile(r'(\d+)([smhd])')
        parts = regex.findall(time_str.lower())
        if parts:
            time_params = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
            unit_map = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
            for value, unit in parts:
                time_params[unit_map[unit]] += int(value)
            from datetime import timedelta
            return int(timedelta(**time_params).total_seconds())

        # Gère un nombre simple de secondes
        try:
            return int(time_str)
        except ValueError:
            return None

    async def _seek_in_current_song(self, guild_id: int, seek_seconds: int):
        """Relance la lecture de la chanson actuelle à un temps donné."""
        state = self.get_guild_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        vc = guild.voice_client

        if not vc or not state.now_playing_info:
            return

        song_to_replay = state.now_playing_info.copy()
        vc.stop()
        await asyncio.sleep(0.5) # Laisse le temps à vc.stop() de finir

        ffmpeg_options_seek = {
            'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_seconds}',
            'options': '-vn'
        }

        stream_url = await self._get_stream_url(song_to_replay['url']) # Appel de la nouvelle fonction
        if not stream_url:
            text_channel = self.bot.get_channel(state.text_channel_id)
            if text_channel:
                await text_channel.send(f"❌ Erreur lors de la tentative de seek sur **{song_to_replay['title']}**. Passage à la suivante.")
            self.bot.loop.create_task(self.play_next(guild_id))
            return

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options_seek), volume=state.volume)
        state.song_start_time = time.time() - seek_seconds
        vc.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild_id, last_song_info=state.now_playing_info)))

    @tasks.loop(seconds=10.0)
    async def update_now_playing_loop(self):
        """Met à jour tous les messages 'En cours de lecture' actifs."""
        for guild_id, state in self.bot.music_states.items():
            if state.now_playing_message and state.now_playing_info:
                try:
                    embed = self.build_now_playing_embed(state)
                    await state.now_playing_message.edit(embed=embed)
                except discord.HTTPException:
                    # Le message a probablement été supprimé, on l'oublie
                    state.now_playing_message = None

    music_group = app_commands.Group(name="musique", description="Commandes liées à la musique")

    @music_group.command(name="play", description="Joue une musique depuis YouTube/Spotify ou l'ajoute à la liste.")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            await interaction.followup.send("❌ Il faut être dans un salon vocal pour que je puisse vous rejoindre !", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if not vc:
            vc = await voice_channel.connect()
        # --- MODIFICATION : Empêcher le bot d'être "volé" ---
        elif vc.channel != voice_channel:
            # Si le bot est déjà en train de jouer ou en pause dans un autre salon
            if vc.is_playing() or vc.is_paused():
                await interaction.followup.send(f"❌ Je suis déjà en train de jouer de la musique dans le salon {vc.channel.mention}. Veuillez me stopper ou attendre la fin avant de m'appeler ailleurs.", ephemeral=True)
                return # On arrête l'exécution de la commande ici
            await vc.move_to(voice_channel) # Si le bot est inactif, on le déplace

        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)

        # Vérifier s'il y a une sauvegarde de file d'attente
        saved_state = _load_state(guild_id)
        if saved_state and saved_state.get("queue") and not state.queue and not vc.is_playing() and not vc.is_paused():
            view = RestoreQueueView(self, interaction, query)
            await interaction.followup.send("🔎 J'ai trouvé une file d'attente précédente pour ce serveur. Voulez-vous la restaurer avant d'ajouter votre nouvelle musique ?", view=view, ephemeral=True)
            return

        if "spotify.com" in query:
            try:
                if "playlist" in query:
                    playlist_tracks = []
                    results = spotify.playlist_items(query, limit=100)
                    playlist_tracks.extend(results['items'])
                    # Gérer la pagination pour les playlists de plus de 100 chansons
                    while results['next']:
                        results = spotify.next(results)
                        playlist_tracks.extend(results['items'])

                    if not playlist_tracks:
                        await interaction.followup.send("❌ La playlist Spotify est vide ou inaccessible.", ephemeral=True)
                        return

                    await interaction.followup.send(f"🔍 Ajout de la playlist Spotify en cours... ({len(playlist_tracks)} chansons)")

                    async with state.lock:
                        # Traiter la première chanson immédiatement pour démarrer la lecture
                        first_track_item = playlist_tracks.pop(0)
                        first_track = first_track_item['track']
                        if first_track and first_track.get('artists'):
                            artist_name = first_track['artists'][0]['name'] if first_track['artists'] else ''
                            search_query = f"{first_track['name']} {artist_name}"
                            song_info = await self.bot.loop.run_in_executor(None, self._search_yt, search_query)
                            if song_info:
                                song_info['requester_id'] = interaction.user.id
                                state.queue.append(song_info)
                                _save_state(guild_id, state)

                        # Lancer la lecture si rien n'est en cours
                        if not vc.is_playing():
                            state.text_channel_id = interaction.channel_id
                            self.bot.loop.create_task(self.play_next(guild_id))

                        # Lancer le traitement du reste de la playlist en arrière-plan
                        self.bot.loop.create_task(self._process_spotify_playlist(playlist_tracks, state, guild_id, interaction.user.id))

                elif "track" in query:
                    track = spotify.track(query)
                    if track and track.get('artists'):
                        artist_name = track['artists'][0]['name'] if track['artists'] else ''
                        search_query = f"{track['name']} {artist_name}"
                        added_song = await self._add_song_to_queue(interaction, search_query)
                        if added_song:
                            await interaction.followup.send(f"✅ **{added_song['title']}** ajouté à la file d'attente.")
            except Exception as e:
                await interaction.followup.send(f"❌ Erreur lors de la recherche sur Spotify : {e}", ephemeral=True)
                return
        else:
            # Pour une recherche simple (YouTube)
            # On vérifie si la file d'attente est vide pour adapter la réponse
            is_first_song = not state.queue and not vc.is_playing() and not vc.is_paused()
            
            added_song = await self._add_song_to_queue(interaction, query)

            # Si la file n'était pas vide, on envoie une confirmation.
            # Si elle était vide, play_next a déjà envoyé le message "En cours de lecture".
            if added_song and not is_first_song:
                await interaction.followup.send(f"✅ **{added_song['title']}** ajouté à la file d'attente.")

    @music_group.command(name="playnext", description="Joue une musique juste après la piste actuelle.")
    @app_commands.describe(recherche="Le nom de la musique ou l'URL YouTube/Spotify.")
    async def playnext(self, interaction: discord.Interaction, recherche: str):
        """Ajoute une musique en haut de la file d'attente."""
        await interaction.response.defer(ephemeral=True)

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.followup.send("❌ Le bot n'est pas connecté. Utilisez `/musique play` d'abord.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        # Amélioration : si la file est vide, on traite comme un /play normal
        if not state.queue:
            await interaction.followup.send("ℹ️ La file d'attente était vide, la musique est ajoutée normalement.", ephemeral=True)
            await self.play(interaction, query=recherche)
        else:
            added_song = await self._add_song_to_queue(interaction, recherche, add_to_top=True)
            if added_song:
                await interaction.followup.send(f"✅ **{added_song['title']}** sera jouée juste après la musique actuelle.", ephemeral=False)

    @music_group.command(name="seek", description="Avance ou recule la lecture à un moment précis.")
    @app_commands.describe(temps="Le moment où aller (ex: 1m30s, 90, 1:30).")
    async def seek(self, interaction: discord.Interaction, temps: str):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("❌ Aucune musique n'est en cours de lecture.", ephemeral=True)

        state = self.get_guild_state(interaction.guild.id)
        if not state.now_playing_info:
            return await interaction.response.send_message("❌ Aucune information sur la musique en cours.", ephemeral=True)

        seek_seconds = self._parse_seek_time(temps)
        if seek_seconds is None or seek_seconds < 0:
            return await interaction.response.send_message("❌ Format de temps invalide. Utilisez par exemple `1m30s` ou `90`.", ephemeral=True)

        song_duration = state.now_playing_info.get('duration', 0)
        if song_duration > 0 and seek_seconds >= song_duration:
            return await interaction.response.send_message("❌ Vous ne pouvez pas avancer au-delà de la fin de la musique.", ephemeral=True)

        await interaction.response.send_message(f"⏩ Avance à `{temps}`...")

        await self._seek_in_current_song(interaction.guild.id, seek_seconds)

    async def _add_song_to_queue(self, interaction: discord.Interaction, query: str, from_restore: bool = False, add_to_top: bool = False) -> dict | None:
        """Recherche une chanson et l'ajoute à la file d'attente de manière non-bloquante."""
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        vc = interaction.guild.voice_client

        # Exécute la recherche bloquante dans un thread séparé
        song_info = await self.bot.loop.run_in_executor(None, self._search_yt, query)

        if song_info:
            song_info['requester_id'] = interaction.user.id
            async with state.lock:
                if add_to_top:
                    state.queue.insert(0, song_info)
                else:
                    state.queue.append(song_info)
                
                _save_state(guild_id, state)

                # Démarrer la lecture si le bot est totalement inactif (ni en lecture, ni en pause)
                if not vc.is_playing() and not vc.is_paused() and not from_restore:
                    state.text_channel_id = interaction.channel_id
                    self.bot.loop.create_task(self.play_next(guild_id))
            return song_info
        else:
            # Informer l'utilisateur si la recherche a échoué
            await interaction.followup.send(f"❌ Impossible de trouver une correspondance pour `{query}`.", ephemeral=True)
            return None

    @music_group.command(name="queue", description="Affiche la file d'attente actuelle")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)

        if not state.queue:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0

        for i, song in enumerate(state.queue):
            line = f"`{i+1}.` {song['title']}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(state.queue) > displayed_count:
            embed.set_footer(text=f"et {len(state.queue) - displayed_count} autre(s) morceau(x).")

        await interaction.response.send_message(embed=embed)

    @music_group.command(name="clear", description="Vide la file d'attente")
    async def clear(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        async with state.lock:
            if not state.queue:
                await interaction.response.send_message("🎶 La file d'attente est déjà vide.", ephemeral=True)
                return
            state.queue.clear()
            _save_state(guild_id, state)
            await interaction.response.send_message("🧹 La file d'attente a été vidée.")

    @music_group.command(name="shuffle", description="Mélange la file d'attente.")
    async def shuffle(self, interaction: discord.Interaction): # noqa
        """Mélange la file d'attente actuelle du serveur."""
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        async with state.lock:
            if not state.queue or len(state.queue) < 2:
                await interaction.response.send_message("❌ Il n'y a pas assez de musiques dans la file d'attente pour les mélanger.", ephemeral=True)
                return
            random.shuffle(state.queue)
            _save_state(guild_id, state)
            await interaction.response.send_message("🔀 La file d'attente a été mélangée !")

    @music_group.command(name="loop", description="Répète la musique ou la file d'attente.")
    @app_commands.describe(mode="Choisissez le mode de répétition.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Musique actuelle (track)", value="track"),
        app_commands.Choice(name="File d'attente (queue)", value="queue"),
        app_commands.Choice(name="Désactivé (off)", value="off"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        
        if mode.value == "off":
            state.loop_mode = None
            _save_state(guild_id, state)
            await interaction.response.send_message("🔁 Répétition désactivée.")
        else:
            state.loop_mode = mode.value
            _save_state(guild_id, state)
            await interaction.response.send_message(f"🔁 Répétition activée pour : **{mode.name}**.")


async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(MusicCog(bot))