import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Ajoute le répertoire racine du projet au path pour permettre les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from commandes.moderation import ModerationCog

# Le backend est maintenant configuré dans pytest.ini
pytestmark = pytest.mark.anyio

@pytest.fixture
def mock_bot():
    """Crée un faux objet bot avec une fausse connexion à la base de données."""
    bot = MagicMock()
    # Simule la connexion à la base de données pour ne pas dépendre de la vraie DB
    bot.db_conn = MagicMock()
    bot.db_conn.cursor.return_value.execute.return_value = None
    bot.db_conn.commit.return_value = None
    return bot

@pytest.fixture
def moderation_cog(mock_bot):
    """Crée une instance du Cog de modération avec le faux bot."""
    return ModerationCog(bot=mock_bot)

@pytest.fixture
def mock_interaction():
    """Crée une fausse interaction Discord."""
    interaction = MagicMock()
    # Les réponses sont des coroutines, on utilise donc AsyncMock
    interaction.response.send_message = AsyncMock()
    
    # Simule l'utilisateur qui lance la commande et le serveur
    interaction.user = MagicMock()
    interaction.user.bot = False # Important: Spécifier que l'utilisateur n'est pas un bot
    interaction.user.id = 12345
    interaction.guild = MagicMock()
    interaction.guild.id = 54321
    return interaction

async def test_warn_a_bot(moderation_cog, mock_interaction):
    """
    Teste que la commande 'warn' refuse d'avertir un bot.
    """
    # Crée un faux membre qui est un bot
    target_member = MagicMock()
    target_member.bot = True
    target_member.id = 99999

    # On appelle le .callback de la commande, car le décorateur transforme la méthode.
    # Le premier argument du callback est toujours l'instance du cog (self).
    await moderation_cog.warn.callback(moderation_cog, mock_interaction, target_member, "Test reason")

    # Vérifie que la bonne réponse a été envoyée
    mock_interaction.response.send_message.assert_called_once_with(
        "❌ Vous ne pouvez pas avertir un bot.", ephemeral=True
    )

async def test_warn_self(moderation_cog, mock_interaction):
    """
    Teste que la commande 'warn' refuse qu'un utilisateur s'avertisse lui-même.
    """
    # Le membre cible est le même que l'utilisateur qui lance la commande
    target_member = mock_interaction.user

    # On appelle le .callback de la commande.
    await moderation_cog.warn.callback(moderation_cog, mock_interaction, target_member, "Test reason")

    mock_interaction.response.send_message.assert_called_once_with(
        "❌ Vous ne pouvez pas vous avertir vous-même.", ephemeral=True
    )