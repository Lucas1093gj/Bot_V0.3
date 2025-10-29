import discord
from discord import app_commands
from discord.ext import commands
from .music import FFMPEG_OPTIONS # On peut garder cet import car il est simple et ne dépend de rien d'autre

# Dictionnaire des URLs de flux radio
RADIO_STREAMS = {
    # URLs de flux audio directs pour une meilleure compatibilité avec FFMPEG
    "RTL": "http://rtlcms.ice.infomaniak.ch/rtlcms-high.mp3",
    "NRJ": "http://cdn.nrjaudio.fm/audio1/fr/30001/mp3_128.mp3",
    "Contact": "http://icecast.rtbf.be/contact-128.mp3",
    "FunRadio": "http://funradio.ice.infomaniak.ch/funradio-high.mp3",
}

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
        await interaction.response.defer(ephemeral=False)

        if not interaction.user.voice:
            await interaction.followup.send("❌ Rejoignez d'abord un salon vocal pour lancer la radio.", ephemeral=True)
            return

        stream_url = RADIO_STREAMS.get(station.value)
        # Trouver la station par son nom
        if not stream_url:
            await interaction.followup.send(f"❌ La station {station.name} n'est pas configurée.", ephemeral=True)
            return

        # 1. Connexion au salon vocal
        try:
            vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect()
        except discord.ClientException:
            await interaction.followup.send("❌ Le bot est déjà connecté ailleurs.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur de connexion vocale: {e}", ephemeral=True)
            return

        # 2. Arrêter la musique ou la radio précédente
        if vc.is_playing() or vc.is_paused():
            vc.stop()

        # On vide la file d'attente de musique car la radio est un flux continu
        if interaction.guild.id in self.bot.music_queues:
            self.bot.music_queues[interaction.guild.id] = []

        # 3. Démarrer le flux radio
        guild_id = interaction.guild.id
        # Assurer un volume par défaut (15%) si non défini
        volume = self.bot.bot_volume_levels.get(guild_id, 0.15)
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), volume=volume)

        vc.play(source, after=lambda e: print(f'Erreur de lecture radio: {e}') if e else None)

        embed = discord.Embed(
            title=f"📻 Lecture en cours : {station.name}",
            description=f"Le bot diffuse maintenant la radio en direct. Utilisez `/musique volume` pour ajuster le son.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(RadioCog(bot))