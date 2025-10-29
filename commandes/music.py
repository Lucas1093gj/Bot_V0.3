import discord
import os
import spotipy
import json
import asyncio
import random
import yt_dlp
from discord.ext import commands # noqa
from discord import app_commands
from spotipy.oauth2 import SpotifyClientCredentials

# --- Constantes ---
QUEUE_BACKUP_DIR = "queue_backups"
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

# Initialisation de l'API Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
spotify_auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
spotify = spotipy.Spotify(auth_manager=spotify_auth_manager)

# --- Fonctions de gestion de la sauvegarde de la file d'attente ---
def _save_queue(guild_id: int, queue: list):
    """Sauvegarde la file d'attente d'un serveur dans un fichier JSON."""
    if not os.path.exists(QUEUE_BACKUP_DIR):
        os.makedirs(QUEUE_BACKUP_DIR)
    filepath = os.path.join(QUEUE_BACKUP_DIR, f"{guild_id}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=4)

def _load_queue(guild_id: int) -> list | None:
    """Charge la file d'attente d'un serveur depuis un fichier JSON, si elle existe."""
    filepath = os.path.join(QUEUE_BACKUP_DIR, f"{guild_id}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def _delete_queue_backup(guild_id: int):
    """Supprime le fichier de sauvegarde de la file d'attente d'un serveur."""
    filepath = os.path.join(QUEUE_BACKUP_DIR, f"{guild_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)


# --- Vue avec les boutons de contrôle ---
class MusicControls(discord.ui.View):
    def __init__(self, music_cog, interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.interaction = interaction

    @discord.ui.button(label="⏯️ Pause/Reprendre", style=discord.ButtonStyle.primary)
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

    @discord.ui.button(label="⏭️ Passer", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Musique passée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucune musique à passer.", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            _save_queue(interaction.guild.id, self.music_cog.bot.music_queues.get(interaction.guild.id, []))
            vc.stop()
            await vc.disconnect()
            self.music_cog.bot.music_queues[interaction.guild.id] = []
            await interaction.response.send_message("⏹️ Lecture arrêtée et file d'attente vidée.", ephemeral=True) # noqa
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté.", ephemeral=True)

    @discord.ui.button(label="👋 Quitter", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            _save_queue(interaction.guild.id, self.music_cog.bot.music_queues.get(interaction.guild.id, []))
            await vc.disconnect()
            await interaction.response.send_message("👋 Le bot a quitté le salon vocal.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Le bot n'est pas connecté à un salon vocal.", ephemeral=True)

    @discord.ui.button(label="📜 File d'attente", style=discord.ButtonStyle.secondary)
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        queue_list = self.music_cog.bot.music_queues.get(guild_id, [])

        if not queue_list:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0

        for i, song in enumerate(queue_list):
            line = f"`{i+1}.` {song['title']}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(queue_list) > displayed_count:
            embed.set_footer(text=f"et {len(queue_list) - displayed_count} autre(s) morceau(x).")

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
        _delete_queue_backup(self.guild_id)
        await self.interaction.edit_original_response(content="Délai dépassé. La sauvegarde a été ignorée.", view=None)
        # On pourrait lancer la lecture de la chanson demandée ici si nécessaire

    @discord.ui.button(label="✅ Restaurer la file d'attente", style=discord.ButtonStyle.success)
    async def restore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        loaded_queue = _load_queue(self.guild_id)
        if loaded_queue:
            self.music_cog.bot.music_queues[self.guild_id] = loaded_queue
            await self.music_cog._add_song_to_queue(self.interaction, self.query, self.interaction.guild.voice_client, from_restore=True)
            await self.interaction.edit_original_response(content="✅ File d'attente restaurée ! La lecture va commencer.", view=None)
        else:
            await self.interaction.edit_original_response(content="❌ Impossible de trouver la sauvegarde.", view=None)
        
        _delete_queue_backup(self.guild_id)
        self.stop()

    @discord.ui.button(label="🗑️ Ignorer", style=discord.ButtonStyle.secondary)
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        _delete_queue_backup(self.guild_id)
        await self.interaction.edit_original_response(content="🗑️ Sauvegarde ignorée. Lancement d'une nouvelle file d'attente.", view=None)
        await self.music_cog._add_song_to_queue(self.interaction, self.query, self.interaction.guild.voice_client)
        self.stop()

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Sauvegarde la file d'attente si le bot est déconnecté manuellement."""
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            _save_queue(before.channel.guild.id, self.bot.music_queues.get(before.channel.guild.id, []))

    def _search_yt(self, query):
        """Recherche sur YouTube. C'est une fonction bloquante, à lancer dans un executor."""
        ydl_opts_search = {'format': 'bestaudio', 'noplaylist': 'True', 'default_search': 'ytsearch1', 'quiet': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info and info['entries']:
                    video = info['entries'][0]
                    return {
                        'url': video.get('webpage_url', ''),
                        'title': video.get('title', 'Titre inconnu')
                    }
        except Exception as e:
            print(f"Erreur yt-dlp pour '{query}': {e}")
        return None

    async def _process_spotify_playlist(self, tracks, guild_id, interaction):
        """Cherche et ajoute les pistes d'une playlist Spotify à la file d'attente."""
        for item in tracks:
            track = item['track']
            if not track or not track.get('artists'):
                continue

            artist_name = track['artists'][0]['name'] if track['artists'] else ''
            search_query = f"{track['name']} {artist_name}"
            song_info = await self.bot.loop.run_in_executor(None, self._search_yt, search_query)
            if song_info:
                self.bot.music_queues[guild_id].append(song_info)

    async def play_next(self, interaction: discord.Interaction, last_song_info: dict = None):
        guild_id = interaction.guild.id
        vc = interaction.guild.voice_client
        if not vc:
            return

        # Gérer la boucle avant de passer à la suivante
        loop_mode = self.bot.loop_states.get(guild_id)
        if last_song_info:
            if loop_mode == 'track':
                self.bot.music_queues.get(guild_id, []).insert(0, last_song_info)
            elif loop_mode == 'queue':
                self.bot.music_queues.get(guild_id, []).append(last_song_info)

        if guild_id in self.bot.music_queues and self.bot.music_queues[guild_id]:
            # La file d'attente n'est pas vide, on joue la suivante

            song_info = self.bot.music_queues[guild_id].pop(0)
            video_url = song_info['url']
            title = song_info['title']

            ydl_opts_stream = {'format': 'bestaudio/best', 'quiet': True}
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts_stream) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    stream_url = info['url']

                volume = self.bot.bot_volume_levels.get(guild_id, 0.15)
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), volume=volume)
                
                # La fonction `after` est appelée à la fin de la lecture
                # On passe les infos de la chanson actuelle pour la gestion de la boucle
                vc.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(interaction, last_song_info=song_info)))
                
                await interaction.channel.send(f"▶️ En cours de lecture : **{title}**", view=MusicControls(self, interaction))

            except Exception as e:
                print(f"Erreur lors de la lecture de {title}: {e}")
                await interaction.channel.send(f"❌ Erreur lors de la lecture de **{title}**. Passage à la suivante.")
                await self.play_next(interaction) # On tente de passer à la suivante
        else:
            # La file d'attente est vide, on réinitialise l'état de la boucle
            self.bot.loop_states[guild_id] = None

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
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        guild_id = interaction.guild.id
        if guild_id not in self.bot.music_queues:
            self.bot.music_queues[guild_id] = []

        # Vérifier s'il y a une sauvegarde de file d'attente
        saved_queue = _load_queue(guild_id)
        if saved_queue and not vc.is_playing():
            view = RestoreQueueView(self, interaction, query)
            await interaction.followup.send("🔎 J'ai trouvé une file d'attente précédente pour ce serveur. Voulez-vous la restaurer ?", view=view, ephemeral=True)
            return

        if "spotify.com" in query:
            try:
                if "playlist" in query:
                    results = spotify.playlist_items(query)
                    playlist_tracks = results['items']
                    if not playlist_tracks:
                        await interaction.followup.send("❌ La playlist Spotify est vide ou inaccessible.", ephemeral=True)
                        return

                    await interaction.followup.send(f"🔍 Ajout de la playlist Spotify en cours...")

                    # Traiter la première chanson immédiatement pour démarrer la lecture
                    first_track_item = playlist_tracks.pop(0)
                    first_track = first_track_item['track']
                    if first_track and first_track.get('artists'):
                        artist_name = first_track['artists'][0]['name'] if first_track['artists'] else ''
                        search_query = f"{first_track['name']} {artist_name}"
                        # Exécute la recherche en arrière-plan pour ne pas bloquer
                        song_info = await self.bot.loop.run_in_executor(None, self._search_yt, search_query)
                        if song_info:
                            self.bot.music_queues[guild_id].append(song_info)
                        
                    # Lancer la lecture si rien n'est en cours
                    if not vc.is_playing():
                        await self.play_next(interaction)

                    # Lancer le traitement du reste de la playlist en arrière-plan
                    self.bot.loop.create_task(self._process_spotify_playlist(playlist_tracks, guild_id, interaction))

                elif "track" in query:
                    track = spotify.track(query)
                    if track and track.get('artists'):
                        artist_name = track['artists'][0]['name'] if track['artists'] else ''
                        search_query = f"{track['name']} {artist_name}"
                        await self._add_song_to_queue(interaction, search_query, vc)
                        await interaction.followup.send(f"✅ **{track['name']}** ajouté à la file d'attente.")
            except Exception as e:
                await interaction.followup.send(f"❌ Erreur lors de la recherche sur Spotify : {e}", ephemeral=True)
                return
        else:
            # Pour une recherche simple (YouTube)
            await self._add_song_to_queue(interaction, query, vc)
            await interaction.followup.send(f"✅ **{query}** ajouté à la file d'attente.")

    @music_group.command(name="playnext", description="Joue une musique juste après la piste actuelle.")
    @app_commands.describe(recherche="Le nom de la musique ou l'URL YouTube/Spotify.")
    async def playnext(self, interaction: discord.Interaction, recherche: str):
        """Ajoute une musique en haut de la file d'attente."""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice:
            await interaction.followup.send("❌ Vous devez être dans un salon vocal.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.followup.send("❌ Le bot n'est pas connecté. Utilisez `/musique play` d'abord.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        if guild_id not in self.bot.music_queues or not self.bot.music_queues[guild_id]:
            await interaction.followup.send("❌ La file d'attente est vide. Utilisez `/musique play` pour ajouter cette musique.", ephemeral=True)
            return

        song_info = await self.bot.loop.run_in_executor(None, self._search_yt, recherche)

        if song_info:
            self.bot.music_queues[guild_id].insert(0, song_info)
            await interaction.followup.send(f"✅ **{song_info['title']}** sera jouée juste après la musique actuelle.", ephemeral=False)
        else:
            await interaction.followup.send(f"❌ Impossible de trouver une correspondance pour `{recherche}`.", ephemeral=True)

    async def _add_song_to_queue(self, interaction: discord.Interaction, query: str, vc: discord.VoiceClient, from_restore: bool = False, add_to_top: bool = False):
        """Recherche une chanson et l'ajoute à la file d'attente de manière non-bloquante."""
        guild_id = interaction.guild.id
        
        # Exécute la recherche bloquante dans un thread séparé
        song_info = await self.bot.loop.run_in_executor(None, self._search_yt, query)

        original_interaction_channel = interaction.channel

        if song_info:
            if add_to_top:
                self.bot.music_queues[guild_id].insert(0, song_info)
            else:
                self.bot.music_queues[guild_id].append(song_info)

            # Démarrer la lecture si le bot est inactif
            # Si on restaure, la lecture est déjà gérée par la vue. On lance play_next seulement si le bot est inactif.
            if not vc.is_playing() and not from_restore:
                await self.play_next(interaction)
        else:
            # Informer l'utilisateur si la recherche a échoué
            try:
                await original_interaction_channel.send(f"❌ Impossible de trouver une correspondance pour `{query}`.", delete_after=10)
            except discord.NotFound:
                pass # Le salon a peut-être été supprimé, on ignore l'erreur

    @music_group.command(name="queue", description="Affiche la file d'attente actuelle")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue_list = self.bot.music_queues.get(guild_id, [])

        if not queue_list:
            await interaction.response.send_message("🎶 La file d'attente est vide.", ephemeral=True)
            return

        embed = discord.Embed(title="🎶 File d'attente", color=discord.Color.blue())
        description = []
        total_length = 0
        displayed_count = 0

        for i, song in enumerate(queue_list):
            line = f"`{i+1}.` {song['title']}\n"
            if displayed_count < 10 and total_length + len(line) < 4000:
                description.append(line)
                total_length += len(line)
                displayed_count += 1
            else:
                break

        embed.description = "".join(description)
        if len(queue_list) > displayed_count:
            embed.set_footer(text=f"et {len(queue_list) - displayed_count} autre(s) morceau(x).")

        await interaction.response.send_message(embed=embed)

    @music_group.command(name="clear", description="Vide la file d'attente")
    async def clear(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.bot.music_queues:
            self.bot.music_queues[guild_id] = []
            await interaction.response.send_message("🧹 La file d'attente a été vidée.")
        else:
            await interaction.response.send_message("🎶 La file d'attente est déjà vide.", ephemeral=True)

    @music_group.command(name="shuffle", description="Mélange la file d'attente.")
    async def shuffle(self, interaction: discord.Interaction): # noqa
        """Mélange la file d'attente actuelle du serveur."""
        guild_id = interaction.guild.id
        queue_list = self.bot.music_queues.get(guild_id)

        if not queue_list or len(queue_list) < 2:
            await interaction.response.send_message("❌ Il n'y a pas assez de musiques dans la file d'attente pour les mélanger.", ephemeral=True)
            return

        random.shuffle(queue_list)
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
        
        if mode.value == "off":
            self.bot.loop_states[guild_id] = None
            await interaction.response.send_message("🔁 Répétition désactivée.")
        else:
            self.bot.loop_states[guild_id] = mode.value
            await interaction.response.send_message(f"🔁 Répétition activée pour : **{mode.name}**.")


async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(MusicCog(bot))