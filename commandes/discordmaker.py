import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import os
import time
import aiosqlite
# --- Configuration principale du module ---
from db_manager import get_db_connection
# --- Constantes de configuration ---
CONFIG_DIR = "guild_configs"
BACKUP_DIR = "guild_backups"

# Cette structure de données définit les propriétés de chaque rôle que le bot peut créer.
# Données des rôles (permissions et couleurs). L'ordre définit la hiérarchie (du plus haut au plus bas).
ROLE_DATA = {
    "Owner": {"permissions": discord.Permissions(administrator=True), "color": discord.Color.from_rgb(255, 85, 85)},
    "Admin": {"permissions": discord.Permissions(administrator=True), "color": discord.Color.red()},
    "Modérateur": {"permissions": discord.Permissions(manage_channels=True, manage_roles=True, kick_members=True, ban_members=True, manage_messages=True, mute_members=True, deafen_members=True, move_members=True, manage_nicknames=True), "color": discord.Color.blue()},
    "Animateur": {"permissions": discord.Permissions(manage_events=True, create_public_threads=True, manage_threads=True), "color": discord.Color.green()},
    "Bot": {"permissions": discord.Permissions(read_messages=True, send_messages=True, manage_messages=True, embed_links=True, attach_files=True, manage_roles=True, manage_channels=True), "color": discord.Color.light_grey()},
    "VIP": {"permissions": discord.Permissions(priority_speaker=True, stream=True), "color": discord.Color.gold()},
    "Vérifié": {"permissions": discord.Permissions(read_messages=True, send_messages=True, embed_links=True, attach_files=True, read_message_history=True, connect=True, speak=True, stream=True, use_voice_activation=True), "color": discord.Color.default()},
    # Rôles de notification (sans permissions spéciales, juste pour le ping)
    "Notif Annonces": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(255, 204, 77)},
    "Notif Giveaways": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(114, 137, 218)},
    # Rôles de jeux (sans permissions spéciales)
    "Valorant": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(253, 69, 86)},
    "League of Legends": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(0, 143, 143)}, # noqa: E501
    "Minecraft": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(85, 170, 85)},
    "Fortnite": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(128, 0, 128)},
    "Apex Legends": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(218, 41, 42)},
    "GTA RP": {"permissions": discord.Permissions.none(), "color": discord.Color.from_rgb(88, 101, 242)},
    "Muted": {"permissions": discord.Permissions.none(), "color": discord.Color.dark_grey()},
}

# Définit le plan du serveur : quelles catégories et quels salons créer.
# Structure des salons
CHANNEL_STRUCTURE = {
    "╭───┤ ACCUEIL ├───╮": {
        "text": ["#✅・vérification", "#📚・règles", "#📢・annonces", "#✨・rôles-notifs", "#🎉・giveaways"],
        "voice": []
    },
    "╭───┤ COMMUNAUTÉ ├───╮": {
        "text": ["#💬・général", "#🖼・médias", "#🤖・commandes-bots", "#💡・suggestions", "#📊・sondages"],
        "voice": []
    },
    "╭───┤ ESPACE GAMING ├───╮": {
        "text": ["#🎮・gaming-discussion", "#🤝・recherche-de-joueurs", "#🎬・clips-screenshots"],
        "voice": []
    },
    "├─ Jeux Populaires": {
        "text": ["#valorant-discussion", "#lol-discussion", "#minecraft-discussion", "#fortnite-discussion", "#apex-discussion", "#gta-rp-discussion"],
        "voice": ["🎤 Gaming 1", "🎤 Gaming 2"]
    },
    "╭───┤ DÉTENTE & CRÉATION ├───╮": {
        "text": ["#🎵・musique", "#🎨・art-et-créations", "#🍿・cinéma-séries", "#💻・développement"],
        "voice": []
    },
    "╰───┤ SALONS VOCAUX ├───╯": {
        "text": [],
        "voice": ["🔊 Général 1", "🔊 Général 2", "🎶 Musique", "💤 AFK"]
    },
    "╭───┤ STAFF ├───╮": {
        "text": ["#🔒・staff-discussion", "#🔒・staff-commandes"],
        "voice": ["🎤 Staff Vocal"],
        "staff_only": True # Marqueur pour permissions spéciales
    },
    "╭───┤ LOGS ├───╮": {
        "text": ["#📜・logs-messages", "#📜・logs-membres", "#📜・logs-modération"],
        "voice": [],
        "staff_only": True # Marqueur pour permissions spéciales
    },
}

# Liste des rôles que les membres peuvent s'attribuer eux-mêmes via la commande /post-roles.
# Rôles que les membres peuvent s'auto-attribuer
SELF_ASSIGNABLE_ROLES = [
    "Notif Annonces", 
    "Notif Giveaways",
    "Valorant",
    "League of Legends",
    "Minecraft",
    "Fortnite",
    "Apex Legends",
    "GTA RP"
]

