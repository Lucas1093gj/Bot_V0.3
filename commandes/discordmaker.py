import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import os
import time
# --- Configuration principale du module ---
# --- Constantes de configuration ---
CONFIG_DIR = "guild_configs"
BACKUP_DIR = "guild_backups"

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
    """Construit le chemin vers le fichier de config d'un serveur."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    return os.path.join(CONFIG_DIR, f"{guild_id}.json")

def load_config(guild_id: int) -> dict:
    """Charge la configuration d'un serveur depuis son fichier JSON."""
    path = get_config_path(guild_id)
    if not os.path.exists(path):
        # Retourne une config par défaut si le fichier n'existe pas
        return {"roles": [], "channel_categories": [], "cleanup_policy": "keep", "verification_system": "disabled"}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(guild_id: int, config: dict):
    """Sauvegarde la configuration d'un serveur dans son fichier JSON."""
    with open(get_config_path(guild_id), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

async def create_server_backup(guild: discord.Guild) -> str | None:
    """Crée une sauvegarde JSON de la structure du serveur (rôles et salons)."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    backup_data = {
        "guild_name": guild.name,
        "guild_id": guild.id,
        "backup_timestamp": int(time.time()),
        "roles": [],
        "channels": []
    }

    # Sauvegarde des rôles
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

    # Sauvegarde des salons et catégories
    for channel in sorted(guild.channels, key=lambda c: c.position):
        # On ignore les threads, on ne veut que les vrais salons
        if isinstance(channel, discord.Thread): continue

        overwrites = {}
        # Convertir les cibles d'overwrite en un format stockable (nom + type)
        # au lieu de l'ID, pour rendre la restauration plus robuste entre serveurs.
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
    """Bouton persistant permettant aux membres de se vérifier."""
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        self.role = role

    @discord.ui.button(label="Cliquez ici pour vérifier", style=discord.ButtonStyle.success, emoji="✅", custom_id="verification_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback du bouton de vérification."""
        if self.role in interaction.user.roles:
            await interaction.response.send_message("Vous êtes déjà vérifié !", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(self.role, reason="Vérification automatique")
                await interaction.response.send_message("✅ Vous avez été vérifié avec succès ! Vous avez maintenant accès au reste du serveur.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Je n'ai pas les permissions pour vous donner ce rôle. Veuillez contacter un administrateur.", ephemeral=True)
            except Exception as e:
                print(f"Erreur lors de l'ajout du rôle de vérification : {e}")
                await interaction.response.send_message(f"❌ Une erreur est survenue lors de la vérification.", ephemeral=True)

# --- Vues (UI) pour la sélection de rôles ---
class RoleMenuView(discord.ui.View):
    """Menu déroulant persistant pour que les membres choisissent leurs rôles."""
    def __init__(self, assignable_roles: list[str]):
        super().__init__(timeout=None)
        # On passe la liste des rôles au Select pour qu'il sache quoi afficher
        self.add_item(RoleMenuSelect(assignable_roles))

class RoleMenuSelect(discord.ui.Select):
    """Menu de sélection pour les rôles de notification."""
    def __init__(self, assignable_roles: list[str]): # noqa
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
        """Met à jour les rôles de l'utilisateur en fonction de sa sélection."""
        member = interaction.user
        
        # On ne traite que les rôles qui étaient proposés dans le menu
        possible_roles = {option.label for option in self.options}

        # Récupérer les objets Role correspondants aux noms
        assignable_roles_obj = {role.name: role for role in interaction.guild.roles if role.name in possible_roles}
        
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
    """Menu de sélection pour choisir les rôles à créer."""
    def __init__(self, current_roles: list):
        options = [
            discord.SelectOption(label=role, description=f"Activer/Désactiver le rôle {role}", default=(role in current_roles))
            for role in sorted(ROLE_DATA.keys())
        ]
        super().__init__(placeholder="Choisissez les rôles à créer...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde les rôles sélectionnés dans la configuration."""
        config = load_config(interaction.guild_id)
        config["roles"] = self.values
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Rôles configurés : `{', '.join(self.values) or 'Aucun'}`", ephemeral=True)

class ChannelSelect(discord.ui.Select):
    """Menu de sélection pour choisir les catégories de salons à créer."""
    def __init__(self, current_categories: list):
        options = [
            discord.SelectOption(label=cat, description=f"Inclure la catégorie '{cat}'", default=(cat in current_categories))
            for cat in sorted(CHANNEL_STRUCTURE.keys())
        ]
        super().__init__(placeholder="Choisissez les catégories de salons à créer...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde les catégories sélectionnées dans la configuration."""
        config = load_config(interaction.guild_id)
        config["channel_categories"] = self.values
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Catégories configurées : `{', '.join(self.values) or 'Aucune'}`", ephemeral=True)

class CleanupSelect(discord.ui.Select):
    """Menu de sélection pour la politique de nettoyage avant création."""
    def __init__(self, current_policy: str):
        options = [
            discord.SelectOption(label="Conserver", value="keep", description="Ne supprime rien avant la création (recommandé).", default=(current_policy == "keep")),
            discord.SelectOption(label="Nettoyage Intelligent", value="smart_delete", description="Supprime uniquement les éléments connus du bot.", default=(current_policy == "smart_delete")),
            discord.SelectOption(label="Suppression Totale (Dangereux)", value="full_delete", description="Supprime TOUS les rôles et salons (Owner uniquement).", default=(current_policy == "full_delete")),
        ]
        super().__init__(placeholder="Action avant la création...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde la politique de nettoyage dans la configuration."""
        config = load_config(interaction.guild_id)
        config["cleanup_policy"] = self.values[0]
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Politique de nettoyage définie sur : `{self.values[0]}`", ephemeral=True)

class VerificationSelect(discord.ui.Select):
    """Menu de sélection pour activer ou désactiver le système de vérification."""
    def __init__(self, current_status: str):
        options = [
            discord.SelectOption(label="Activé", value="enabled", description="Met en place un salon de vérification.", default=(current_status == "enabled")),
            discord.SelectOption(label="Désactivé", value="disabled", description="Aucun système de vérification.", default=(current_status == "disabled")),
        ]
        super().__init__(placeholder="Système de vérification...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Sauvegarde le statut du système de vérification."""
        config = load_config(interaction.guild_id)
        config["verification_system"] = self.values[0]
        save_config(interaction.guild_id, config) # noqa
        await interaction.response.send_message(f"✅ Système de vérification : `{self.values[0]}`", ephemeral=True)

class ConfigView(discord.ui.View):
    """Vue principale regroupant tous les menus de configuration."""
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        config = load_config(guild_id)
        self.add_item(RoleSelect(config.get("roles", [])))
        self.add_item(ChannelSelect(config.get("channel_categories", [])))
        self.add_item(CleanupSelect(config.get("cleanup_policy", "keep")))
        self.add_item(VerificationSelect(config.get("verification_system", "disabled")))

# --- Classe principale du Cog ---
class DiscordMakerCog(commands.Cog, name="DiscordMaker"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    maker_group = app_commands.Group(name="discordmaker", description="Commandes pour construire et gérer votre serveur.")

    @maker_group.command(name="setup", description="Ouvre le panneau pour configurer la structure du serveur.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        """Affiche le panneau de configuration du serveur."""
        config = load_config(interaction.guild_id)
        roles = ", ".join(f"`{r}`" for r in config.get("roles", [])) or "Aucun"
        cats = ", ".join(f"`{c}`" for c in config.get("channel_categories", [])) or "Aucune"
        policy = f"`{config.get('cleanup_policy', 'keep')}`"
        verification_status = f"`{config.get('verification_system', 'disabled').capitalize()}`"

        embed = discord.Embed(
            title="🛠️ Configuration du Serveur",
            description="Configurez votre serveur pas à pas avec les menus ci-dessous.\n"
                        "Vos choix sont sauvegardés automatiquement. Une fois prêt, lancez `/discordmaker start`.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Rôles Actuels", value=roles, inline=False)
        embed.add_field(name="Catégories Actuelles", value=cats, inline=False)
        embed.add_field(name="Politique de Nettoyage", value=policy, inline=False)
        embed.add_field(name="Système de Vérification", value=verification_status, inline=False)
        
        await interaction.response.send_message(embed=embed, view=ConfigView(interaction.guild_id), ephemeral=True)

    @maker_group.command(name="start", description="Construit le serveur avec la configuration actuelle.")
    @app_commands.checks.has_permissions(administrator=True)
    async def start(self, interaction: discord.Interaction):
        """Construit le serveur en se basant sur la configuration sauvegardée."""
        await interaction.response.defer(ephemeral=True)
        config = load_config(interaction.guild_id)
        guild = interaction.guild

        if not config.get("roles") and not config.get("channel_categories"):
            await interaction.followup.send("❌ Aucune configuration n'a été trouvée. Utilisez d'abord `/discordmaker setup`.", ephemeral=True)
            return

        await interaction.followup.send("🚀 Lancement de la construction du serveur... Cela peut prendre un moment.", ephemeral=True)

        # --- Nettoyage (si configuré) ---
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
            await self._full_cleanup_guild(guild)

        # --- Création des rôles ---
        created_roles = {}
        # Trier les rôles pour créer les plus hauts en premier
        role_creation_order = sorted(
            config.get("roles", []),
            key=lambda r: list(ROLE_DATA.keys()).index(r) if r in ROLE_DATA else -1,
            reverse=True
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
                    role = await guild.create_role(name=role_name, permissions=permissions, color=color, reason="DiscordMaker Setup", hoist=hoist)
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

            for category_name in config["channel_categories"]:
                structure = CHANNEL_STRUCTURE.get(category_name)
                if not structure:
                    continue

                # Définition des permissions de base pour la catégorie
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
                    cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

                # Création de la catégorie
                try:
                    category = await guild.create_category(category_name, overwrites=cat_overwrites, reason="DiscordMaker Setup")
                    await asyncio.sleep(0.5)
                except discord.Forbidden:
                    await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer la catégorie `{category_name}`.")
                    continue

                # Salons textuels
                for channel_name in structure["text"]:
                    chan_overwrites = cat_overwrites.copy() # Hérite des permissions de la catégorie
                    # Permissions spécifiques au salon
                    if "annonces" in channel_name and verified_role:
                        chan_overwrites[verified_role] = discord.PermissionOverwrite(send_messages=False)
                    if "vérification" in channel_name: # Visible par tous, mais personne ne peut écrire
                        chan_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                    
                    try:
                        await guild.create_text_channel(channel_name, category=category, overwrites=chan_overwrites, reason="DiscordMaker Setup")
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer le salon `{channel_name}`.")

                # Salons vocaux
                for channel_name in structure["voice"]:
                    voice_overwrites = cat_overwrites.copy()
                    try:
                        if "AFK" in channel_name and verified_role:
                            voice_overwrites[verified_role] = discord.PermissionOverwrite(speak=False)
                        await guild.create_voice_channel(channel_name, category=category, overwrites=voice_overwrites, reason="DiscordMaker Setup")
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        await interaction.channel.send(f"⚠️ Je n'ai pas la permission de créer le salon `{channel_name}`.")

        # --- Système de vérification ---
        if config.get("verification_system") == "enabled":
            verification_channel = discord.utils.get(guild.text_channels, name="✅・vérification")
            verified_role = discord.utils.get(guild.roles, name="Vérifié")
            if verification_channel and verified_role:
                embed = discord.Embed(
                    title=f"Bienvenue sur {guild.name} !",
                    description="Pour accéder au reste du serveur et discuter avec les autres membres, "
                                "veuillez cliquer sur le bouton ci-dessous.\n\n"
                                "Cela confirme que vous avez lu et accepté les règles.",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Si vous rencontrez un problème, contactez un membre du staff.")
                await verification_channel.send(embed=embed, view=VerificationView(verified_role))

        # Si un nettoyage a eu lieu, le salon original n'existe peut-être plus. On envoie un DM.
        if config.get("cleanup_policy") == "delete":
            try:
                await interaction.user.send(f"✅ La construction du serveur **{guild.name}** est terminée !")
            except discord.Forbidden:
                print(f"Impossible d'envoyer un DM à {interaction.user} pour confirmer la fin de la construction.")
        else:
            await interaction.followup.send("✅ Construction du serveur terminée !", ephemeral=True)

    @maker_group.command(name="reset", description="Nettoie les rôles et salons créés par le bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        """Affiche une confirmation pour réinitialiser le serveur."""
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

    @maker_group.command(name="full-reset", description="[DANGER] Réinitialise totalement le serveur (Owner uniquement).")
    async def full_reset(self, interaction: discord.Interaction):
        """Lance la suppression totale du serveur avec double confirmation."""
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
        """Restaure un serveur depuis un fichier .json. L'option de suppression totale est dans la confirmation."""
        guild = interaction.guild
        if interaction.user.id != guild.owner_id:
            await interaction.response.send_message("❌ Seul le propriétaire du serveur peut exécuter cette commande.", ephemeral=True)
            return

        if not backup_file.filename.endswith('.json'):
            await interaction.response.send_message("❌ Le fichier doit être au format `.json`.", ephemeral=True)
            return

        try:
            backup_content = await backup_file.read()
            backup_data = json.loads(backup_content)
            # Validation rapide de la structure du fichier
            if "roles" not in backup_data or "channels" not in backup_data:
                raise ValueError("Structure de sauvegarde invalide.")
        except (json.JSONDecodeError, ValueError) as e:
            await interaction.response.send_message(f"❌ Fichier de sauvegarde invalide ou corrompu : {e}", ephemeral=True)
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
                """Met à jour le label et le style du bouton de réinitialisation."""
                if self.full_reset:
                    self.toggle_reset.label = "Full Reset: Activé"
                    self.toggle_reset.style = discord.ButtonStyle.success
                else:
                    self.toggle_reset.label = "Full Reset: Désactivé"
                    self.toggle_reset.style = discord.ButtonStyle.secondary

            def create_embed(self) -> discord.Embed:
                """Crée l'embed de confirmation en fonction de l'état actuel."""
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
                except (discord.Forbidden, discord.HTTPException):
                    pass

            @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
            async def cancel(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                self.clear_items()
                await view_interaction.response.edit_message(content="Opération annulée.", view=None)

            @discord.ui.button(label="Full Reset: Désactivé", style=discord.ButtonStyle.secondary, row=1)
            async def toggle_reset(self, view_interaction: discord.Interaction, button: discord.ui.Button):
                """Bascule l'option de suppression totale."""
                self.full_reset = not self.full_reset
                self.update_reset_button()
                await view_interaction.response.edit_message(embed=self.create_embed(), view=self)

        view = ConfirmRestoreView(self, self.bot, backup_file.filename)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @maker_group.command(name="post-roles", description="Poste le message pour s'attribuer des rôles.")
    @app_commands.describe(channel="Le salon où envoyer le message. Par défaut, le salon actuel.") # noqa: E501
    @app_commands.checks.has_permissions(administrator=True)
    async def post_roles(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Envoie un message interactif pour l'auto-attribution de rôles."""
        target_channel = channel or interaction.channel
        
        # Charger la configuration du serveur
        config = load_config(interaction.guild_id)
        chosen_roles = config.get("roles", [])

        # 2. Filtrer pour ne garder que les rôles auto-attribuables qui ont été choisis
        final_assignable_roles = [role for role in chosen_roles if role in SELF_ASSIGNABLE_ROLES]

        if not final_assignable_roles:
            await interaction.response.send_message("❌ Aucun rôle auto-attribuable n'est configuré pour ce serveur. Veuillez en ajouter via `/discordmaker setup`.", ephemeral=True)
            return

        # Vérifier que ces rôles existent bien sur le serveur
        for role_name in final_assignable_roles:
            if not discord.utils.get(interaction.guild.roles, name=role_name):
                await interaction.response.send_message(f"❌ Le rôle `{role_name}` n'existe pas. Veuillez le créer avec `/discordmaker start`.", ephemeral=True)
                return

        embed = discord.Embed(
            title="✨ Choisissez vos Rôles",
            description="Utilisez le menu ci-dessous pour sélectionner les rôles que vous souhaitez obtenir (notifications, jeux, etc.).\nVous pouvez en sélectionner plusieurs.",
            color=discord.Color.gold()
        )
        await target_channel.send(embed=embed, view=RoleMenuView(final_assignable_roles))
        await interaction.response.send_message(f"✅ Le message de sélection de rôles a été envoyé dans {target_channel.mention}.", ephemeral=True)

    async def _cleanup_guild(self, guild: discord.Guild):
        """Supprime uniquement les rôles et salons définis dans les constantes du bot."""
        
        # Créer la liste des noms d'éléments connus du bot
        known_channel_names = set(CHANNEL_STRUCTURE.keys())
        for category_data in CHANNEL_STRUCTURE.values():
            for chan in category_data.get("text", []):
                known_channel_names.add(chan)
            for chan in category_data.get("voice", []):
                known_channel_names.add(chan)

        known_role_names = set(ROLE_DATA.keys())

        # Supprimer les salons et catégories connus (en ordre inversé pour les catégories)
        for channel in reversed(guild.channels):
            if channel.name in known_channel_names:
                try:
                    await channel.delete(reason="DiscordMaker Smart Reset")
                    await asyncio.sleep(0.5)
                except (discord.Forbidden, discord.HTTPException):
                    print(f"Impossible de supprimer le salon {channel.name} (Smart Reset)")

        # Supprimer les rôles connus
        for role in guild.roles:
            if role.name not in known_role_names:
                continue
            if role.is_default() or role.is_bot_managed() or role.position >= guild.me.top_role.position:
                continue
            try:
                await role.delete(reason="DiscordMaker Smart Reset")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException):
                print(f"Impossible de supprimer le rôle {role.name} (Smart Reset)")

    async def _full_cleanup_guild(self, guild: discord.Guild):
        """Supprime TOUS les salons et rôles gérables sur le serveur."""
        # Supprimer les salons
        for channel in guild.channels:
            try:
                await channel.delete(reason="DiscordMaker Full Reset")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException):
                print(f"Impossible de supprimer le salon {channel.name} (Full Reset)")

        # Supprimer les rôles
        for role in guild.roles:
            if role.is_default() or role.is_bot_managed() or role.position >= guild.me.top_role.position:
                continue
            try:
                await role.delete(reason="DiscordMaker Full Reset")
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException):
                print(f"Impossible de supprimer le rôle {role.name} (Full Reset)")
    
    async def _restore_from_backup(self, guild: discord.Guild, data: dict):
        """Logique de restauration des rôles et salons depuis les données de sauvegarde."""
        # --- Étape 1: Restaurer les rôles ---
        created_roles = {} # Dico pour mapper nom de rôle -> objet Role
        # Trier les rôles par position (du plus haut au plus bas) pour la création
        sorted_roles_data = sorted(data.get("roles", []), key=lambda r: r.get("position", 0), reverse=True)

        for role_data in sorted_roles_data:
            role_name = role_data.get("name")
            if not role_name or role_name == "@everyone":
                continue
            
            try:
                # Ne pas recréer les rôles qui existent déjà (cas d'un reset non-total)
                existing_role = discord.utils.get(guild.roles, name=role_name)
                if existing_role:
                    created_roles[role_name] = existing_role
                    continue

                new_role = await guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(role_data.get("permissions", 0)),
                    color=discord.Color.from_rgb(*role_data.get("color", [0, 0, 0])),
                    hoist=role_data.get("hoist", False),
                    mentionable=role_data.get("mentionable", False),
                    reason="Restauration depuis sauvegarde"
                )
                created_roles[role_name] = new_role
                await asyncio.sleep(0.5)
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Erreur lors de la création du rôle {role_name}: {e}")

        # --- Étape 2: Restaurer les catégories et salons ---
        created_categories = {} # Dico pour mapper ancien ID de catégorie -> objet CategoryChannel
        channels_data = sorted(data.get("channels", []), key=lambda c: c.get("position", 0))

        # Créer les catégories d'abord
        for channel_data in channels_data:
            if channel_data.get("type") == "category":
                try:
                    new_cat = await guild.create_category(name=channel_data["name"], reason="Restauration")
                    created_categories[channel_data.get("id")] = new_cat
                    await asyncio.sleep(0.5)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Erreur lors de la création de la catégorie {channel_data['name']}: {e}")

        # Créer les salons ensuite
        for channel_data in channels_data:
            chan_type = channel_data.get("type")
            if chan_type in ["text", "voice"]:
                category_obj = created_categories.get(channel_data.get("category_id"))
                
                # Recréer les overwrites
                overwrites = {}
                for target_name, perms_data in channel_data.get("overwrites", {}).items():
                    target_obj = discord.utils.get(guild.roles, name=target_name) or guild.default_role
                    if target_obj:
                        overwrites[target_obj] = discord.PermissionOverwrite.from_pair(discord.Permissions(perms_data["allow"]), discord.Permissions(perms_data["deny"]))

                try:
                    if chan_type == "text":
                        await guild.create_text_channel(name=channel_data["name"], category=category_obj, overwrites=overwrites, reason="Restauration")
                    elif chan_type == "voice":
                        await guild.create_voice_channel(name=channel_data["name"], category=category_obj, overwrites=overwrites, reason="Restauration")
                    await asyncio.sleep(0.5)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Erreur lors de la création du salon {channel_data['name']}: {e}")

    @setup.error
    @start.error
    @reset.error
    @restore.error
    @full_reset.error
    @post_roles.error
    async def maker_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Gestionnaire d'erreurs centralisé pour les commandes du groupe."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Vous devez être administrateur pour utiliser cette commande.", ephemeral=True)
        else:
            print(f"Erreur dans DiscordMaker: {error}")
            if isinstance(error, app_commands.CheckFailure): # Pour le @app_commands.checks.is_owner()
                return # L'erreur est déjà gérée manuellement dans la commande
            error_message = f"Une erreur inattendue est survenue: {error}"
            try:
                # Tente de répondre à l'interaction normalement
                if not interaction.response.is_done(): # noqa
                    await interaction.response.send_message(error_message, ephemeral=True)
                else:
                    await interaction.followup.send(error_message, ephemeral=True)
            except discord.errors.HTTPException as e:
                # Si le salon n'existe plus (code 10003), tente d'envoyer un DM
                if e.code == 10003:
                    await interaction.user.send(f"Une erreur est survenue sur le serveur **{interaction.guild.name}** et je n'ai pas pu répondre dans le salon (il a probablement été supprimé).\nErreur: `{error}`")

    @commands.Cog.listener()
    async def on_ready(self):
        """Ré-enregistre les vues persistantes au redémarrage du bot."""
        for guild in self.bot.guilds:
            config = load_config(guild.id)
            if config.get("verification_system") == "enabled":
                verified_role = discord.utils.get(guild.roles, name="Vérifié")
                if verified_role:
                    self.bot.add_view(VerificationView(verified_role), message_id=None)
        # La persistance de RoleMenuView nécessiterait une base de données pour être fiable après un redémarrage.

# --- Setup du cog ---
async def setup(bot: commands.Bot, **kwargs):
    await bot.add_cog(DiscordMakerCog(bot))
