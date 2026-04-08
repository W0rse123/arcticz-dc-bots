import discord
from discord import app_commands
from discord.ui import Select, View
import os
import logging
import json
import traceback

# ---------- CONFIGURATION ----------
DISCORD_TOKEN = "Discord Bot Token"
GUILD_ID = Guild Id
SCHEMATICS_CHANNEL_NAME = "schematics"
CONFIG_FILE = "config.json"
# ----------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file {CONFIG_FILE} not found!")
        return None, None
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    allowed_roles = config.get('allowed_roles', [])
    schematics_list = config.get('schematics', [])
    schematics_dict = {}
    for idx, s in enumerate(schematics_list):
        schematics_dict[str(idx)] = {
            'label': s.get('name', 'Unnamed'),
            'description': s.get('description', ''),
            'file_name': s.get('file_name', ''),
            'file_path': s.get('file_path', ''),
            'details': s.get('details', 'No description provided.')
        }
    return allowed_roles, schematics_dict

class SchematicSelect(Select):
    def __init__(self, schematics_dict: dict, original_message: discord.Message = None):
        self.schematics_dict = schematics_dict
        self.original_message = original_message
        options = []
        for value, data in schematics_dict.items():
            label = data['label'][:100]
            desc = data['description'][:100] if data['description'] else None
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=desc,
                    emoji="📄"
                )
            )
        super().__init__(placeholder="Choose a schematic...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            data = self.schematics_dict.get(self.values[0])
            if not data:
                await interaction.followup.send("❌ Invalid selection.", ephemeral=True)
                return
            if not os.path.exists(data['file_path']):
                await interaction.followup.send(
                    f"⚠️ **Schematic file not found!**\n`{data['file_name']}` is missing.",
                    ephemeral=True
                )
                return
            embed = discord.Embed(
                title="📦 Schematic Download",
                description=data['details'][:4000],
                color=discord.Color.green()
            )
            embed.add_field(name="📄 File Name", value=f"`{data['file_name']}`", inline=False)
            embed.set_footer(text="Arcticz Helper")
            file = discord.File(data['file_path'], filename=data['file_name'])
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            logger.info(f"User {interaction.user} downloaded: {data['label']}")

            if self.original_message:
                new_view = SchematicView(self.schematics_dict, self.original_message)
                await self.original_message.edit(view=new_view)

        except Exception as e:
            logger.error(f"Error in dropdown: {e}\n{traceback.format_exc()}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Error", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Error", ephemeral=True)
            except:
                pass

class SchematicView(View):
    def __init__(self, schematics_dict: dict, original_message: discord.Message = None):
        super().__init__(timeout=None)
        self.add_item(SchematicSelect(schematics_dict, original_message))

class SchematicBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.allowed_roles = []
        self.schematics_dict = {}

    async def setup_hook(self):
        self.allowed_roles, self.schematics_dict = load_config()
        if self.allowed_roles is None or self.schematics_dict is None:
            logger.error("Failed to load config.")
            return
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        os.makedirs("schematics", exist_ok=True)
        for data in self.schematics_dict.values():
            if not os.path.exists(data['file_path']):
                with open(data['file_path'], 'w') as f:
                    f.write(f"Placeholder for {data['file_name']}\nReplace with real schematic.")
                logger.warning(f"Created placeholder: {data['file_path']}")

    async def on_ready(self):
        logger.info(f"✅ Logged in as {self.user}")
        logger.info(f"📁 Loaded {len(self.schematics_dict)} schematics")
        await self.refresh_schematics_channel()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Download Schematics"))

    async def refresh_schematics_channel(self):
        channel = None
        for c in self.get_all_channels():
            if c.name == SCHEMATICS_CHANNEL_NAME and isinstance(c, discord.TextChannel):
                channel = c
                break
        if not channel:
            logger.warning(f"Channel #{SCHEMATICS_CHANNEL_NAME} not found!")
            return
        async for message in channel.history(limit=100):
            if message.author == self.user:
                try:
                    await message.delete()
                    logger.info(f"Deleted old menu message {message.id}")
                except:
                    pass
        await self.create_menu(channel)

    async def create_menu(self, channel):
        embed = discord.Embed(
            title="🗂️ Schematic Library",
            description="",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Arcticz Helper • Schematic Manager")
        embed.add_field(
            name="📌 How to use",
            value="1. Select a schematic from the dropdown\n"
                  "2. The bot will send the file **privately** to you\n"
                  "3. Click the attachment to download",
            inline=False
        )
        view = SchematicView(self.schematics_dict)
        # Send silently - no push notification, no role/user mentions
        message = await channel.send(
            embed=embed,
            view=view,
            silent=True,
            allowed_mentions=discord.AllowedMentions.none()
        )
        for child in view.children:
            if isinstance(child, SchematicSelect):
                child.original_message = message
        logger.info(f"Created fresh permanent menu in #{channel.name} (ID: {message.id})")

bot = SchematicBot()

def has_allowed_role(interaction: discord.Interaction) -> bool:
    if not bot.allowed_roles:
        return True
    user_roles = [role.id for role in interaction.user.roles]
    return any(rid in user_roles for rid in bot.allowed_roles)

@bot.tree.command(name="schematics", description="Get the schematic menu")
async def schematics_cmd(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        embed = discord.Embed(title="❌ Access Denied", description="No permission.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    embed = discord.Embed(title="🗂️ Schematic Library", description="", color=discord.Color.blue())
    embed.set_footer(text="Arcticz Helper")
    view = SchematicView(bot.schematics_dict)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

@bot.tree.command(name="how_to_use", description="[ADMIN ONLY] Admin guide")
async def how_to_use_cmd(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        embed = discord.Embed(title="❌ Access Denied", description="Admins only.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    embed = discord.Embed(title="🔧 Admin Guide: Arcticz Schematic Bot", description="How to manage the bot", color=discord.Color.gold())
    embed.add_field(name="📁 Adding Schematics", value="Edit config.json, upload .litematic to schematics/, restart bot.", inline=False)
    embed.add_field(name="🔒 Managing Access", value="Add role IDs to allowed_roles in config.json. Empty list = everyone.", inline=False)
    embed.add_field(name="📂 Channel Setup", value=f"Create #{SCHEMATICS_CHANNEL_NAME} with view-only for everyone, bot needs send/embed/attach.", inline=False)
    embed.add_field(name="🔄 Refreshing Menu", value="The bot automatically deletes and recreates the menu on every restart.", inline=False)
    embed.set_footer(text="Arcticz Helper • Admin Documentation")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(f"Command error: {error}")
    await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "PASTE_YOUR_NEW_BOT_TOKEN_HERE":
        logger.error("❌ Please paste your real Discord token!")
    else:
        try:
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"Failed to start: {e}")