# --- Fonctions utilitaires pour la configuration ---
def get_config_path(guild_id: int) -> str:
    """Génère le chemin complet vers le fichier de configuration JSON d'un serveur."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    return os.path.join(CONFIG_DIR, f"{guild_id}.json")

def load_config(guild_id: int) -> dict:
    """Charge la configuration d'un serveur. Si aucun fichier n'existe, retourne une configuration par défaut."""
    path = get_config_path(guild_id)
    if not os.path.exists(path):
        # Crée une configuration vide si le fichier n'existe pas encore.
        return {"roles": [], "channel_categories": [], "cleanup_policy": "keep", "verification_system": "disabled"}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(guild_id: int, config: dict):
    """Enregistre la configuration d'un serveur dans un fichier JSON."""
    with open(get_config_path(guild_id), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

async def create_server_backup(guild: discord.Guild) -> str | None:
    """Crée un fichier de sauvegarde JSON contenant la structure complète des rôles et salons du serveur."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    backup_data = {
        "guild_name": guild.name,
        "guild_id": guild.id,
        "backup_timestamp": int(time.time()),
        "roles": [],
        "channels": []
    }

    # Sauvegarde de tous les rôles, en respectant leur ordre hiérarchique.
    for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
        if role.is_default(): continue
        backup_data["roles"].append({
            "name": role.name,
            "permissions": role.permissions.value,
            "color": role.color.to_rgb(),
            "hoist": role.hoist,
            "position": role.position,
            "mentionable": role.mentionable
        })

    # Sauvegarde des catégories et des salons, en respectant leur position.
    for channel in sorted(guild.channels, key=lambda c: c.position):
        # On ignore les threads pour ne sauvegarder que les salons principaux.
        if isinstance(channel, discord.Thread): continue

        overwrites = {}
        # On convertit les cibles des permissions (rôles/membres) par leur nom plutôt que leur ID.
        # L'ID ne serait valide que sur le serveur d'origine.
        for target, perms in channel.overwrites.items():
            target_name = target.name if isinstance(target, discord.Role) else str(target)
            overwrites[target_name] = {"type": "role" if isinstance(target, discord.Role) else "member", "allow": perms.pair()[0].value, "deny": perms.pair()[1].value}

        backup_data["channels"].append({
            "id": channel.id, # Ajout de l'ID pour la restauration des catégories
            "name": channel.name,
            "type": str(channel.type),
            "position": channel.position,
            "category_id": channel.category.id if channel.category else None,
            "overwrites": overwrites
        })

    backup_filename = os.path.join(BACKUP_DIR, f"{guild.id}-{backup_data['backup_timestamp']}.json")
    with open(backup_filename, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=4, ensure_ascii=False)
    return backup_filename

# --- Vues (UI) pour la vérification ---
class VerificationView(discord.ui.View):
    """Définit le bouton de vérification persistant. `timeout=None` le rend permanent."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cliquez ici pour vérifier", style=discord.ButtonStyle.success, emoji="✅", custom_id="verification_button_persistent")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cette fonction est appelée lorsqu'un utilisateur clique sur le bouton de vérification."""
        # On récupère le rôle dynamiquement au moment du clic
        verified_role = discord.utils.get(interaction.guild.roles, name="Vérifié")

        if not verified_role:
            return await interaction.response.send_message("❌ Le rôle 'Vérifié' n'a pas été trouvé sur ce serveur. Veuillez contacter un administrateur.", ephemeral=True)

        # On vérifie si l'utilisateur a déjà le rôle
        if verified_role in interaction.user.roles:
            await interaction.response.send_message("Vous êtes déjà vérifié !", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(verified_role, reason="Vérification automatique")
                await interaction.response.send_message("✅ Vous avez été vérifié avec succès ! Vous avez maintenant accès au reste du serveur.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Je n'ai pas les permissions pour vous donner ce rôle. Veuillez contacter un administrateur.", ephemeral=True)
            except Exception as e:
                print(f"Erreur lors de l'ajout du rôle de vérification : {e}")
                await interaction.response.send_message("❌ Une erreur est survenue lors de la vérification.", ephemeral=True)

# --- Vues (UI) pour la sélection de rôles ---
class RoleMenuView(discord.ui.View):
    """Définit la vue (le conteneur) pour le menu déroulant de sélection de rôles."""
    def __init__(self, assignable_roles: list[str], bot_instance):
        super().__init__(timeout=None)
        # On ajoute le menu déroulant (Select) à cette vue.
        self.add_item(RoleMenuSelect(assignable_roles, bot_instance))

class RoleMenuSelect(discord.ui.Select):
    """Définit le menu déroulant lui-même, avec ses options."""
    def __init__(self, assignable_roles: list[str], bot_instance): # noqa
        self.bot = bot_instance
        options = []
        for role_name in assignable_roles:
            description = f"Pour obtenir le rôle {role_name}"
            if role_name.startswith("Notif "):
                try:
                    description = f"Recevoir les notifications pour {role_name.split(' ', 1)[1]}"
                except IndexError:
                    pass # Garde la description par défaut si le split échoue
            
            options.append(discord.SelectOption(label=role_name, description=description))

        super().__init__(
            placeholder="Choisissez vos rôles (notifications, jeux, etc.)...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id="role_menu_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Cette fonction est appelée quand l'utilisateur valide sa sélection dans le menu."""
        member = interaction.user

        # Recharger la configuration pour obtenir les rôles assignables actuels
        # rend la vue plus robuste si la configuration change pendant que le bot est en ligne.
        config = load_config(interaction.guild.id)
        server_assignable_roles = [role for role in config.get("roles", []) if role in SELF_ASSIGNABLE_ROLES]

        # On s'assure que les options du menu correspondent toujours à la configuration actuelle.
        self.options = [opt for opt in self.options if opt.label in server_assignable_roles]
        self.max_values = len(self.options)
        
        # On ne traite que les rôles qui étaient proposés dans le menu
        possible_roles = {option.label for option in self.options}

        # Récupérer les objets Role correspondants aux noms
        assignable_roles_obj = {role.name: role for role in interaction.guild.roles if role.name in possible_roles}
        
        # On calcule les rôles à ajouter et à retirer en comparant la sélection de l'utilisateur à ses rôles actuels.
        roles_to_add = [assignable_roles_obj[role_name] for role_name in self.values if role_name in assignable_roles_obj and assignable_roles_obj[role_name] not in member.roles]
        roles_to_remove = [role for name, role in assignable_roles_obj.items() if name not in self.values and role in member.roles]

        try:
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Auto-attribution de rôle")
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Auto-attribution de rôle")
            await interaction.response.send_message("✅ Vos rôles ont été mis à jour !", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas les permissions pour modifier vos rôles.", ephemeral=True)

# --- Vues (UI) pour la configuration ---
class RoleSelect(discord.ui.Select):
    """Un menu déroulant pour que l'admin choisisse les rôles à inclure dans la configuration."""
    def __init__(self, current_roles: list):
        options = [
            discord.SelectOption(label=role, description=f"Activer/Désactiver le rôle {role}", default=(role in current_roles))
            for role in sorted(ROLE_DATA.keys())
        ]
        super().__init__(placeholder="Choisissez les rôles à créer...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde la sélection de rôles dans le fichier de configuration du serveur."""
        config = load_config(interaction.guild_id)
        config["roles"] = self.values
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Rôles configurés : `{', '.join(self.values) or 'Aucun'}`", ephemeral=True)

class ChannelSelect(discord.ui.Select):
    """Un menu déroulant pour que l'admin choisisse les catégories de salons à créer."""
    def __init__(self, current_categories: list):
        options = [
            discord.SelectOption(label=cat, description=f"Inclure la catégorie '{cat}'", default=(cat in current_categories))
            for cat in sorted(CHANNEL_STRUCTURE.keys())
        ]
        super().__init__(placeholder="Choisissez les catégories de salons à créer...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde la sélection de catégories dans le fichier de configuration."""
        config = load_config(interaction.guild_id)
        config["channel_categories"] = self.values
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Catégories configurées : `{', '.join(self.values) or 'Aucune'}`", ephemeral=True)

class CleanupSelect(discord.ui.Select):
    """Permet à l'admin de choisir ce qu'il faut faire avant de construire le serveur (ne rien faire, nettoyer, etc.)."""
    def __init__(self, current_policy: str):
        options = [
            discord.SelectOption(label="Conserver", value="keep", description="Ne supprime rien avant la création (recommandé).", default=(current_policy == "keep")),
            discord.SelectOption(label="Nettoyage Intelligent", value="smart_delete", description="Supprime uniquement les éléments connus du bot.", default=(current_policy == "smart_delete")),
            discord.SelectOption(label="Suppression Totale (Dangereux)", value="full_delete", description="Supprime TOUS les rôles et salons (Owner uniquement).", default=(current_policy == "full_delete")),
        ]
        super().__init__(placeholder="Action avant la création...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde la politique de nettoyage choisie."""
        config = load_config(interaction.guild_id)
        config["cleanup_policy"] = self.values[0]
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Politique de nettoyage définie sur : `{self.values[0]}`", ephemeral=True)

class VerificationSelect(discord.ui.Select):
    """Permet à l'admin d'activer ou de désactiver le système de vérification par bouton."""
    def __init__(self, current_status: str):
        options = [
            discord.SelectOption(label="Activé", value="enabled", description="Met en place un salon de vérification.", default=(current_status == "enabled")),
            discord.SelectOption(label="Désactivé", value="disabled", description="Aucun système de vérification.", default=(current_status == "disabled")),
        ]
        super().__init__(placeholder="Système de vérification...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde le choix concernant le système de vérification."""
        config = load_config(interaction.guild_id)
        config["verification_system"] = self.values[0]
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Système de vérification : `{self.values[0]}`", ephemeral=True)

class ModLogChannelSelect(discord.ui.ChannelSelect):
    """Un menu déroulant spécialisé pour ne montrer que les salons textuels, pour les logs."""
    def __init__(self, current_channel_id: int | None):
        super().__init__(
            placeholder="Choisissez un salon pour les logs de modération...",
            min_values=0, # Permet de désélectionner
            max_values=1,
            channel_types=[discord.ChannelType.text],
            custom_id="mod_log_channel_select"
        )

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0].id) if self.values else None
        async with get_db_connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO guild_settings (guild_id, mod_log_channel_id) VALUES (?, ?)", (interaction.guild.id, channel_id))
            await conn.commit()

        message = f"✅ Salon des logs de modération défini sur : {self.values[0].mention}" if channel_id else "✅ Salon des logs de modération désactivé."
        await interaction.response.send_message(message, ephemeral=True)

class TicketCategorySelect(discord.ui.ChannelSelect):
    """Un menu déroulant spécialisé pour ne montrer que les catégories, pour les tickets."""
    def __init__(self):
        super().__init__(
            placeholder="Choisissez une catégorie pour les tickets...",
            min_values=0, # Permet de désélectionner
            max_values=1,
            channel_types=[discord.ChannelType.category],
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        category_id = int(self.values[0].id) if self.values else None
        async with get_db_connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO guild_settings (guild_id, ticket_category_id) VALUES (?, ?)", (interaction.guild.id, category_id))
            await conn.commit()

        message = f"✅ Catégorie des tickets définie sur : **{self.values[0].name}**" if category_id else "✅ Système de tickets désactivé."
        await interaction.response.send_message(message, ephemeral=True)

class ConfigView(discord.ui.View):
    """La vue principale qui gère la pagination entre les différentes pages de configuration."""
    def __init__(self, guild_id: int):
        super().__init__(timeout=300) # La vue expire après 5 minutes d'inactivité.
        self.guild_id = guild_id
        self.current_page = 1
        self.update_view()

    def update_view(self):
        """Efface et reconstruit les éléments de la vue en fonction de la page affichée."""
        self.clear_items()
        config = load_config(self.guild_id)

        if self.current_page == 1:
            # Page 1: Configuration principale
            self.add_item(RoleSelect(config.get("roles", [])))
            self.add_item(ChannelSelect(config.get("channel_categories", [])))
            self.add_item(CleanupSelect(config.get("cleanup_policy", "keep")))
            self.add_item(VerificationSelect(config.get("verification_system", "disabled")))
            self.add_item(PageButton(label="Suivant ➡️", next_page=2, style=discord.ButtonStyle.secondary, row=4))
        elif self.current_page == 2:
            # Page 2: Configuration des modules
            self.add_item(ModLogChannelSelect(None))
            self.add_item(TicketCategorySelect())
            self.add_item(PageButton(label="⬅️ Précédent", next_page=1, style=discord.ButtonStyle.secondary, row=4))

class PageButton(discord.ui.Button):
    def __init__(self, label: str, next_page: int, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.next_page = next_page

    async def callback(self, interaction: discord.Interaction):
        """Change la page de la vue de configuration et met à jour le message."""
        await interaction.response.defer() # Accuser réception de l'interaction immédiatement

        view: ConfigView = self.view
        view.current_page = self.next_page
        view.update_view()

        # On crée le nouvel embed pour la page demandée.
        config = load_config(interaction.guild.id)
        embed = discord.Embed(
            title=f"🛠️ Configuration du Serveur (Page {view.current_page}/2)",
            color=discord.Color.blurple()
        )

        if view.current_page == 1:
            embed.description = "Configurez les options principales de la structure du serveur."
            embed.add_field(name="Rôles", value=f"{len(config.get('roles', []))} configurés", inline=True)
            embed.add_field(name="Catégories", value=f"{len(config.get('channel_categories', []))} configurées", inline=True)
        elif view.current_page == 2:
            record = None
            async with get_db_connection() as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT mod_log_channel_id, ticket_category_id FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                    record = await cursor.fetchone()

            log_channel_status = "✅" if record and record['mod_log_channel_id'] else "❌" # noqa
            ticket_category_status = "✅" if record and record['ticket_category_id'] else "❌"

            embed.description = "Configurez les options des modules additionnels."
            embed.add_field(name="Salon des Logs", value=f"Configuré : {log_channel_status}", inline=True)
            embed.add_field(name="Catégorie des Tickets", value=f"Configurée : {ticket_category_status}", inline=True)

        await interaction.edit_original_response(embed=embed, view=view)

# --- Classe principale du Cog ---
class DiscordMakerCog(commands.Cog, name="DiscordMaker"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    maker_group = app_commands.Group(name="discordmaker", description="Commandes pour construire et gérer votre serveur.")

    @maker_group.command(name="setup", description="Ouvre le panneau pour configurer la structure du serveur.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        """Affiche le panneau de configuration interactif pour le serveur."""
        embed = discord.Embed(
            title="🛠️ Configuration du Serveur (Page 1/2)",
            description="Bienvenue dans le panneau de configuration. Configurez les options principales de la structure du serveur.\n"
                        "Vos choix sont sauvegardés automatiquement. Une fois prêt, lancez `/discordmaker start`.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=ConfigView(interaction.guild_id), ephemeral=True)

    @maker_group.command(name="start", description="Construit le serveur avec la configuration actuelle.")
    @app_commands.checks.has_permissions(administrator=True)
    async def start(self, interaction: discord.Interaction):
        """Lance la construction (ou reconstruction) du serveur en se basant sur la configuration sauvegardée."""
        await interaction.response.defer(ephemeral=True)

        # On utilise le verrou pour s'assurer que cette opération critique ne soit pas interrompue ou lancée en double.
        async with self.bot.critical_operation_lock:
            config = load_config(interaction.guild_id)
            guild = interaction.guild

            if not config.get("roles") and not config.get("channel_categories"):
                await interaction.followup.send("❌ Aucune configuration n'a été trouvée. Utilisez d'abord `/discordmaker setup`.", ephemeral=True)
                return

            await interaction.followup.send("🚀 Lancement de la construction du serveur... Cela peut prendre un moment.", ephemeral=True)

            # Étape 1 : Nettoyage du serveur (si l'option a été choisie dans le setup).
            cleanup_policy = config.get("cleanup_policy", "keep")
            if cleanup_policy == "smart_delete":
                await self._cleanup_guild(guild)
            elif cleanup_policy == "full_delete":
                # Vérification de sécurité pour la suppression totale
                if interaction.user.id != guild.owner_id:
                    await interaction.followup.send("❌ La politique de 'Suppression Totale' est sélectionnée. Seul le propriétaire du serveur peut lancer cette commande.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="⚠️ CONFIRMATION DE SUPPRESSION TOTALE ⚠️",
                    description=f"**Vous avez demandé une suppression totale du serveur `{guild.name}` via la commande `start`.**\n\n"
                                "Pour confirmer, veuillez taper `OUI` en majuscules dans ce salon dans les 30 secondes.",
                    color=discord.Color.dark_red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

                def check(m: discord.Message):
                    return m.author == interaction.user and m.channel == interaction.channel and m.content == "OUI"

                try:
                    msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                    await msg.delete()
                except asyncio.TimeoutError:
                    await interaction.followup.send("❌ Délai de confirmation dépassé. Opération annulée.", ephemeral=True)
                    return
                except discord.HTTPException:
                    pass # Pas grave si on ne peut pas supprimer le message de confirmation

                # Création et envoi de la sauvegarde avant la suppression
                await interaction.followup.send("🔄 Création d'une sauvegarde du serveur avant suppression...", ephemeral=True)
                backup_file_path = await create_server_backup(guild)
                if backup_file_path:
                    try:
                        embed_backup = discord.Embed(title=f"📄 Sauvegarde du serveur {guild.name}", description="Voici une sauvegarde de la structure de votre serveur (rôles et salons) avant sa réinitialisation complète. **Conservez ce fichier précieusement.**", color=discord.Color.orange())
                        embed_backup.add_field(name="À quoi sert ce fichier ?", value="Ce fichier `.json` contient les informations sur vos rôles, salons et permissions. Il peut être utilisé avec la commande `/discordmaker restore` pour recréer cette structure.", inline=False)
                        embed_backup.set_footer(text="⚠️ ATTENTION : Cette sauvegarde n'inclut PAS les messages, les membres, ou les fichiers du serveur.")
                        await interaction.user.send(embed=embed_backup, file=discord.File(backup_file_path))
                    except discord.Forbidden:
                        await interaction.followup.send("⚠️ Impossible de vous envoyer la sauvegarde en DM. Vos messages privés sont probablement fermés.", ephemeral=True)
                await self._full_cleanup_guild(guild) # Lancement de la suppression.

            # --- Création des rôles ---
            created_roles = {}
            # Trier les rôles pour créer les plus hauts en premier
            role_creation_order = sorted(
                config.get("roles", []),
                key=lambda r: list(ROLE_DATA.keys()).index(r) if r in ROLE_DATA else -1,
            )

            if config.get("roles"):
                for role_name in role_creation_order:
                    existing_role = discord.utils.get(guild.roles, name=role_name)
                    if existing_role:
                        created_roles[role_name] = existing_role
                        continue

                    role_data = ROLE_DATA.get(role_name, {})
                    permissions = role_data.get("permissions", discord.Permissions.none())
                    color = role_data.get("color", discord.Color.default())
                    # Les rôles VIP et Muted ne sont pas affichés séparément
                    hoist = role_name in ["Owner", "Admin", "Modérateur", "Animateur"]
                    try:
                        role = await guild.create_role(name=role_name, permissions=permissions, color=color, reason="DiscordMaker Setup", hoist=hoist) # noqa
                        # On enregistre l'ID du rôle créé dans la base de données pour pouvoir le retrouver plus tard (pour le /reset).
                        async with get_db_connection() as conn:
                            await conn.execute("INSERT OR IGNORE INTO created_elements (guild_id, element_id, element_type) VALUES (?, ?, ?)", (guild.id, role.id, 'role'))
                            await conn.commit()
                        created_roles[role_name] = role
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer le rôle `{role_name}`.")
                        continue

            # --- Création des salons ---
            if config.get("channel_categories"):
                # Récupération des rôles clés pour les permissions
                verified_role = created_roles.get("Vérifié") or discord.utils.get(guild.roles, name="Vérifié")
                admin_role = created_roles.get("Admin") or discord.utils.get(guild.roles, name="Admin")
                mod_role = created_roles.get("Modérateur") or discord.utils.get(guild.roles, name="Modérateur")

                # Trier les catégories pour les créer dans le bon ordre
                category_creation_order = sorted(
                    config["channel_categories"],
                    key=lambda c: list(CHANNEL_STRUCTURE.keys()).index(c) if c in CHANNEL_STRUCTURE else -1
                )

                for category_name in category_creation_order:
                    structure = CHANNEL_STRUCTURE.get(category_name)
                    if not structure:
                        continue

                    # Définition des permissions de base pour la catégorie (overwrites)
                    cat_overwrites = {guild.me: discord.PermissionOverwrite(view_channel=True)}
                    if structure.get("staff_only"):
                        cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                        if admin_role: cat_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                        if mod_role: cat_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
                    elif config.get("verification_system") == "enabled":
                        cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                        if verified_role: cat_overwrites[verified_role] = discord.PermissionOverwrite(view_channel=True)
                    
                    # Cas spécial pour la catégorie ACCUEIL
                    if "ACCUEIL" in category_name:
                        cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, create_public_threads=False, create_private_threads=False)

                    # Création de la catégorie
                    try:
                        category = await guild.create_category(category_name, overwrites=cat_overwrites, reason="DiscordMaker Setup")
                        # On marque également la catégorie dans la DB.
                        async with get_db_connection() as conn:
                            await conn.execute("INSERT OR IGNORE INTO created_elements (guild_id, element_id, element_type) VALUES (?, ?, ?)", (guild.id, category.id, 'category'))
                            await conn.commit()
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer la catégorie `{category_name}`.")
                        continue

                    # Salons textuels
                    for channel_name in structure["text"]:
                        chan_overwrites = cat_overwrites.copy() # Hérite des permissions de la catégorie
                        # Permissions spécifiques au salon
                        if "annonces" in channel_name and verified_role:
                            chan_overwrites[verified_role] = discord.PermissionOverwrite(send_messages=False, create_public_threads=False, create_private_threads=False)
                        if "vérification" in channel_name:
                            # Visible par tous, mais personne ne peut écrire...
                            chan_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, create_public_threads=False, create_private_threads=False)
                            # ... SAUF le bot lui-même, pour qu'il puisse poster le message de bienvenue et de vérification.
                            chan_overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True)

                        
                        try:
                            new_channel = await guild.create_text_channel(channel_name, category=category, overwrites=chan_overwrites, reason="DiscordMaker Setup")
                            # Et on marque le salon.
                            async with get_db_connection() as conn:
                                await conn.execute("INSERT OR IGNORE INTO created_elements (guild_id, element_id, element_type) VALUES (?, ?, ?)", (guild.id, new_channel.id, 'channel'))
                                await conn.commit()
                            await asyncio.sleep(0.5)
                            # Si on crée le salon de logs, on le configure automatiquement dans les paramètres du serveur.
                            if "logs-modération" in channel_name:
                                async with get_db_connection() as conn:
                                    await conn.execute("INSERT OR REPLACE INTO guild_settings (guild_id, mod_log_channel_id) VALUES (?, ?)", (guild.id, new_channel.id))
                                    await conn.commit()
                        except discord.Forbidden:
                            await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer le salon `{channel_name}`.")

                    # Salons vocaux
                    for channel_name in structure["voice"]:
                        voice_overwrites = cat_overwrites.copy()
                        try:
                            if "AFK" in channel_name and verified_role:
                                voice_overwrites[verified_role] = discord.PermissionOverwrite(speak=False)
                            new_channel = await guild.create_voice_channel(channel_name, category=category, overwrites=voice_overwrites, reason="DiscordMaker Setup")
                            # Et on marque le salon vocal.
                            async with get_db_connection() as conn:
                                await conn.execute("INSERT OR IGNORE INTO created_elements (guild_id, element_id, element_type) VALUES (?, ?, ?)", (guild.id, new_channel.id, 'channel'))
                                await conn.commit()
                            await asyncio.sleep(0.5)
                        except discord.Forbidden:
                            await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer le salon `{channel_name}`.")

            # --- Système de vérification ---
            if config.get("verification_system") == "enabled":
                verification_channel = discord.utils.get(guild.text_channels, name="✅・vérification")
                if verification_channel:
                    embed = discord.Embed(
                        title=f"Bienvenue sur {guild.name} !",
                        description="Pour accéder au reste du serveur et discuter avec les autres membres, "
                                    "veuillez cliquer sur le bouton ci-dessous.\n\n"
                                    "Cela confirme que vous avez lu et accepté les règles.",
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="Si vous rencontrez un problème, contactez un membre du staff.")
                    await verification_channel.send(embed=embed, view=VerificationView())
            
            # On envoie la confirmation finale en DM pour être sûr que l'utilisateur la voie, même si le salon de commande a été supprimé.
            try:
                await interaction.user.send(f"✅ La construction du serveur **{guild.name}** est terminée !")
            except discord.Forbidden:
                # Si les DMs sont fermés, on tente de répondre au followup, mais ça peut échouer si le salon a été supprimé.
                await interaction.followup.send("✅ Construction du serveur terminée ! (Impossible d'envoyer une confirmation en DM)", ephemeral=True)

    @maker_group.command(name="reset", description="Nettoie les rôles et salons créés par le bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        """Supprime uniquement les éléments (rôles, salons) que le bot a créés, en se basant sur la base de données."""
        class ConfirmView(discord.ui.View):
            def __init__(self, cog_instance):
                super().__init__(timeout=60)
                self.cog_instance = cog_instance

            @discord.ui.button(label="Confirmer la Réinitialisation", style=discord.ButtonStyle.danger)
            async def confirm(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                await view_interaction.response.defer(ephemeral=True)
                self.clear_items()
                button.disabled = True
                await view_interaction.edit_original_response(content="🔄 Réinitialisation en cours...", view=None)
                await self.cog_instance._cleanup_guild(view_interaction.guild)
                try:
                    await view_interaction.user.send(f"✅ Le serveur **{view_interaction.guild.name}** a été réinitialisé avec succès.")
                except discord.Forbidden:
                    print(f"Impossible d'envoyer un DM à {view_interaction.user}. Leurs DMs sont probablement fermés.")

            @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
            async def cancel(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                self.clear_items()
                await view_interaction.response.edit_message(content="Opération annulée.", view=None)

        embed = discord.Embed(
            title="🚨 Confirmation Requise 🚨",
            description="**Êtes-vous absolument certain de vouloir réinitialiser ce serveur ?**\n\n"
                        "Cette action supprimera de manière irréversible **uniquement les rôles et salons connus du bot** (ceux définis dans sa configuration).\n\n"
                        "Les éléments que vous avez créés manuellement seront conservés.\n\n"
                        "**Cette action ne peut pas être annulée.**",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=ConfirmView(self), ephemeral=True)

    # --- Vérification de permission personnalisée ---
    def is_admin_or_creator():
        """Vérifie si l'utilisateur est un admin du serveur OU le créateur du bot."""
        async def predicate(interaction: discord.Interaction) -> bool:
            # L'ID du créateur est stocké sur l'instance du bot (client)
            creator_id = getattr(interaction.client, 'creator_id', None)
            
            # L'utilisateur est le créateur du bot
            if creator_id and str(interaction.user.id) == creator_id:
                return True
            # L'utilisateur a les permissions d'administrateur sur le serveur
            return interaction.user.guild_permissions.administrator
        return app_commands.check(predicate)

    @maker_group.command(name="backup", description="Crée une sauvegarde JSON de la structure actuelle du serveur.")
    @is_admin_or_creator()
    async def backup(self, interaction: discord.Interaction):
        """Crée une sauvegarde de la structure du serveur (rôles, salons) et l'envoie en message privé."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

        await interaction.followup.send("🔄 Création de la sauvegarde en cours...", ephemeral=True)

        backup_file_path = None
        try:
            # On utilise la fonction existante pour créer le fichier de sauvegarde
            backup_file_path = await create_server_backup(guild)
            if not backup_file_path:
                await interaction.followup.send("❌ Une erreur est survenue lors de la création du fichier de sauvegarde.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"📄 Sauvegarde du serveur {guild.name}",
                description="Voici une sauvegarde de la structure de votre serveur (rôles et salons). **Conservez ce fichier précieusement.**",
                color=discord.Color.green()
            )
            embed.add_field(name="Utilisation", value="Ce fichier `.json` peut être utilisé avec la commande `/discordmaker restore` pour recréer cette structure sur n'importe quel serveur où vous êtes propriétaire.", inline=False)
            embed.set_footer(text="⚠️ ATTENTION : Cette sauvegarde n'inclut PAS les messages, les membres, ou les fichiers du serveur.")

            await interaction.user.send(embed=embed, file=discord.File(backup_file_path))
            await interaction.followup.send("✅ La sauvegarde vous a été envoyée en message privé.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("⚠️ Impossible de vous envoyer la sauvegarde en DM. Vos messages privés sont probablement fermés. La sauvegarde a été créée mais n'a pas pu être envoyée.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Une erreur inattendue est survenue : {e}", ephemeral=True)
        finally:
            # Nettoyage : on supprime le fichier de sauvegarde du disque après l'avoir envoyé (ou tenté de l'envoyer).
            if backup_file_path and os.path.exists(backup_file_path):
                os.remove(backup_file_path)

    @maker_group.command(name="full-reset", description="[DANGER] Réinitialise totalement le serveur (Owner uniquement).")
    async def full_reset(self, interaction: discord.Interaction):
        """Supprime TOUS les rôles et salons du serveur, avec une double confirmation pour la sécurité."""
        guild = interaction.guild
        if interaction.user.id != guild.owner_id:
            await interaction.response.send_message("❌ Seul le propriétaire du serveur peut exécuter cette commande.", ephemeral=True)
            return

        class ConfirmFullResetView(discord.ui.View):
            def __init__(self, cog_instance, bot_instance):
                super().__init__(timeout=60)
                self.bot_instance = bot_instance
                self.cog_instance = cog_instance

            @discord.ui.button(label="Confirmer la Suppression Totale", style=discord.ButtonStyle.danger)
            async def confirm(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                await view_interaction.response.defer(ephemeral=True)
                self.clear_items()
                await view_interaction.edit_original_response(content="⚠️ **Dernière confirmation requise !**\nPour finaliser la suppression, veuillez taper `SUPPRIMER` en majuscules dans ce salon.", view=None)

                def check(m: discord.Message):
                    return m.author == view_interaction.user and m.channel == view_interaction.channel and m.content == "SUPPRIMER"

                try:
                    msg = await self.bot_instance.wait_for('message', check=check, timeout=30.0)
                    await msg.delete()
                except asyncio.TimeoutError:
                    await view_interaction.followup.send("❌ Délai de confirmation dépassé. Opération annulée.", ephemeral=True)
                    return
                except discord.HTTPException:
                    pass # Pas grave si on ne peut pas supprimer le message de confirmation

                await view_interaction.followup.send("🔄 Création d'une sauvegarde du serveur avant suppression...", ephemeral=True)
                backup_file_path = await create_server_backup(guild)
                if backup_file_path:
                    try:
                        embed_backup = discord.Embed(
                            title=f"📄 Sauvegarde du serveur {guild.name}",
                            description="Voici une sauvegarde de la structure de votre serveur (rôles et salons) avant sa réinitialisation complète. **Conservez ce fichier précieusement.**",
                            color=discord.Color.orange()
                        )
                        embed_backup.add_field(name="À quoi sert ce fichier ?", value="Ce fichier `.json` peut être utilisé avec la commande `/discordmaker restore` pour recréer cette structure.", inline=False)
                        embed_backup.set_footer(text="⚠️ ATTENTION : Cette sauvegarde n'inclut PAS les messages, les membres, ou les fichiers du serveur.")
                        await view_interaction.user.send(embed=embed_backup, file=discord.File(backup_file_path))
                    except discord.Forbidden:
                        await view_interaction.followup.send("⚠️ Impossible de vous envoyer la sauvegarde en DM. Vos messages privés sont probablement fermés.", ephemeral=True)

                await view_interaction.followup.send("💥 Suppression totale en cours...", ephemeral=True)
                await self.cog_instance._full_cleanup_guild(guild)
                await view_interaction.user.send(f"✅ La suppression totale du serveur **{guild.name}** est terminée.")

            @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
            async def cancel(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                self.clear_items()
                await view_interaction.response.edit_message(content="Opération annulée.", view=None)

        embed = discord.Embed(title="🚨 CONFIRMATION DE SUPPRESSION TOTALE 🚨", description="Cette action est **extrêmement destructive** et supprimera **TOUS** les rôles et salons de ce serveur que le bot peut gérer. Une sauvegarde sera tentée et envoyée en message privé.", color=discord.Color.dark_red())
        await interaction.response.send_message(embed=embed, view=ConfirmFullResetView(self, self.bot), ephemeral=True)

    @maker_group.command(name="restore", description="Restaure la structure du serveur depuis un fichier de sauvegarde.")
    @app_commands.describe(
        backup_file="Le fichier de sauvegarde (.json) à utiliser.",
    )
    async def restore(self, interaction: discord.Interaction, backup_file: discord.Attachment):
        """Restaure la structure d'un serveur à partir d'un fichier de sauvegarde .json."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if interaction.user.id != guild.owner_id:
            await interaction.followup.send("❌ Seul le propriétaire du serveur peut exécuter cette commande.", ephemeral=True)
            return

        if not backup_file.filename.endswith('.json'):
            await interaction.followup.send("❌ Le fichier doit être au format `.json`.", ephemeral=True)
            return

        try:
            backup_content = await backup_file.read()
            backup_data = json.loads(backup_content)
            # On vérifie que le fichier JSON a bien la structure attendue.
            if "roles" not in backup_data or "channels" not in backup_data:
                raise ValueError("Structure de sauvegarde invalide.")
        except (json.JSONDecodeError, ValueError) as e:
            await interaction.followup.send(f"❌ Fichier de sauvegarde invalide ou corrompu : {e}", ephemeral=True)
            return

        # On limite le nombre d'éléments à créer pour éviter les abus ou les fichiers malveillants (rate-limits Discord).
        # Limiter le nombre total d'éléments pour prévenir les abus
        MAX_ROLES = 250 # Limite de Discord est 250, on peut être un peu plus strict
        MAX_CHANNELS = 500 # Limite de Discord est 500

        num_roles = len(backup_data.get("roles", []))
        num_channels = len(backup_data.get("channels", []))

        if num_roles > MAX_ROLES or num_channels > MAX_CHANNELS:
            error_msg = f"❌ Fichier de sauvegarde rejeté pour des raisons de sécurité. Trop d'éléments détectés.\n" \
                        f"- Rôles : {num_roles} (max: {MAX_ROLES})\n" \
                        f"- Salons : {num_channels} (max: {MAX_CHANNELS})"
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        class ConfirmRestoreView(discord.ui.View):
            def __init__(self, cog_instance, bot_instance, backup_filename: str):
                super().__init__(timeout=60)
                self.cog_instance = cog_instance
                self.bot_instance = bot_instance
                self.backup_filename = backup_filename
                self.full_reset = False # Désactivé par défaut pour plus de sécurité
                self.update_reset_button()

            def update_reset_button(self):
                """Met à jour l'apparence du bouton 'Full Reset' pour montrer s'il est activé ou non."""
                if self.full_reset:
                    self.toggle_reset.label = "Full Reset: Activé"
                    self.toggle_reset.style = discord.ButtonStyle.success
                else:
                    self.toggle_reset.label = "Full Reset: Désactivé"
                    self.toggle_reset.style = discord.ButtonStyle.secondary

            def create_embed(self) -> discord.Embed:
                """Génère l'embed de confirmation en fonction de si le 'Full Reset' est activé."""
                reset_warning = "\n\n**ATTENTION : L'option `full_reset` est activée.** TOUS les rôles et salons actuels seront supprimés avant la restauration." if self.full_reset else ""
                return discord.Embed(
                    title="🚨 CONFIRMATION DE RESTAURATION 🚨",
                    description=f"Vous êtes sur le point de restaurer la structure du serveur **{guild.name}** depuis le fichier `{self.backup_filename}`."
                                f"{reset_warning}\n\nCette action est irréversible.",
                    color=discord.Color.dark_orange()
                )

            @discord.ui.button(label="Confirmer la Restauration", style=discord.ButtonStyle.danger)
            async def confirm(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                await view_interaction.response.defer(ephemeral=True)
                self.clear_items()
                await view_interaction.edit_original_response(content="⚠️ **Dernière confirmation requise !**\nPour finaliser la restauration, veuillez taper `RESTAURER` en majuscules.", view=None)

                def check(m: discord.Message):
                    return m.author == view_interaction.user and m.channel == view_interaction.channel and m.content == "RESTAURER"

                try:
                    msg = await self.bot_instance.wait_for('message', check=check, timeout=30.0)
                    await msg.delete()
                except asyncio.TimeoutError:
                    await view_interaction.followup.send("❌ Délai de confirmation dépassé. Opération annulée.", ephemeral=True)
                    return
                except discord.HTTPException:
                    pass

                # On verrouille l'opération pour s'assurer qu'elle aille jusqu'au bout sans interruption.
                async with self.bot_instance.critical_operation_lock:
                    try:
                        if self.full_reset:
                            await view_interaction.followup.send("💥 Suppression totale du serveur en cours... Les prochaines étapes seront envoyées en message privé.", ephemeral=True)
                            await self.cog_instance._full_cleanup_guild(guild)
                            await view_interaction.user.send(f"🔄 Restauration du serveur **{guild.name}** en cours... Cela peut prendre plusieurs minutes.")
                        else:
                            await view_interaction.followup.send("🔄 Restauration en cours... Cela peut prendre plusieurs minutes.", ephemeral=True)

                        await self.cog_instance._restore_from_backup(guild, backup_data)

                        if self.full_reset:
                            await view_interaction.user.send(f"✅ La restauration du serveur **{guild.name}** est terminée.")
                        else:
                            await view_interaction.followup.send("✅ Restauration terminée !", ephemeral=True)
                    except (discord.Forbidden, discord.HTTPException, RuntimeError) as e:
                        # On attrape aussi RuntimeError pour l'échec critique
                        await view_interaction.user.send(f"❌ Une erreur critique est survenue lors de la restauration du serveur **{guild.name}** : {e}")

            @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
            async def cancel(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                self.clear_items()
                await view_interaction.response.edit_message(content="Opération annulée.", view=None)

            @discord.ui.button(label="Full Reset: Désactivé", style=discord.ButtonStyle.secondary, row=1)
            async def toggle_reset(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                """Active ou désactive l'option de suppression totale avant la restauration."""
                self.full_reset = not self.full_reset
                self.update_reset_button()
                await view_interaction.response.edit_message(embed=self.create_embed(), view=self)

        view = ConfirmRestoreView(self, self.bot, backup_file.filename)
        await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=True)

    @maker_group.command(name="post-roles", description="Poste le message pour s'attribuer des rôles.")
    @app_commands.describe(channel="Le salon où envoyer le message. Par défaut, le salon actuel.") # noqa: E501
    @app_commands.checks.has_permissions(administrator=True)
    async def post_roles(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Poste un message avec un menu déroulant pour que les membres puissent s'auto-attribuer des rôles."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        target_channel = channel or interaction.channel
        
        # On charge la configuration du serveur pour savoir quels rôles proposer.
        config = load_config(interaction.guild_id)
        chosen_roles = config.get("roles", [])

        # On ne garde que les rôles qui sont à la fois dans la config ET dans la liste des rôles auto-attribuables.
        final_assignable_roles = [role for role in chosen_roles if role in SELF_ASSIGNABLE_ROLES]

        if not final_assignable_roles:
            await interaction.followup.send("❌ Aucun rôle auto-attribuable n'est configuré pour ce serveur. Veuillez en ajouter via `/discordmaker setup`.", ephemeral=True)
            return

        # Vérifier que ces rôles existent bien sur le serveur
        for role_name in final_assignable_roles:
            if not discord.utils.get(interaction.guild.roles, name=role_name):
                await interaction.followup.send(f"❌ Le rôle `{role_name}` n'existe pas. Veuillez le créer avec `/discordmaker start`.", ephemeral=True)
                return

        embed = discord.Embed(
            title="✨ Choisissez vos Rôles",
            description="Utilisez le menu ci-dessous pour sélectionner les rôles que vous souhaitez obtenir (notifications, jeux, etc.).\nVous pouvez en sélectionner plusieurs.",
            color=discord.Color.gold()
        )
        await target_channel.send(embed=embed, view=RoleMenuView(final_assignable_roles, self.bot)) # noqa
        await interaction.followup.send(f"✅ Le message de sélection de rôles a été envoyé dans {target_channel.mention}.", ephemeral=True)

    @setup.error
    @start.error
    @reset.error
    @backup.error
    @restore.error
    @full_reset.error
    @post_roles.error
    async def maker_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Un gestionnaire d'erreurs centralisé pour toutes les commandes de ce cog."""
        if isinstance(error, app_commands.CheckFailure):
            # Gère notre check personnalisé `is_admin_or_creator`
            await interaction.response.send_message("❌ Vous devez être administrateur du serveur ou le créateur du bot pour utiliser cette commande.", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        else:
            print(f"Erreur dans DiscordMaker: {error}")
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original
            error_message = f"Une erreur inattendue est survenue: {error}"
            try:
                if not interaction.response.is_done(): # noqa
                    await interaction.response.send_message(error_message, ephemeral=True)
                else:
                    await interaction.followup.send(error_message, ephemeral=True)
            except discord.errors.HTTPException as e:
                # Si le salon n'existe plus (code 10003), tente d'envoyer un DM
                if e.code == 10003:
                    await interaction.user.send(f"Une erreur est survenue sur le serveur **{interaction.guild.name}** et je n'ai pas pu répondre dans le salon (il a probablement été supprimé).\nErreur: `{error}`")
                    try:
                        await interaction.user.send(f"Une erreur est survenue sur le serveur **{interaction.guild.name}** et je n'ai pas pu répondre dans le salon (il a probablement été supprimé).\nErreur: `{error}`")
                    except discord.Forbidden:
                        pass # L'utilisateur a aussi ses DMs fermés, on ne peut rien faire.

# --- Vérification de permission personnalisée (déplacée au niveau du module) ---
def is_admin_or_creator():
    """Vérifie si l'utilisateur est un admin du serveur OU le créateur du bot."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # L'ID du créateur est stocké sur l'instance du bot (client)
        creator_id = getattr(interaction.client, 'creator_id', None)
        
        # L'utilisateur est le créateur du bot
        if creator_id and str(interaction.user.id) == creator_id:
            return True
        # L'utilisateur a les permissions d'administrateur sur le serveur
        return interaction.user.guild_permissions.administrator

    async def _cleanup_guild(self, guild: discord.Guild):
        """Supprime uniquement les rôles et salons créés par le bot, en se basant sur les IDs stockés dans la base de données."""
        async with get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT element_id, element_type FROM created_elements WHERE guild_id = ?", (guild.id,)) as cursor:
                elements_to_delete = await cursor.fetchall()

            # Trier pour supprimer les salons avant les catégories
            channels = [e['element_id'] for e in elements_to_delete if e['element_type'] == 'channel']
            categories = [e['element_id'] for e in elements_to_delete if e['element_type'] == 'category']
            roles = [e['element_id'] for e in elements_to_delete if e['element_type'] == 'role']

            # Suppression des salons
            for channel_id in channels:
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="DiscordMaker Reset")
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        print(f"Permissions manquantes pour supprimer le salon {channel.name} ({channel.id})")
                    except discord.HTTPException as e:
                        print(f"Erreur HTTP lors de la suppression du salon {channel_id}: {e}")

            # Suppression des catégories
            for category_id in categories:
                category = guild.get_channel(category_id)
                if category:
                    try:
                        await category.delete(reason="DiscordMaker Reset")
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        print(f"Permissions manquantes pour supprimer la catégorie {category.name} ({category.id})")
                    except discord.HTTPException as e:
                        print(f"Erreur HTTP lors de la suppression de la catégorie {category_id}: {e}")

            # Suppression des rôles
            for role_id in roles:
                role = guild.get_role(role_id)
                if role and not role.is_integration() and not role.is_premium_subscriber() and role < guild.me.top_role:
                    try:
                        await role.delete(reason="DiscordMaker Reset")
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        print(f"Permissions manquantes pour supprimer le rôle {role.name} ({role.id})")
                    except discord.HTTPException as e:
                        print(f"Erreur HTTP lors de la suppression du rôle {role_id}: {e}")

            # Une fois tout supprimé, on vide la table des éléments créés pour ce serveur.
            await conn.execute("DELETE FROM created_elements WHERE guild_id = ?", (guild.id,))
            await conn.commit()

    async def _full_cleanup_guild(self, guild: discord.Guild):
        """Supprime TOUS les rôles et salons que le bot a la permission de supprimer."""
        # Suppression des salons
        for channel in guild.channels:
            try:
                await channel.delete(reason="DiscordMaker Full Reset")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException):
                print(f"Impossible de supprimer le salon {channel.name} ({channel.id})")

        # Suppression des rôles (sauf @everyone, rôles d'intégration/boost et rôles au-dessus du bot)
        for role in guild.roles:
            if role.is_default() or role.is_integration() or role.is_premium_subscriber() or role >= guild.me.top_role:
                continue
            try:
                await role.delete(reason="DiscordMaker Full Reset")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException):
                print(f"Impossible de supprimer le rôle {role.name} ({role.id})")

    async def _restore_from_backup(self, guild: discord.Guild, backup_data: dict):
        """Contient la logique de restauration d'un serveur à partir des données d'un fichier de sauvegarde."""
        # --- Phase 1: Création des rôles ---
        created_roles = {}
        for role_data in reversed(backup_data.get("roles", [])): # Créer du plus haut au plus bas
            try:
                role = await guild.create_role(
                    name=role_data["name"],
                    permissions=discord.Permissions(role_data["permissions"]),
                    color=discord.Color.from_rgb(*role_data["color"]),
                    hoist=role_data.get("hoist", False),
                    mentionable=role_data.get("mentionable", False),
                    reason="DiscordMaker Restore"
                )
                created_roles[role_data["name"]] = role
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Erreur lors de la création du rôle {role_data['name']}: {e}")

        # --- Phase 2: Création des catégories et salons ---
        created_channels = {}
        # D'abord les catégories
        for channel_data in backup_data.get("channels", []):
            if channel_data["type"] == "category":
                try:
                    category = await guild.create_category(
                        name=channel_data["name"],
                        position=channel_data.get("position"),
                        reason="DiscordMaker Restore"
                    )
                    created_channels[channel_data["id"]] = category
                    await asyncio.sleep(0.5)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Erreur lors de la création de la catégorie {channel_data['name']}: {e}")

        # Ensuite les autres salons
        for channel_data in backup_data.get("channels", []):
            if channel_data["type"] != "category":
                chan_type = channel_data["type"]
                category = created_channels.get(channel_data["category_id"])

                create_func = None
                if chan_type == "text":
                    create_func = guild.create_text_channel
                elif chan_type == "voice":
                    create_func = guild.create_voice_channel

                if create_func:
                    try:
                        channel = await create_func(
                            name=channel_data["name"],
                            category=category,
                            position=channel_data.get("position"),
                            reason="DiscordMaker Restore"
                        )
                        created_channels[channel_data["id"]] = channel
                        await asyncio.sleep(0.5)
                    except (discord.Forbidden, discord.HTTPException) as e:
                        print(f"Erreur lors de la création du salon {channel_data['name']}: {e}")

        # --- Phase 3: Application des permissions (overwrites) ---
        for channel_data in backup_data.get("channels", []):
            channel = created_channels.get(channel_data["id"])
            if not channel:
                continue

            overwrites = {}
            for target_name, perms_data in channel_data.get("overwrites", {}).items():
                target = None
                if perms_data["type"] == "role":
                    target = created_roles.get(target_name) or discord.utils.get(guild.roles, name=target_name)
                # La restauration des permissions pour un membre spécifique n'est pas gérée pour rester simple et robuste.

                if target:
                    overwrites[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(perms_data["allow"]),
                        discord.Permissions(perms_data["deny"])
                    )

            try:
                await channel.edit(overwrites=overwrites, reason="DiscordMaker Restore Permissions")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Erreur lors de l'application des permissions pour {channel.name}: {e}")

# --- Setup du cog ---
async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(DiscordMakerCog(bot))
