import discord
from discord.ext import commands
from discord import app_commands
import datetime
from db_manager import get_db_connection
import asyncio

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Êtes-vous sûr de vouloir fermer ce ticket ? Cette action est irréversible.", view=ConfirmCloseView(), ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmer la Fermeture", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.channel.send("Fermeture du ticket dans 5 secondes...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

class TicketsCog(commands.Cog, name="Tickets"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ré-enregistrer la vue persistante au démarrage
        self.bot.add_view(CloseTicketView())

    @app_commands.command(name="ticket", description="Ouvre un ticket pour contacter le staff en privé.")
    @app_commands.describe(sujet="La raison pour laquelle vous ouvrez un ticket.")
    async def ticket(self, interaction: discord.Interaction, sujet: str):
        await interaction.response.defer(ephemeral=True)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_category_id FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,))
        record = cursor.fetchone() # noqa

        ticket_category = None
        if record and record['ticket_category_id']:
            ticket_category = interaction.guild.get_channel(record['ticket_category_id'])

        # Si la catégorie n'est pas trouvée dans la DB ou a été supprimée de Discord
        if not ticket_category:
            try:
                # Permissions pour la nouvelle catégorie : privée par défaut
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.guild.me: discord.PermissionOverwrite(view_channel=True)
                }
                ticket_category = await interaction.guild.create_category(
                    "Tickets",
                    overwrites=overwrites,
                    reason="Création automatique de la catégorie pour les tickets"
                )
                # Sauvegarder l'ID de la nouvelle catégorie dans la base de données
                cursor.execute("INSERT OR REPLACE INTO guild_settings (guild_id, ticket_category_id) VALUES (?, ?)", (interaction.guild.id, ticket_category.id))
                conn.commit()
            except discord.Forbidden:
                await interaction.followup.send("❌ Je n'ai pas la permission de créer une catégorie. Veuillez me donner la permission 'Gérer les salons' ou créer manuellement une catégorie 'Tickets' et la configurer avec `/discordmaker setup`.", ephemeral=True)
                conn.close()
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Une erreur est survenue lors de la création de la catégorie de tickets : {e}", ephemeral=True)
                conn.close()
                return

        # Récupérer les rôles de staff
        mod_role = discord.utils.get(interaction.guild.roles, name="Modérateur")
        admin_role = discord.utils.get(interaction.guild.roles, name="Admin")

        if not mod_role and not admin_role:
            await interaction.followup.send("❌ Aucun rôle de staff ('Modérateur', 'Admin') n'a été trouvé pour gérer le ticket.", ephemeral=True)
            return

        # Définir les permissions pour le nouveau salon
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True, read_message_history=True)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True, read_message_history=True)

        # Nettoyer le nom du salon
        channel_name = f"ticket-{interaction.user.name.lower()}"
        
        try:
            ticket_channel = await ticket_category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Ticket ouvert par {interaction.user} pour : {sujet}"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Je n'ai pas les permissions pour créer un salon dans la catégorie des tickets.", ephemeral=True)
            return

        # Envoyer le message initial dans le ticket
        staff_mention = f"{mod_role.mention if mod_role else ''} {admin_role.mention if admin_role else ''}"
        
        embed = discord.Embed(
            title=f"Ticket Ouvert : {sujet}",
            description=f"Bienvenue, {interaction.user.mention} !\n\nUn membre du staff va vous répondre dès que possible. "
                        "Veuillez décrire votre problème en détail.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Ticket de {interaction.user.name} | ID: {interaction.user.id}")

        await ticket_channel.send(content=staff_mention, embed=embed, view=CloseTicketView())
        await interaction.followup.send(f"✅ Votre ticket a été créé : {ticket_channel.mention}", ephemeral=True)
        conn.close()

    @ticket.error
    async def ticket_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        print(f"Erreur dans TicketsCog: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors de la création du ticket.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Une erreur est survenue lors de la création du ticket.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))