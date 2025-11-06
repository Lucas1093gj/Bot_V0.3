import discord
from discord.ext import commands
from discord import app_commands
from db_manager import get_db_connection
import random
import time

class LevelingCog(commands.Cog, name="Leveling"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _calculate_xp_for_level(self, level: int) -> int:
        """Calcule la quantité d'XP nécessaire pour atteindre un certain niveau."""
        return 5 * (level ** 2) + 50 * level + 100

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # --- Vérifications initiales ---
        # 1. Ignorer les bots
        if message.author.bot:
            return
        # 2. Ignorer les messages privés (DMs)
        if not message.guild:
            return
        # 3. Ignorer les commandes pour ne pas donner d'XP pour ça
        if message.content.startswith(self.bot.command_prefix):
            return

        # --- Logique de gain d'XP ---
        # Utilisation d'un contexte asynchrone pour gérer la connexion
        async with get_db_connection() as conn:
            cursor = await conn.cursor() # noqa

            # Récupérer l'utilisateur ou le créer s'il n'existe pas
            await cursor.execute("SELECT xp, level, last_message_timestamp FROM user_levels WHERE guild_id = ? AND user_id = ?", (message.guild.id, message.author.id))
            user_data = await cursor.fetchone()

            if not user_data:
                # Le timestamp est en secondes (integer)
                await cursor.execute("INSERT INTO user_levels (guild_id, user_id, xp, level, last_message_timestamp) VALUES (?, ?, 0, 0, 0)", (message.guild.id, message.author.id))
                await conn.commit() # Commit de l'insertion
                user_data = {'xp': 0, 'level': 0, 'last_message_timestamp': 0}

            # --- Gestion du Cooldown (maintenant avec la DB) ---
            current_time = int(time.time())
            if current_time - user_data['last_message_timestamp'] < 60: # Cooldown de 60 secondes
                return

            # Ajouter de l'XP
            xp_to_add = random.randint(15, 25)
            new_xp = user_data['xp'] + xp_to_add

            # Vérifier si l'utilisateur monte de niveau
            xp_needed = self._calculate_xp_for_level(user_data['level'])
            new_level = user_data['level']
            if new_xp >= xp_needed:
                new_level += 1
                await message.channel.send(f"🎉 Bravo {message.author.mention}, vous avez atteint le **niveau {new_level}** !")

            # Mettre à jour la base de données
            await cursor.execute("UPDATE user_levels SET xp = ?, level = ?, last_message_timestamp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_level, current_time, message.guild.id, message.author.id))
            await conn.commit()

# --- Setup du cog ---
async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))