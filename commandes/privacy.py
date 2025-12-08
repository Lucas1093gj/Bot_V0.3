import discord
from discord.ext import commands
from discord import option

import json
import io
from datetime import datetime

# Ce cog regroupe les commandes liées à la gestion des données personnelles des utilisateurs.
class PrivacyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Assurez-vous que votre bot a une référence à votre gestionnaire de base de données
        # Exemple : self.db = bot.db_manager
        # Pour cet exemple, nous allons simuler les appels à la base de données.

    async def fetch_user_warnings(self, user_id: int, guild_id: int):
        """
        Fonction simulée pour récupérer les avertissements d'un utilisateur.
        À remplacer par votre propre appel à la base de données.
        Exemple : return await self.bot.db_manager.get_warnings_for_user(user_id, guild_id)
        """
        # Données d'exemple
        return [
            {"warn_id": 1, "moderator_id": 12345, "reason": "Spam", "date": "2024-05-01 10:00:00"},
            {"warn_id": 5, "moderator_id": 67890, "reason": "Comportement inapproprié", "date": "2024-06-10 15:30:00"}
        ]

    async def fetch_user_level(self, user_id: int, guild_id: int):
        """
        Fonction simulée pour récupérer le niveau et l'XP d'un utilisateur.
        À remplacer par votre propre appel à la base de données.
        Exemple : return await self.bot.db_manager.get_level_for_user(user_id, guild_id)
        """
        # Données d'exemple
        return {"level": 12, "xp": 12500, "total_xp": 25000}

    @commands.slash_command(
        name="mydata",
        description="Recevez une copie de toutes les données personnelles que le bot a stockées sur vous."
    )
    async def mydata(self, ctx: discord.ApplicationContext):
        """
        Envoie à l'utilisateur un fichier JSON contenant ses données personnelles
        collectées par le bot sur le serveur actuel.
        """
        await ctx.defer(ephemeral=True)

        user = ctx.author
        guild = ctx.guild

        # 1. Collecter les données de l'utilisateur depuis la base de données
        # Remplacez ces appels par les vôtres
        warnings_data = await self.fetch_user_warnings(user.id, guild.id)
        level_data = await self.fetch_user_level(user.id, guild.id)

        # 2. Construire le dictionnaire de données
        user_data = {
            "requested_at_utc": datetime.utcnow().isoformat(),
            "user_info": {
                "id": str(user.id),
                "username": user.name
            },
            "guild_info": {
                "id": str(guild.id),
                "name": guild.name
            },
            "data": {
                "warnings": warnings_data,
                "level_progress": level_data
                # Ajoutez ici d'autres données que vous pourriez stocker
            }
        }

        # 3. Créer le fichier JSON en mémoire
        json_str = json.dumps(user_data, indent=4, ensure_ascii=False)
        json_bytes = io.BytesIO(json_str.encode('utf-8'))
        file = discord.File(json_bytes, filename=f"my_data_{user.id}_{guild.id}.json")

        # 4. Envoyer le fichier en message privé
        try:
            dm_channel = await user.create_dm()
            await dm_channel.send(
                f"Bonjour {user.mention} !\n\n"
                f"Voici une copie de vos données personnelles pour le serveur **{guild.name}**, comme vous l'avez demandé.\n"
                "Ce fichier contient les informations que nous stockons vous concernant, comme votre progression de niveaux et votre historique d'avertissements.",
                file=file
            )
            await ctx.followup.send("✅ Fichier envoyé ! Je vous ai envoyé un message privé contenant vos données.", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send(
                "❌ Impossible d'envoyer le fichier. Il semble que vos messages privés soient désactivés pour ce serveur ou pour moi.\n"
                "Veuillez activer l'option `Autoriser les messages privés venant des membres du serveur` dans les paramètres de confidentialité de ce serveur.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Erreur lors de l'envoi des données à {user.id}: {e}")
            await ctx.followup.send("❌ Une erreur inattendue est survenue. Veuillez réessayer plus tard ou contacter le support.", ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(PrivacyCog(bot))
