import discord
from discord import app_commands
from discord.ext import commands
import os
from collections import defaultdict

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author: discord.User):
        super().__init__(timeout=180)
        self.bot = bot
        self.author = author
        self.add_item(self.build_select_menu())

        # Ajout du bouton pour le dashboard
        dashboard_url = os.getenv("WEB_BASE_URL", "http://127.0.0.1:5001")
        self.add_item(discord.ui.Button(label="Visiter le Dashboard", style=discord.ButtonStyle.link, url=dashboard_url, emoji="🌐"))

    def get_cogs_and_commands(self):
        """Regroupe les commandes par cog."""
        grouped_commands = defaultdict(list)
        # On ignore le cog 'General' lui-même et les commandes sans description
        hidden_cogs = ["GeneralCog", "LoggerCog"]
        for command in self.bot.tree.get_commands():
            if not command.description:
                continue
            cog_name = command.cog.qualified_name if command.cog and command.cog.qualified_name not in hidden_cogs else "Autres"
            grouped_commands[cog_name].append(command)
        return grouped_commands

    def build_select_menu(self):
        """Construit le menu déroulant avec les catégories de commandes."""
        options = [
            discord.SelectOption(label="Accueil", description="Retourner à la vue d'ensemble", emoji="🏠")
        ]
        for cog_name in sorted(self.get_cogs_and_commands().keys()):
            options.append(discord.SelectOption(label=cog_name, description=f"Commandes de la catégorie {cog_name}"))
        
        select = discord.ui.Select(placeholder="Choisissez une catégorie...", options=options)
        select.callback = self.select_callback
        return select

    async def select_callback(self, interaction: discord.Interaction):
        """Gère la sélection d'une catégorie dans le menu."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce menu.", ephemeral=True)
            return

        selected_category = interaction.data['values'][0]
        
        if selected_category == "Accueil":
            embed = self.create_initial_embed()
        else:
            embed = self.create_category_embed(selected_category)

        await interaction.response.edit_message(embed=embed)

    def create_initial_embed(self):
        """Crée l'embed initial de la commande /help."""
        embed = discord.Embed(
            title=f"👋 Aide pour {self.bot.user.name}",
            description="Bienvenue dans le panneau d'aide interactif.\n"
                        "Utilisez le menu déroulant ci-dessous pour explorer les commandes par catégorie.",
            color=discord.Color.blurple()
        )
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="Sélectionnez une catégorie pour voir les commandes.")
        return embed

    def create_category_embed(self, category_name: str):
        """Crée un embed pour une catégorie de commandes spécifique."""
        embed = discord.Embed(title=f"Catégorie : {category_name}", color=discord.Color.dark_blue())
        
        commands_in_cog = self.get_cogs_and_commands().get(category_name, [])
        if not commands_in_cog:
            embed.description = "Aucune commande trouvée dans cette catégorie."
        else:
            description = ""
            for command in sorted(commands_in_cog, key=lambda c: c.name):
                description += f"`/{command.name}`: {command.description}\n"
            embed.description = description
        
        return embed

class GeneralCog(commands.Cog, name="General"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Affiche le panneau d'aide interactif du bot.")
    async def help(self, interaction: discord.Interaction):
        view = HelpView(self.bot, interaction.user)
        embed = view.create_initial_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="dashboard", description="Envoie un lien privé pour accéder au tableau de bord web.")
    async def dashboard(self, interaction: discord.Interaction):
        dashboard_url = os.getenv("WEB_BASE_URL", "http://127.0.0.1:5001")
        embed = discord.Embed(
            title="🌐 Accès au Tableau de Bord",
            description=f"Cliquez sur le bouton ci-dessous pour ouvrir le tableau de bord et gérer vos serveurs.",
            color=discord.Color.green()
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ouvrir le Dashboard", style=discord.ButtonStyle.link, url=dashboard_url))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))