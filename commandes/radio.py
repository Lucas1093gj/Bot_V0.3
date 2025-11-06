import discord
from discord import app_commands
from discord.ext import commands
from .music import FFMPEG_OPTIONS

# Dictionnaire des URLs de flux radio
RADIO_STREAMS = {
    # URLs de flux audio directs pour une meilleure compatibilité avec FFMPEG
    "RTL": "http://rtlcms.ice.infomaniak.ch/rtlcms-high.mp3",
    "NRJ": "http://cdn.nrjaudio.fm/audio1/fr/30001/mp3_128.mp3",
    "Contact": "http://icecast.rtbf.be/contact-128.mp3",
    "FunRadio": "http://funradio.ice.infomaniak.ch/funradio-high.mp3",
}

class ConfirmRadioView(discord.ui.View):
    def __init__(self, radio_cog, interaction: discord.Interaction, station_choice: app_commands.Choice[str]):
        super().__init__(timeout=60)
        self.radio_cog = radio_cog
        self.interaction = interaction
        self.station_choice = station_choice

    async def on_timeout(self):
        await self.interaction.edit_original_response(content="⏰ Délai de confirmation dépassé. Opération annulée.", view=None)

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        # Désactiver les boutons
        for item in self.children:
            item.disabled = True
        await self.interaction.edit_original_response(view=self)
        # Lancer la logique de la radio
        await self.radio_cog.launch_radio(self.interaction, self.station_choice, confirmed=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        # Désactiver les boutons
        for item in self.children:
            item.disabled = True
        await self.interaction.edit_original_response(content="✅ Opération annulée. Votre file d'attente est intacte.", view=None)


class RadioCog(commands.Cog, name="Radio"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="radio", description="Lance une radio en direct dans votre salon vocal.")
    @app_commands.describe(
        station="Choisissez la station de radio à écouter."
    )
    @app_commands.choices(station=[
        app_commands.Choice(name="RTL", value="RTL"),
        app_commands.Choice(name="NRJ", value="NRJ"),
        app_commands.Choice(name="Radio Contact", value="Contact"),
        app_commands.Choice(name="Fun Radio", value="FunRadio"),
    ])
    async def radio(self, interaction: discord.Interaction, station: app_commands.Choice[str]):
        if not interaction.user.voice:
            await interaction.response.send_message("❌ Rejoignez d'abord un salon vocal pour lancer la radio.", ephemeral=True)
            return

        # Vérifier si une file d'attente musicale existe
        music_cog = self.bot.get_cog("MusicCog")
        if not music_cog:
            await interaction.response.send_message("❌ Le module de musique semble désactivé. Impossible de continuer.", ephemeral=True)
            return

        player: wavelink.Player = interaction.guild.voice_client
        if player and not player.queue.is_empty:
            embed = discord.Embed(
                title="⚠️ Confirmation Requise",
                description="Lancer la radio va **arrêter la musique actuelle et vider la file d'attente**.\n\nVoulez-vous continuer ?",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=ConfirmRadioView(self, interaction, station), ephemeral=True)
        else:
            # Pas de file d'attente, on lance directement
            await self.launch_radio(interaction, station, confirmed=False)

    async def launch_radio(self, interaction: discord.Interaction, station: app_commands.Choice[str], confirmed: bool = False):
        # Si la confirmation n'a pas été demandée, on doit différer la réponse initiale.
        if not interaction.response.is_done():
            await interaction.response.defer()

        stream_url = RADIO_STREAMS.get(station.value)

        try:
            vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect()
        except discord.ClientException:
            await interaction.followup.send("❌ Le bot est déjà connecté à un autre salon.", ephemeral=True, view=None)
            return

        if vc.is_playing() or vc.is_paused():
            vc.stop()

        # Vider la file d'attente
        player: wavelink.Player = interaction.guild.voice_client
        if player:
            player.queue.clear()

        # Le volume est géré par le player wavelink, pas par PCMVolumeTransformer ici.
        # Le volume sera appliqué par le player lui-même.
        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: print(f'Erreur de lecture radio: {e}') if e else None)

        embed = discord.Embed(
            title=f"📻 Lecture en cours : {station.name}",
            description=f"Le bot diffuse maintenant la radio en direct. Utilisez `/volume` pour ajuster le son.",
            color=discord.Color.green()
        )
        # Utiliser followup.send si la réponse a été différée, sinon edit_original_response si on vient d'une confirmation.
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=None)
        else: # Devrait être le cas de la confirmation
            await interaction.edit_original_response(embed=embed, view=None)

async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(RadioCog(bot))