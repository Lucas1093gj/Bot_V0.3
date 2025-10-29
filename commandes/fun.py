import discord
from discord.ext import commands
from discord import app_commands

class PollCog(commands.Cog, name="Fun"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="poll", description="Crée un sondage simple avec des options.")
    @app_commands.describe(
        question="La question du sondage.",
        option1="Première option de réponse.",
        option2="Deuxième option de réponse.",
        option3="Troisième option de réponse (optionnel).",
        option4="Quatrième option de réponse (optionnel).",
        option5="Cinquième option de réponse (optionnel)."
    )
    async def poll(self, interaction: discord.Interaction,
                   question: str,
                   option1: str,
                   option2: str,
                   option3: str = None,
                   option4: str = None,
                   option5: str = None):
        
        # Collecter toutes les options non vides
        options = [option1, option2]
        if option3: options.append(option3)
        if option4: options.append(option4)
        if option5: options.append(option5)

        # Vérifier le nombre d'options
        if len(options) < 2:
            await interaction.response.send_message("❌ Un sondage doit avoir au moins deux options.", ephemeral=True)
            return
        if len(options) > 5:
            await interaction.response.send_message("❌ Un sondage ne peut pas avoir plus de cinq options.", ephemeral=True)
            return

        # Définir les emojis pour les options
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        
        description = ""
        for i, opt in enumerate(options):
            description += f"{emojis[i]} {opt}\n"

        embed = discord.Embed(
            title=f"📊 Sondage : {question}",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Sondage créé par {interaction.user.display_name}")

        # Envoyer le message du sondage
        poll_message = await interaction.channel.send(embed=embed)
        
        # Ajouter les réactions pour chaque option
        for i in range(len(options)):
            await poll_message.add_reaction(emojis[i])

        await interaction.response.send_message("✅ Sondage créé !", ephemeral=True)

    @poll.error
    async def poll_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous n'avez pas les permissions nécessaires pour créer un sondage.", ephemeral=True)
        else:
            print(f"Erreur dans PollCog: {error}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de la création du sondage.", ephemeral=True)

async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(PollCog(bot))
