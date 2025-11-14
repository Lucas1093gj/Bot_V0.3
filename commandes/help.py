import discord
from discord.ext import commands
from discord import app_commands
import os

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)  # Le message d'aide expirera après 3 minutes
        self.bot = bot
        self.add_item(HelpSelect(bot))

class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="Accueil", description="Retour à la page d'accueil de l'aide.", emoji="🏠"),
            discord.SelectOption(label="DiscordMaker", description="Commandes pour construire et gérer le serveur.", emoji="⚙️"),
            discord.SelectOption(label="Musique", description="Commandes pour le lecteur musical.", emoji="🎵"),
            discord.SelectOption(label="Modération", description="Outils pour les modérateurs.", emoji="🛡️"),
            discord.SelectOption(label="Tickets", description="Système de support pour contacter le staff.", emoji="🎟️"),
            discord.SelectOption(label="Utilitaires & Fun", description="Commandes utiles et amusantes pour tous.", emoji="🎉"),
        ]
        super().__init__(placeholder="Choisissez une catégorie...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # On utilise la valeur sélectionnée pour créer le bon embed
        embed = await self.create_help_embed(self.values[0], interaction.user.id)
        await interaction.response.edit_message(embed=embed)

    async def create_help_embed(self, category: str, user_id: int) -> discord.Embed:
        """Crée un embed d'aide basé sur la catégorie."""
        creator_id = int(os.getenv("CREATOR_ID")) if os.getenv("CREATOR_ID") else None
        is_creator = user_id == creator_id

        if category == "Accueil":
            return await self.create_main_embed()

        embed = discord.Embed(title=f"Aide - Catégorie : {category}", color=discord.Color.blurple())
        embed.set_footer(text="Utilisez le menu déroulant pour naviguer entre les catégories.")

        if category == "DiscordMaker":
            embed.title = "⚙️ Aide - DiscordMaker"
            embed.description = "Commandes pour construire et gérer la structure de votre serveur."
            embed.add_field(name="`/discordmaker setup`", value="Ouvre le panneau de configuration interactif pour choisir les rôles, salons, etc.", inline=False)
            embed.add_field(name="`/discordmaker start`", value="Lance la construction du serveur avec la configuration définie.", inline=False)
            embed.add_field(name="`/discordmaker reset`", value="Nettoie uniquement les rôles et salons créés par le bot.", inline=False)
            if is_creator:
                embed.add_field(name="`/discordmaker full-reset`", value="**(Owner)** Réinitialise **totalement** le serveur (une sauvegarde est envoyée en DM).", inline=False) # noqa
            embed.add_field(name="`/discordmaker post-roles`", value="Poste un message avec un menu déroulant pour que les membres puissent s'auto-attribuer des rôles.", inline=False)
        elif category == "Musique":
            embed.title = "🎵 Aide - Musique"
            embed.description = "Commandes pour animer vos salons vocaux avec de la musique."
            embed.add_field(name="`/musique play [recherche]`", value="Joue une musique ou playlist (YouTube, Spotify).", inline=False)
            embed.add_field(name="`/musique playnext [recherche]`", value="Ajoute une musique en haut de la file d'attente.", inline=False)
            embed.add_field(name="`/musique queue`", value="Affiche la file d'attente.", inline=False)
            embed.add_field(name="`/musique loop [mode]`", value="Répète la piste (`track`), la file d'attente (`queue`) ou désactive (`off`).", inline=False)
            embed.add_field(name="`/musique shuffle`", value="Mélange la file d'attente.", inline=False)
            embed.add_field(name="`/musique clear`", value="Vide la file d'attente.", inline=False)
            embed.add_field(name="`/musique seek [temps]`", value="Avance la lecture à un moment précis (ex: `1m30s`).", inline=False)

        elif category == "Modération":
            embed.title = "🛡️ Aide - Modération"
            embed.description = "Outils pour maintenir un environnement sain sur le serveur."
            embed.add_field(name="`/clear [nombre]`", value="Supprime un nombre de messages dans un salon.", inline=False)
            embed.add_field(name="`/warn [membre] [raison]`", value="Avertit un membre et enregistre l'avertissement.", inline=False)
            embed.add_field(name="`/warnings [membre ou ID]`", value="Affiche l'historique des avertissements d'un membre.", inline=False)
            embed.add_field(name="`/delwarn [id]`", value="Supprime un avertissement spécifique via son ID.", inline=False)
            embed.add_field(name="`/mute [membre] [durée] [raison]`", value="Applique un timeout à un membre (ex: `10m`, `2h`, `7d`).", inline=False)
            embed.add_field(name="`/unmute [membre]`", value="Retire le timeout d'un membre.", inline=False)
            embed.add_field(name="`/lock [salon] [raison]`", value="Verrouille un salon pour que les membres ne puissent plus y envoyer de messages.", inline=False)
            embed.add_field(name="`/unlock [salon]`", value="Déverrouille un salon.", inline=False)
            embed.add_field(name="`/getlog`", value="**(Admin)** Récupère la base de données des logs en message privé.", inline=False)

        elif category == "Tickets":
            embed.title = "🎟️ Aide - Tickets"
            embed.description = "Un système de support pour une communication privée et structurée entre les membres et le staff."
            embed.add_field(name="`/ticket open [sujet]`", value="Crée un salon privé (un \"ticket\") visible uniquement par vous et le staff pour discuter d'un problème.", inline=False)

        elif category == "Utilitaires & Fun":
            embed.title = "🎉 Aide - Utilitaires & Fun"
            embed.description = "Commandes diverses pour l'information et le divertissement."
            embed.add_field(name="`/help`", value="Affiche ce message d'aide.", inline=False)
            embed.add_field(name="`/ping`", value="Affiche la latence du bot.", inline=False)
            embed.add_field(name="`/serverinfo`", value="Affiche des informations détaillées sur le serveur.", inline=False)
            embed.add_field(name="`/userinfo [membre]`", value="Affiche des informations sur un membre.", inline=False)
            embed.add_field(name="`/poll [question] [options...]`", value="Crée un sondage simple avec des réactions.", inline=False)
            if is_creator:
                embed.add_field(name="`/restart`", value="**(Owner)** Redémarre le bot.", inline=False)

        return embed
    async def create_main_embed(self) -> discord.Embed:
        """Crée l'embed principal (page d'accueil de l'aide)."""
        embed = discord.Embed(
            title=f"👋 Aide pour {self.bot.user.name}",
            description=f"Bienvenue sur le panneau d'aide interactif ! Je suis un bot multifonction conçu pour vous aider à gérer et animer votre serveur.\n\n"
                        "**Utilisez le menu déroulant ci-dessous pour explorer mes commandes par catégorie.**",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Catégories Disponibles",
            value="""
            ⚙️ **DiscordMaker** : Créez un serveur de A à Z. # noqa: E501
            🎵 **Musique** : Animez vos salons vocaux.
            🛡️ **Modération** : Gardez votre communauté saine.
            🎟️ **Tickets** : Contactez le staff en privé.
            🎉 **Utilitaires & Fun** : Commandes diverses pour tous.
            """,
            inline=False
        )
        embed.set_footer(text=f"Bot v0.3 | Développé avec passion")
        return embed


class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Affiche le panneau d'aide interactif du bot.")
    async def help(self, interaction: discord.Interaction):
        """Affiche le message d'aide principal avec le menu déroulant."""
        # On crée l'instance de la vue et de l'embed initial
        view = HelpView(self.bot)
        # L'embed initial est créé par une méthode de la classe Select pour éviter la duplication de code
        initial_embed = await view.children[0].create_main_embed() # type: ignore
        
        await interaction.response.send_message(embed=initial_embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))