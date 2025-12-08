import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class UtilsCog(commands.Cog, name="Utilitaires"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Vérifie la latence du bot.")
    async def ping(self, interaction: discord.Interaction):
        """Affiche la latence du bot avec l'API Discord."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! 🏓 Latence : {latency}ms", ephemeral=True)

    @app_commands.command(name="serverinfo", description="Affiche des informations détaillées sur le serveur.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild

        # Comptages
        member_count = guild.member_count
        human_count = len([m for m in guild.members if not m.bot])
        bot_count = member_count - human_count
        
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        role_count = len(guild.roles)

        # Statut de boost
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count

        # Création de l'embed
        embed = discord.Embed(
            title=f"Informations sur le serveur {guild.name}",
            color=discord.Color.blurple(),
            timestamp=guild.created_at
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text=f"Serveur créé le {discord.utils.format_dt(guild.created_at, style='F')}")

        embed.add_field(name="👑 Propriétaire", value=guild.owner.mention, inline=True)
        embed.add_field(name="👥 Membres", value=f"**Total**: {member_count}\n**Humains**: {human_count}\n**Bots**: {bot_count}", inline=True)
        embed.add_field(name="💬 Salons", value=f"**Catégories**: {categories}\n**Textuels**: {text_channels}\n**Vocaux**: {voice_channels}", inline=True)
        
        embed.add_field(name="✨ Boosts", value=f"**Niveau**: {boost_level}\n**Nombre**: {boost_count}", inline=True)
        embed.add_field(name="🎭 Rôles", value=str(role_count), inline=True)
        embed.add_field(name="🆔 ID du Serveur", value=f"`{guild.id}`", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Affiche des informations sur un membre.")
    @app_commands.describe(membre="Le membre sur lequel vous voulez des informations (par défaut : vous-même).")
    async def userinfo(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        target = membre or interaction.user

        embed = discord.Embed(title=f"Informations sur {target.display_name}", color=target.color or discord.Color.blurple())
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        embed.add_field(name="Nom complet", value=f"`{target}`", inline=True)
        embed.add_field(name="ID Utilisateur", value=f"`{target.id}`", inline=True)
        
        if isinstance(target, discord.Member):
            status_emoji = {discord.Status.online: "🟢 En ligne", discord.Status.idle: "🌙 Inactif", discord.Status.dnd: "⛔ Ne pas déranger", discord.Status.offline: "⚫ Hors ligne"}
            embed.add_field(name="Statut", value=status_emoji.get(target.status, "❓ Inconnu"), inline=True)

        embed.add_field(name="Compte créé le", value=discord.utils.format_dt(target.created_at, style='F'), inline=False)
        if isinstance(target, discord.Member) and target.joined_at:
            embed.add_field(name="A rejoint le serveur le", value=discord.utils.format_dt(target.joined_at, style='F'), inline=False)

        if isinstance(target, discord.Member) and len(target.roles) > 1:
            roles = sorted(target.roles, key=lambda r: r.position, reverse=True)
            role_mentions = ", ".join([r.mention for r in roles if r.name != "@everyone"])
            embed.add_field(name=f"Rôles ({len(roles) - 1})", value=role_mentions if len(role_mentions) < 1024 else f"{len(roles) - 1} rôles", inline=False)

        embed.set_footer(text=f"Demandé par {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(UtilsCog(bot))