import os
import re
import io
import time
import asyncio
import random
import string
import requests
import discord
from discord import app_commands
from pycognito import Cognito
from urllib.parse import urlparse
import json as _json
import base64 as _base64
from html.parser import HTMLParser
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from flask import Flask
from threading import Thread
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from datetime import datetime, timedelta

# Custom adapter to ignore SSL verification
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1_2
        kwargs['cert_reqs'] = ssl.CERT_NONE
        kwargs['assert_hostname'] = False
        return super().init_poolmanager(*args, **kwargs)

PASSWORD = "Test1234Abc!"
COGNITO_CLIENT_ID = "1kvg8re5bgu9ljqnnkjosu477k"
USER_POOL_ID = "eu-west-1_7hEawdalF"
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"
OREATE_BASE = "https://www.oreateai.com"
GPTIMAGE2_BASE = "https://gptimage2.im"

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_SIZES = ["1280x720", "720x1280"]

BRAND_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
PROGRESS_COLOR = 0xFEE75C
INFO_COLOR = 0x5865F2

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://oreateai.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Create a session that ignores SSL verification for image downloads
download_session = requests.Session()
download_session.mount('https://', SSLAdapter())
download_session.verify = False

# ─── إعداد خادم الويب (لـ Render) ─────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive and running 24/7!"

@app.route('/ping')
def ping():
    return "pong"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ─── Admin Commands - Data Management ─────────────────────────────────────────

DATA_FILE = "cmd_config.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"blacklist": [], "timeout_list": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def parse_duration(duration_str: str) -> int:
    total_seconds = 0
    pattern = r'(\d+)([smhd])'
    matches = re.findall(pattern, duration_str.lower())
    
    for value, unit in matches:
        value = int(value)
        if unit == 's':
            total_seconds += value
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 'h':
            total_seconds += value * 3600
        elif unit == 'd':
            total_seconds += value * 86400
    
    return total_seconds

def format_duration_remaining(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and days == 0 and hours == 0:
        parts.append(f"{secs}s")
    
    return " ".join(parts) if parts else "0s"

# ─── Application Owner Check ─────────────────────────────────────────────────

async def is_app_owner(interaction: discord.Interaction) -> bool:
    """Check if user is the application owner"""
    try:
        app_info = await client.application_info()
        return interaction.user.id == app_info.owner.id
    except:
        return False

# ─── Check Functions ─────────────────────────────────────────────────────────

async def is_user_banned(interaction: discord.Interaction) -> bool:
    data = load_data()
    user_id = str(interaction.user.id)
    
    if user_id in data.get("blacklist", []):
        embed = discord.Embed(
            title="⛔ You Are Banned",
            description="You have been banned from using this bot's commands.",
            color=ERROR_COLOR
        )
        embed.set_footer(text="Contact bot owner for more information.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return True
    return False

async def is_user_timeout(interaction: discord.Interaction) -> bool:
    data = load_data()
    user_id = str(interaction.user.id)
    timeout_list = data.get("timeout_list", [])
    
    for entry in timeout_list:
        if entry["user_id"] == user_id:
            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.now() < expires_at:
                remaining = int((expires_at - datetime.now()).total_seconds())
                embed = discord.Embed(
                    title="⏰ You Are Timed Out",
                    description=f"You have been timed out from using this bot's commands.\n\n**Remaining time:** `{format_duration_remaining(remaining)}`\n**Reason:** {entry.get('reason', 'No reason provided')}",
                    color=PROGRESS_COLOR
                )
                embed.set_footer(text="Contact bot owner for more information.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return True
            else:
                timeout_list.remove(entry)
                save_data(data)
                return False
    return False

async def check_cmd_status(interaction: discord.Interaction, command_name: str) -> bool:
    if await is_user_banned(interaction):
        return False
    
    if await is_user_timeout(interaction):
        return False
    
    data = load_data()
    guild_id = str(interaction.guild.id) if interaction.guild else None
    
    if not guild_id or guild_id not in data or command_name not in data[guild_id]:
        return True
    
    cmd_data = data[guild_id][command_name]
    mode = cmd_data.get("mode", "normal")
    
    if mode == "down":
        embed = discord.Embed(
            title=cmd_data.get("title", "Command Down"),
            description=cmd_data.get("description", "This command is currently down."),
            color=cmd_data.get("color", ERROR_COLOR)
        )
        embed.set_footer(text="Please try again later.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    if mode == "buggy":
        embed = discord.Embed(
            description="⚠️ **This Command is Buggy!** Some features may not work correctly.",
            color=PROGRESS_COLOR
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return True
    
    return True

# ─── Setstatus Command (Customize Command) ───────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="setstatus", description="Customize a command's behavior (Owner only)")
@app_commands.describe(
    command_name="Name of the command to customize",
    mode="Select the mode for the command",
    title="Title for the embed (optional)",
    description="Description for the embed (optional)",
    color="Hex color for the embed like FF0000 (optional)"
)
@app_commands.choices(mode=[
    app_commands.Choice(name="Normal - Command works fine", value="normal"),
    app_commands.Choice(name="Down - Command is down show embed", value="down"),
    app_commands.Choice(name="Buggy - Command is buggy show warning", value="buggy"),
])
async def setstatus(
    interaction: discord.Interaction,
    command_name: str,
    mode: app_commands.Choice[str],
    title: str = None,
    description: str = None,
    color: str = None
):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        data[guild_id] = {}

    if mode.value == "normal":
        if command_name in data[guild_id]:
            del data[guild_id][command_name]
        save_data(data)
        embed = discord.Embed(
            description=f"✅ `/{command_name}` has been set back to **Normal** mode.",
            color=SUCCESS_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    hex_color = BRAND_COLOR
    if color:
        try:
            hex_color = int(color.replace("#", ""), 16)
        except ValueError:
            pass

    data[guild_id][command_name] = {
        "mode": mode.value,
        "title": title or ("Command Down" if mode.value == "down" else "Command Buggy"),
        "description": description or (
            f"The command `/{command_name}` is currently **down** for maintenance. Please try again later."
            if mode.value == "down"
            else f"The command `/{command_name}` is currently experiencing issues. Some features may not work."
        ),
        "color": hex_color
    }

    save_data(data)

    preview_embed = discord.Embed(
        title="⚙️ Command Customized",
        color=BRAND_COLOR
    )
    preview_embed.add_field(name="Command", value=f"`/{command_name}`", inline=True)
    preview_embed.add_field(name="Mode", value=mode.name, inline=True)
    preview_embed.add_field(
        name="Preview Embed",
        value=f"**{data[guild_id][command_name]['title']}**\n{data[guild_id][command_name]['description']}",
        inline=False
    )
    preview_embed.set_footer(text=f"Configured by {interaction.user}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=preview_embed, ephemeral=True)

# ─── Ban Command ──────────────────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="ban", description="Ban a user from using the bot permanently (Owner only)")
@app_commands.describe(
    user="The user to ban from using the bot",
    reason="Reason for the ban (optional)"
)
async def ban_user(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = None
):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if user == client.user:
        embed = discord.Embed(
            description="❌ You cannot ban the bot!",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    if "blacklist" not in data:
        data["blacklist"] = []
    
    user_id = str(user.id)
    if user_id in data["blacklist"]:
        embed = discord.Embed(
            description=f"❌ {user.mention} is already banned from using the bot.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if "timeout_list" in data:
        data["timeout_list"] = [entry for entry in data["timeout_list"] if entry["user_id"] != user_id]
    
    data["blacklist"].append(user_id)
    
    if "ban_reasons" not in data:
        data["ban_reasons"] = {}
    data["ban_reasons"][user_id] = {
        "reason": reason or "No reason provided",
        "banned_by": interaction.user.id,
        "banned_at": datetime.now().isoformat()
    }
    
    save_data(data)
    
    embed = discord.Embed(
        title="✅ User Banned From Bot",
        description=f"{user.mention} has been banned from using **all bot commands**.",
        color=SUCCESS_COLOR
    )
    embed.add_field(name="User", value=f"{user}\n`{user.id}`", inline=True)
    embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)
    
    try:
        dm_embed = discord.Embed(
            title=f"⛔ You have been banned from using {client.user.name}",
            description=f"**Reason:** {reason or 'No reason provided'}\n**Banned by:** {interaction.user}",
            color=ERROR_COLOR
        )
        await user.send(embed=dm_embed)
    except:
        pass

# ─── Unban Command ──────────────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="unban", description="Unban a user from using the bot (Owner only)")
@app_commands.describe(
    user="The user to unban",
    reason="Reason for the unban (optional)"
)
async def unban_user(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = None
):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    user_id = str(user.id)
    
    if "blacklist" not in data or user_id not in data["blacklist"]:
        embed = discord.Embed(
            description=f"❌ {user.mention} is not banned from using the bot.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data["blacklist"].remove(user_id)
    
    save_data(data)
    
    embed = discord.Embed(
        title="✅ User Unbanned From Bot",
        description=f"{user.mention} can now use bot commands again.",
        color=SUCCESS_COLOR
    )
    embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
    
    await interaction.followup.send(embed=embed)
    
    try:
        dm_embed = discord.Embed(
            title=f"✅ You have been unbanned from using {client.user.name}",
            description=f"**Reason:** {reason or 'No reason provided'}",
            color=SUCCESS_COLOR
        )
        await user.send(embed=dm_embed)
    except:
        pass

# ─── Banned Users Command ───────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="banned_users", description="Show all users banned from using the bot (Owner only)")
async def banned_users(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    blacklist = data.get("blacklist", [])
    ban_reasons = data.get("ban_reasons", {})
    
    if not blacklist:
        embed = discord.Embed(
            title="📋 Banned Users",
            description="No users are currently banned from using the bot.",
            color=INFO_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    banned_list = []
    for user_id in blacklist:
        try:
            user = await client.fetch_user(int(user_id))
            user_name = f"{user.name} (`{user_id}`)"
        except:
            user_name = f"Unknown User (`{user_id}`)"
        
        reason = ban_reasons.get(user_id, {}).get("reason", "No reason provided")
        banned_by_id = ban_reasons.get(user_id, {}).get("banned_by", "Unknown")
        
        try:
            banned_by_user = await client.fetch_user(int(banned_by_id)) if banned_by_id != "Unknown" else None
            banned_by = banned_by_user.name if banned_by_user else str(banned_by_id)
        except:
            banned_by = str(banned_by_id)
        
        banned_list.append(f"**{user_name}**\n└ Reason: {reason}\n└ Banned by: {banned_by}")
    
    chunks = [banned_list[i:i+10] for i in range(0, len(banned_list), 10)]
    
    for i, chunk in enumerate(chunks):
        embed = discord.Embed(
            title=f"📋 Banned Users (Page {i+1}/{len(chunks)})",
            description="\n\n".join(chunk),
            color=ERROR_COLOR
        )
        embed.set_footer(text=f"Total: {len(blacklist)} banned users")
        await interaction.followup.send(embed=embed, ephemeral=(i==0))

# ─── Timeout Command ────────────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="timeout", description="Timeout a user from using the bot for a specific duration (Owner only)")
@app_commands.describe(
    user="The user to timeout from using the bot",
    duration="How long to timeout the user (e.g., 1h, 30m, 2d, 1h30m)",
    reason="Reason for the timeout (optional)"
)
async def timeout_user(
    interaction: discord.Interaction,
    user: discord.User,
    duration: str,
    reason: str = None
):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if user == client.user:
        embed = discord.Embed(
            description="❌ You cannot timeout the bot!",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    seconds = parse_duration(duration)
    if seconds <= 0:
        embed = discord.Embed(
            description="❌ Invalid duration format. Use formats like: `30m`, `2h`, `1d`, `1h30m`",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    if "timeout_list" not in data:
        data["timeout_list"] = []
    
    user_id = str(user.id)
    
    data["timeout_list"] = [entry for entry in data["timeout_list"] if entry["user_id"] != user_id]
    
    if user_id in data.get("blacklist", []):
        embed = discord.Embed(
            description=f"❌ {user.mention} is permanently banned. Use `unban` first.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    expires_at = datetime.now() + timedelta(seconds=seconds)
    
    data["timeout_list"].append({
        "user_id": user_id,
        "expires_at": expires_at.isoformat(),
        "reason": reason or "No reason provided",
        "timed_out_by": interaction.user.id,
        "timed_out_at": datetime.now().isoformat()
    })
    
    save_data(data)
    
    embed = discord.Embed(
        title="⏰ User Timed Out From Bot",
        description=f"{user.mention} has been timed out from using **all bot commands**.",
        color=PROGRESS_COLOR
    )
    embed.add_field(name="User", value=f"{user}\n`{user.id}`", inline=True)
    embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
    embed.add_field(name="Duration", value=f"`{format_duration_remaining(seconds)}`", inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.add_field(name="Expires At", value=f"<t:{int(expires_at.timestamp())}:R>", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)
    
    try:
        dm_embed = discord.Embed(
            title=f"⏰ You have been timed out from using {client.user.name}",
            description=f"**Duration:** {format_duration_remaining(seconds)}\n**Reason:** {reason or 'No reason provided'}\n**Timed out by:** {interaction.user}",
            color=PROGRESS_COLOR
        )
        await user.send(embed=dm_embed)
    except:
        pass

# ─── Untimeout Command ──────────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="untimeout", description="Remove timeout from a user (Owner only)")
@app_commands.describe(
    user="The user to remove timeout from",
    reason="Reason for removing the timeout (optional)"
)
async def untimeout_user(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = None
):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    user_id = str(user.id)
    timeout_list = data.get("timeout_list", [])
    
    user_timeout = None
    for entry in timeout_list:
        if entry["user_id"] == user_id:
            user_timeout = entry
            break
    
    if not user_timeout:
        embed = discord.Embed(
            description=f"❌ {user.mention} is not currently timed out.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data["timeout_list"] = [entry for entry in timeout_list if entry["user_id"] != user_id]
    save_data(data)
    
    embed = discord.Embed(
        title="✅ Timeout Removed From Bot",
        description=f"{user.mention} can now use bot commands again.",
        color=SUCCESS_COLOR
    )
    embed.add_field(name="Owner", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
    
    await interaction.followup.send(embed=embed)
    
    try:
        dm_embed = discord.Embed(
            title=f"✅ Your timeout from using {client.user.name} has been removed",
            description=f"**Reason:** {reason or 'No reason provided'}",
            color=SUCCESS_COLOR
        )
        await user.send(embed=dm_embed)
    except:
        pass

# ─── Timed Out Users Command ─────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=False)
@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@tree.command(name="timedout_users", description="Show all users currently timed out from using the bot (Owner only)")
async def timedout_users(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # Check if user is the application owner
    if not await is_app_owner(interaction):
        embed = discord.Embed(
            description="❌ Only the bot application owner can use this command.",
            color=ERROR_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data = load_data()
    timeout_list = data.get("timeout_list", [])
    
    current_time = datetime.now()
    active_timeouts = []
    for entry in timeout_list:
        expires_at = datetime.fromisoformat(entry["expires_at"])
        if current_time < expires_at:
            active_timeouts.append(entry)
    
    if not active_timeouts:
        embed = discord.Embed(
            title="📋 Timed Out Users",
            description="No users are currently timed out from using the bot.",
            color=INFO_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    data["timeout_list"] = active_timeouts
    save_data(data)
    
    timeout_list_display = []
    for entry in active_timeouts:
        user_id = entry["user_id"]
        expires_at = datetime.fromisoformat(entry["expires_at"])
        remaining = int((expires_at - current_time).total_seconds())
        
        try:
            user = await client.fetch_user(int(user_id))
            user_name = f"{user.name} (`{user_id}`)"
        except:
            user_name = f"Unknown User (`{user_id}`)"
        
        reason = entry.get("reason", "No reason provided")
        
        timeout_list_display.append(f"**{user_name}**\n└ Remaining: `{format_duration_remaining(remaining)}`\n└ Reason: {reason}")
    
    chunks = [timeout_list_display[i:i+10] for i in range(0, len(timeout_list_display), 10)]
    
    for i, chunk in enumerate(chunks):
        embed = discord.Embed(
            title=f"📋 Timed Out Users (Page {i+1}/{len(chunks)})",
            description="\n\n".join(chunk),
            color=PROGRESS_COLOR
        )
        embed.set_footer(text=f"Total: {len(active_timeouts)} timed out users")
        await interaction.followup.send(embed=embed, ephemeral=(i==0))

# ─── GPT Image 2 Automation ──────────────────────────────────────────────────

class GPTImage2Automation:
    def __init__(self):
        self.base_url = GPTIMAGE2_BASE
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "dnt": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
            "origin": GPTIMAGE2_BASE,
            "referer": f"{GPTIMAGE2_BASE}/ai-image-generator"
        })
        
    def generate_credentials(self):
        letters = ''.join(random.choices(string.ascii_lowercase, k=6))
        numbers = ''.join(random.choices(string.digits, k=2))
        email = f"{letters}{numbers}@gmail.com"
        
        capitals = ''.join(random.choices(string.ascii_uppercase, k=2))
        smalls = ''.join(random.choices(string.ascii_lowercase, k=4))
        nums = ''.join(random.choices(string.digits, k=3))
        password = f"{capitals}{smalls}{nums}"
        
        username = ''.join(random.choices(string.ascii_lowercase, k=4))
        
        return email, password, username
    
    def sign_up(self, email, password, name):
        url = f"{self.base_url}/api/auth/sign-up/email"
        data = {"email": email, "password": password, "name": name}
        response = self.session.post(url, json=data)
        return response.json()
    
    def get_session(self, token):
        url = f"{self.base_url}/api/auth/get-session"
        self.session.cookies.set("__Secure-better-auth.session_token", token)
        response = self.session.get(url)
        return response.json()
    
    def get_user_info(self):
        url = f"{self.base_url}/api/user/get-user-info"
        response = self.session.post(url)
        return response.json()
    
    def generate_image_text_to_image(self, prompt):
        url = f"{self.base_url}/api/ai/generate"
        data = {
            "mediaType": "image",
            "scene": "text-to-image",
            "provider": "fal",
            "model": "openai/gpt-image-2",
            "prompt": prompt,
            "options": {
                "image_size": "portrait_16_9",
                "quality": "medium"
            },
            "credits": 5
        }
        response = self.session.post(url, json=data)
        return response.json()
    
    def generate_image_image_to_image(self, prompt, image_urls):
        url = f"{self.base_url}/api/ai/generate"
        data = {
            "mediaType": "image",
            "scene": "image-to-image",
            "provider": "fal",
            "model": "openai/gpt-image-2",
            "prompt": prompt,
            "options": {
                "image_size": "auto",
                "quality": "medium",
                "image_urls": image_urls[:4]
            },
            "credits": 5
        }
        response = self.session.post(url, json=data)
        return response.json()
    
    def query_task(self, task_uuid):
        url = f"{self.base_url}/api/ai/query"
        data = {"taskId": task_uuid}
        response = self.session.post(url, json=data)
        return response.json()
    
    def upload_image_to_gptimage2(self, image_bytes, filename):
        upload_url_res = self.session.post(
            f"{self.base_url}/api/upload/generate-url",
            json={"filename": filename, "type": "image"}
        )
        upload_data = upload_url_res.json()
        
        if upload_data.get('code') != 0:
            raise RuntimeError(f"Failed to get upload URL: {upload_data}")
        
        upload_url = upload_data['data']['url']
        file_url = upload_data['data']['fileUrl']
        
        files = {'file': (filename, image_bytes, f'image/{filename.split(".")[-1]}')}
        upload_response = requests.post(upload_url, files=files)
        
        if upload_response.status_code != 200:
            raise RuntimeError(f"Failed to upload image: {upload_response.status_code}")
        
        return file_url
    
    def run(self, prompt, ref_images=None):
        email, password, username = self.generate_credentials()
        
        signup_response = self.sign_up(email, password, username)
        
        if 'token' not in signup_response:
            raise RuntimeError(f"Signup failed: {signup_response}")
        
        token = signup_response['token']
        
        session_data = self.get_session(token)
        
        if 'session' not in session_data:
            raise RuntimeError(f"Session error: {session_data}")
        
        user_info = self.get_user_info()
        
        if user_info.get('code') != 0:
            raise RuntimeError(f"Error getting user info: {user_info}")
        
        credits = user_info['data']['credits']['remainingCredits']
        
        if credits < 5:
            raise RuntimeError(f"Not enough credits! Need 5, have {credits}")
        
        image_urls = []
        if ref_images:
            for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:4]):
                try:
                    uploaded_url = self.upload_image_to_gptimage2(image_bytes, filename)
                    image_urls.append(uploaded_url)
                except Exception as e:
                    print(f"Failed to upload reference image {idx+1}: {e}")
        
        if image_urls:
            generate_response = self.generate_image_image_to_image(prompt, image_urls)
        else:
            generate_response = self.generate_image_text_to_image(prompt)
        
        if generate_response.get('code') != 0:
            raise RuntimeError(f"Generation error: {generate_response}")
        
        task_uuid = generate_response['data']['id']
        
        max_attempts = 60
        attempt = 0
        
        while attempt < max_attempts:
            time.sleep(2)
            status_response = self.query_task(task_uuid)
            
            if status_response.get('code') == 0:
                status = status_response['data'].get('status')
                
                if status == "success":
                    task_result = status_response['data'].get('taskResult', '{}')
                    if isinstance(task_result, str):
                        task_result = _json.loads(task_result)
                    
                    images = task_result.get('images', [])
                    
                    if images:
                        image_url = images[0].get('url')
                        if image_url:
                            return {
                                "url": image_url,
                                "download_url": image_url,
                            }
                    
                    task_info = status_response['data'].get('taskInfo', '{}')
                    if isinstance(task_info, str):
                        task_info = _json.loads(task_info)
                    
                    alt_images = task_info.get('images', [])
                    if alt_images:
                        image_url = alt_images[0].get('imageUrl') or alt_images[0].get('url')
                        if image_url:
                            return {
                                "url": image_url,
                                "download_url": image_url,
                            }
                    
                    raise RuntimeError("No image URL found in response")
                
                elif status == "failed":
                    raise RuntimeError(f"Task failed: {status_response['data'].get('taskInfo', {})}")
                
                elif status in ["pending", "processing"]:
                    pass
            attempt += 1
        
        raise TimeoutError("Timeout waiting for image generation")

def run_gptimage2_generation(prompt: str, ref_images: list = None) -> dict:
    automation = GPTImage2Automation()
    return automation.run(prompt, ref_images)

# ─── Temp email ──────────────────────────────────────────────────────────────

class TempEmail:
    def __init__(self):
        self.sid_token = None
        self.email_addr = None
        self.seq = 0
        self.seen_ids = set()

    def generate(self):
        r = requests.get(f"{GUERRILLA_API}?f=get_email_address", timeout=15)
        data = r.json()
        self.sid_token = data["sid_token"]
        self.seq = 0
        self.seen_ids = set()
        raw = data["email_addr"]
        at = raw.find("@")
        self.email_addr = (raw[:at + 1] if at != -1 else raw + "@") + "sharklasers.com"
        return self.email_addr

    def check_inbox(self):
        if not self.sid_token:
            return None
        try:
            r = requests.get(
                f"{GUERRILLA_API}?f=check_email&sid_token={self.sid_token}&seq={self.seq}",
                timeout=15,
            )
            data = r.json()
            if "seq" in data:
                self.seq = data["seq"]
            for email in data.get("list", []):
                if email["mail_id"] in self.seen_ids:
                    continue
                self.seen_ids.add(email["mail_id"])
                code = self._extract_code(email.get("mail_subject", ""))
                if not code:
                    code = self._fetch_body_code(email["mail_id"])
                if code:
                    return code
        except Exception:
            pass
        return None

    def _fetch_body_code(self, mail_id):
        try:
            r = requests.get(
                f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={self.sid_token}",
                timeout=15,
            )
            d = r.json()
            body = re.sub(r"<[^>]+>", "", d.get("mail_body", "") or "")
            return (
                self._extract_code(d.get("mail_subject", ""))
                or self._extract_code(body)
            )
        except Exception:
            return None

    @staticmethod
    def _extract_code(text):
        if not text:
            return None
        m = re.search(r"(\d{6})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{5})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4})", text)
        return m.group(1) if m else None

    def wait_for_code(self, timeout=120, interval=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            code = self.check_inbox()
            if code:
                return code
            time.sleep(interval)
        return None

# ─── Cognito auth ─────────────────────────────────────────────────────────────

def sign_up_with_cognito(email):
    try:
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
        cognito.email = email
        cognito.given_name = "Bot"
        cognito.family_name = "User"
        cognito.register(username=email, password=PASSWORD)
        return {"status": "success", "message": "User signed up, waiting for confirmation"}
    except Exception as e:
        error_msg = str(e)
        if "User already exists" in error_msg or "UsernameExistsException" in error_msg:
            return {"status": "exists", "message": "User already exists"}
        raise RuntimeError(f"Sign-up failed: {error_msg}")

def confirm_sign_up_with_cognito(email, code):
    try:
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
        cognito.confirm_sign_up(confirmation_code=code)
        return True
    except Exception as e:
        raise RuntimeError(f"Confirmation failed: {str(e)}")

def sign_in_with_cognito(email):
    try:
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
        cognito.authenticate(password=PASSWORD)
        id_token = cognito.id_token
        if not id_token:
            raise RuntimeError("Failed to get ID token after authentication")
        return id_token
    except Exception as e:
        error_msg = str(e)
        if "NEW_PASSWORD_REQUIRED" in error_msg:
            try:
                cognito = Cognito(
                    user_pool_id=USER_POOL_ID,
                    client_id=COGNITO_CLIENT_ID,
                    username=email,
                    user_pool_region="eu-west-1",
                )
                cognito.authenticate(password=PASSWORD)
                if hasattr(cognito, "new_password_required") and cognito.new_password_required:
                    cognito.set_new_password_challenge(PASSWORD)
                    cognito.authenticate(password=PASSWORD)
                return cognito.id_token
            except Exception as inner_e:
                raise RuntimeError(f"Failed to handle password change: {str(inner_e)}")
        raise RuntimeError(f"Authentication failed: {error_msg}")

# ─── Synthesia workspace ───────────────────────────────────────────────────────

def create_workspace(id_token):
    headers = {
        "Authorization": id_token,
        "Content-Type": "application/json",
    }
    res = requests.get("https://api.synthesia.io/workspaces?scope=public", headers=headers)
    res.raise_for_status()
    data = res.json()
    if data.get("results") and len(data["results"]) > 0:
        workspace_id = data["results"][0]["id"]
    else:
        res = requests.post(
            "https://api.synthesia.io/workspaces",
            headers=headers,
            json={"strict": True, "includeDemoVideos": False},
        )
        res.raise_for_status()
        workspace_id = res.json()["workspace"]["id"]

    try:
        requests.post(
            "https://api.synthesia.io/user/onboarding/setPreferredWorkspaceId",
            headers=headers,
            json={"workspaceId": workspace_id},
        )
    except Exception:
        pass

    try:
        requests.post(
            "https://api.synthesia.io/user/onboarding/initialize",
            headers=headers,
            json={
                "featureFlags": {"freemiumEnabled": True},
                "queryParams": {"paymentPlanType": "free"},
                "allowReinitialize": False,
            },
        )
    except Exception:
        pass

    for _ in range(5):
        try:
            res = requests.post(
                "https://api.synthesia.io/user/onboarding/completeCurrentStep",
                headers=headers,
                json={"featureFlags": {"freemiumEnabled": True}},
            )
            if res.status_code != 200:
                break
        except Exception:
            break

    try:
        requests.post(
            "https://api.synthesia.io/user/questionnaire",
            headers=headers,
            json={
                "company": {"size": "emerging", "industry": "professional_services"},
                "seniority": "individual_contributor",
                "persona": "marketing",
            },
        )
    except Exception:
        pass

    try:
        requests.post(
            "https://api.synthesia.io/user/signupForm",
            headers=headers,
            json={"analyticsCookies": {}},
        )
    except Exception:
        pass

    try:
        requests.post(
            f"https://api.synthesia.io/billing/self-serve/{workspace_id}/paywall",
            headers=headers,
            json={
                "targetPlan": "freemium",
                "redirectUrl": "https://app.synthesia.io/#/?plan_created=true&payment_plan=freemium",
            },
        )
    except Exception:
        pass

    time.sleep(30)
    return workspace_id

# ─── Synthesia media generation ───────────────────────────────────────────────

SIZE_TO_ASPECT_RATIO = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1080x1080": "1:1",
}

VIDEO_MODELS = {"fal_veo3", "fal_veo3_fast", "sora_2", "seedance_2", "wan_2_6"}

def start_synthesia_generation(token, workspace_id, prompt, size, model):
    try:
        aspect_ratio = SIZE_TO_ASPECT_RATIO.get(size, "16:9")

        if model == "sora_2":
            model_request = {
                "modelName": "sora_2",
                "generateAudio": True,
                "aspectRatio": aspect_ratio,
            }
            media_type = "video"
        elif model in ("fal_veo3", "fal_veo3_fast"):
            model_request = {
                "modelName": model,
                "aspectRatio": aspect_ratio,
                "generateAudio": True,
            }
            media_type = "video"
        else:
            model_request = {
                "modelName": "nanobanana_pro",
                "aspectRatio": aspect_ratio,
            }
            media_type = "image"

        r = requests.post(
            "https://api.prd.synthesia.io/avatarServices/api/generatedMedia/stockFootage/bulk?numberOfResults=1",
            headers={"Authorization": token, "Content-Type": "application/json"},
            json={
                "mediaType": media_type,
                "modelRequest": model_request,
                "userPrompt": prompt,
                "workspaceId": workspace_id,
            },
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()
        if not result or len(result) == 0:
            raise RuntimeError("No asset ID returned from Synthesia")
        return result[0]["mediaAssetId"]
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to start generation: {str(e)}")

def poll_synthesia(token, asset_id, timeout=600, interval=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(
                f"https://api.synthesia.io/assets/{asset_id}",
                headers={"Authorization": token},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("uploadMetadata", {}).get("status", "unknown")
            if status == "ready":
                return data
            if status == "failed":
                raise RuntimeError("Generation failed on Synthesia side.")
            time.sleep(interval)
        except requests.exceptions.RequestException as e:
            print(f"Polling error: {e}, retrying...")
            time.sleep(interval)
    raise TimeoutError("Generation timed out after 10 minutes.")

def run_synthesia_generation(prompt: str, size: str, model: str) -> dict:
    temp = TempEmail()
    email = temp.generate()

    sign_up_with_cognito(email)

    code = temp.wait_for_code(timeout=120)
    if not code:
        raise RuntimeError("Timed out waiting for email verification code.")

    confirm_sign_up_with_cognito(email, code)
    token = sign_in_with_cognito(email)
    workspace_id = create_workspace(token)
    asset_id = start_synthesia_generation(token, workspace_id, prompt, size, model)
    result = poll_synthesia(token, asset_id)

    return {
        "url": result.get("url", ""),
        "download_url": result.get("downloadUrl", ""),
    }

# ─── OreateAI image generation (Nano Banana 2) ───────────────────────────────

_OREATE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def _oreate_generate_email() -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=14)) + "@gmail.com"

def _oreate_generate_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1!"

def _oreate_encrypt_password(plain_text: str, public_key_pem: str) -> str:
    clean_pem = public_key_pem.strip()
    if "BEGIN RSA PUBLIC KEY" in clean_pem:
        b64 = (
            clean_pem
            .replace("-----BEGIN RSA PUBLIC KEY-----", "")
            .replace("-----END RSA PUBLIC KEY-----", "")
            .replace("\n", "").replace("\r", "").strip()
        )
        key = RSA.import_key(_base64.b64decode(b64))
    else:
        key = RSA.import_key(clean_pem)

    cipher = PKCS1_v1_5.new(key)
    return _base64.b64encode(cipher.encrypt(plain_text.encode())).decode()

def _oreate_upload_image_to_gcs(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    
    token_res = requests.post(
        f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
            "User-Agent": _OREATE_UA,
        },
        json={
            "mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}],
            "source": "aiImage",
        },
        timeout=30,
    )
    token_res.raise_for_status()
    token_json = token_res.json()
    
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}")
    if not key_data and key_list:
        key_data = list(key_list.values())[0]
    if not key_data:
        raise RuntimeError(f"No upload token key received. Available: {list(key_list.keys())}")
    
    bucket = key_data["bucket"]
    object_path = key_data["objectPath"]
    session_key = key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    
    gcs_init_url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    )
    
    init_res = requests.post(
        gcs_init_url,
        headers={
            "Authorization": f"Bearer {session_key}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": content_type,
            "X-Upload-Content-Length": str(len(image_bytes)),
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        timeout=30,
    )
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    
    put_res = requests.put(
        upload_url,
        headers={
            "Content-Type": content_type,
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        data=image_bytes,
        timeout=120,
    )
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    
    return {
        "bos_url": object_path,
        "doc_title": clean_name,
        "doc_type": ext,
        "size": len(image_bytes),
        "bosUrl": object_path,
        "flag": "upload",
        "type": "file",
        "status": 1,
    }

def _oreate_extract_image_url_from_stream(response_text: str) -> str:
    if not response_text:
        return None
    
    lines = response_text.split('\n')
    for line in lines:
        if line.startswith('data: '):
            try:
                data = _json.loads(line[6:])
                if data.get('data', {}).get('imgUrl'):
                    return data['data']['imgUrl']
                if data.get('data', {}).get('url'):
                    return data['data']['url']
                if data.get('imgUrl'):
                    return data['imgUrl']
                if data.get('url'):
                    return data['url']
            except (_json.JSONDecodeError, KeyError):
                pass
    
    m = re.search(r"(https?://[^\s\"'<>]+\.(jpg|jpeg|png|gif|webp|bmp)(\?[^\s\"'<>]*)?)", response_text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def run_oreate_generation(prompt: str, size: str, ref_images: list) -> dict:
    ticket_res = requests.get(
        f"{OREATE_BASE}/passport/api/getticket",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Client-Type": "pc",
            "Locale": "en-US",
            "Referer": f"{OREATE_BASE}/home/vertical/aiImage",
            "User-Agent": _OREATE_UA,
        },
        timeout=30,
    )
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    
    ticket_id = ticket_data["data"]["ticketID"]
    public_key = ticket_data["data"]["pk"]
    
    cookies = ticket_res.cookies.get_dict()
    
    email = _oreate_generate_email()
    password = _oreate_generate_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    
    signup_res = requests.post(
        f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/vertical/aiImage",
            "User-Agent": _OREATE_UA,
        },
        json={
            "fr": "GGSEMIMAGE",
            "email": email,
            "ticketID": ticket_id,
            "password": encrypted_password,
            "jt": "",
        },
        timeout=30,
    )
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"OreateAI signup failed: {signup_data.get('status', {}).get('msg')}")
    
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    
    attachments = []
    for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
        try:
            att = _oreate_upload_image_to_gcs(image_bytes, filename, file_ext, session_cookies)
            attachments.append(att)
        except Exception as e:
            print(f"Ref {idx+1} upload FAILED: {e}")
    
    chat_res = requests.post(
        f"{OREATE_BASE}/oreate/create/chat",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json={"type": "aiImage", "docId": ""},
        timeout=30,
    )
    chat_res.raise_for_status()
    chat_data = chat_res.json()
    chat_id = chat_data.get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"OreateAI: no chatId in response")
    
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    
    request_body = {
        "jt": jt_token,
        "ua": _OREATE_UA,
        "js_env": "h5",
        "extra": {
            "email": email,
            "vip": "0",
            "reg_ts": int(time.time()),
            "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1",
            "bid": "19caf744b12438441a8a1c",
            "doc_name": "",
            "module_name": "gpt4o",
        },
        "clientType": "wap",
        "type": "chat",
        "chatType": "aiImage",
        "chatTitle": "Unnamed Session",
        "focusId": chat_id,
        "chatId": chat_id,
        "from": "home",
        "messages": [{
            "role": "user",
            "content": prompt,
            "attachments": attachments,
        }],
        "isFirst": True,
    }
    
    sse_res = requests.post(
        f"{OREATE_BASE}/oreate/sse/stream",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json=request_body,
        stream=True,
        timeout=180,
    )
    sse_res.raise_for_status()
    
    image_url = None
    full_response = ""
    
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        
        extracted = _oreate_extract_image_url_from_stream(chunk)
        if extracted:
            image_url = extracted
            break
        
        lines = chunk.split("\n")
        for line in lines:
            if line.startswith("data: "):
                try:
                    data = _json.loads(line[6:])
                    if data.get("data", {}).get("imgUrl"):
                        image_url = data["data"]["imgUrl"]
                        break
                    if data.get("data", {}).get("url"):
                        image_url = data["data"]["url"]
                        break
                except (_json.JSONDecodeError, KeyError):
                    pass
        
        if image_url:
            break
    
    if not image_url:
        image_url = _oreate_extract_image_url_from_stream(full_response)
    
    if not image_url:
        raise RuntimeError("OreateAI: no image URL found in response")
    
    return {
        "url": image_url,
        "download_url": image_url,
        "is_nanobanana2": True,
    }

# ─── Wan 2.6 Video Generation ────────────────────────────────────────────────

def _oreate_generate_video_password() -> str:
    chars = []
    for _ in range(8):
        chars.append(random.choice("0123456789abcdef"))
    return "Aa" + "".join(chars) + "1"

def _oreate_upload_video_reference_image(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    
    token_res = requests.post(
        f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
            "User-Agent": _OREATE_UA,
        },
        json={
            "mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}],
            "source": "aiVideo",
        },
        timeout=30,
    )
    token_res.raise_for_status()
    token_json = token_res.json()
    
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}")
    if not key_data and key_list:
        key_data = list(key_list.values())[0]
    if not key_data:
        raise RuntimeError(f"No upload token key received. Available: {list(key_list.keys())}")
    
    bucket = key_data["bucket"]
    object_path = key_data["objectPath"]
    session_key = key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    
    gcs_init_url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    )
    
    init_res = requests.post(
        gcs_init_url,
        headers={
            "Authorization": f"Bearer {session_key}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": content_type,
            "X-Upload-Content-Length": str(len(image_bytes)),
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        timeout=30,
    )
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    
    put_res = requests.put(
        upload_url,
        headers={
            "Content-Type": content_type,
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        data=image_bytes,
        timeout=120,
    )
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    
    return {
        "bos_url": object_path,
        "doc_title": clean_name,
        "doc_type": ext,
        "size": len(image_bytes),
        "bosUrl": object_path,
        "flag": "upload",
        "type": "file",
        "status": 1,
    }

def run_wan26_generation(prompt: str, size: str, ref_images: list = None) -> dict:
    ticket_res = requests.get(
        f"{OREATE_BASE}/passport/api/getticket",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Client-Type": "pc",
            "Locale": "en-US",
            "Referer": f"{OREATE_BASE}/home/vertical/aiVideo",
            "User-Agent": _OREATE_UA,
        },
        timeout=30,
    )
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    
    ticket_id = ticket_data["data"]["ticketID"]
    public_key = ticket_data["data"]["pk"]
    
    cookies = ticket_res.cookies.get_dict()
    
    email = _oreate_generate_email()
    password = _oreate_generate_video_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    
    signup_res = requests.post(
        f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/vertical/aiVideo",
            "User-Agent": _OREATE_UA,
        },
        json={
            "fr": "GGSEMVIDEO",
            "email": email,
            "ticketID": ticket_id,
            "password": encrypted_password,
            "jt": "",
        },
        timeout=30,
    )
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Wan 2.6 signup failed: {signup_data.get('status', {}).get('msg')}")
    
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    
    attachments = []
    if ref_images:
        for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
            try:
                att = _oreate_upload_video_reference_image(image_bytes, filename, file_ext, session_cookies)
                attachments.append(att)
            except Exception as e:
                print(f"Ref {idx+1} upload FAILED: {e}")
    
    chat_res = requests.post(
        f"{OREATE_BASE}/oreate/create/chat",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json={"type": "aiVideo", "docId": ""},
        timeout=30,
    )
    chat_res.raise_for_status()
    chat_data = chat_res.json()
    chat_id = chat_data.get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"Wan 2.6: no chatId in response")
    
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    
    request_body = {
        "jt": jt_token,
        "ua": _OREATE_UA,
        "js_env": "h5",
        "extra": {
            "email": email,
            "vip": "0",
            "reg_ts": int(time.time()),
            "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1",
            "bid": "19caf744b12438441a8a1c",
            "doc_name": "",
            "module_name": "gpt4o",
        },
        "clientType": "pc",
        "type": "chat",
        "chatType": "aiVideo",
        "chatTitle": "Unnamed Session",
        "focusId": chat_id,
        "chatId": chat_id,
        "from": "home",
        "messages": [{
            "role": "user",
            "content": prompt,
            "attachments": attachments,
        }],
        "isFirst": True,
    }
    
    sse_res = requests.post(
        f"{OREATE_BASE}/oreate/sse/stream",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json=request_body,
        stream=True,
        timeout=180,
    )
    sse_res.raise_for_status()
    
    video_url = None
    full_response = ""
    
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        
        lines = chunk.split("\n")
        for line in lines:
            if line.startswith("data: "):
                try:
                    data = _json.loads(line[6:])
                    if data.get("data", {}).get("videoUrl"):
                        video_url = data["data"]["videoUrl"]
                        break
                    if data.get("data", {}).get("url"):
                        url = data["data"]["url"]
                        if url and any(url.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv']):
                            video_url = url
                            break
                    if data.get("videoUrl"):
                        video_url = data["videoUrl"]
                        break
                except (_json.JSONDecodeError, KeyError):
                    pass
        
        if not video_url:
            url_match = re.search(r"(https?://[^\s\"'<>]+\.(mp4|mov|avi|webm|mkv)(\?[^\s\"'<>]*)?)", chunk, re.IGNORECASE)
            if url_match:
                video_url = url_match.group(1)
                break
        
        if video_url:
            break
    
    if not video_url:
        url_match = re.search(r"(https?://[^\s\"'<>]+\.(mp4|mov|avi|webm|mkv)(\?[^\s\"'<>]*)?)", full_response, re.IGNORECASE)
        if url_match:
            video_url = url_match.group(1)
    
    if not video_url:
        raise RuntimeError("Wan 2.6: no video URL found in response")
    
    return {
        "url": video_url,
        "download_url": video_url,
    }

# ─── Seedance 2 via Buzzy ─────────────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return ' '.join(self._parts)

def _strip_html(html):
    if not html:
        return ''
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        return html

def _extract_code_from_text(text):
    if not text:
        return None
    m = re.search(r'(\d{6})', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{5})', text)
    if m:
        return m.group(1)
    m = re.search(r'(?:verification\s+code|verification|code|otp)[^\d]{0,20}?(\d{4})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4})', text)
    return m.group(1) if m else None

def _buzzy_generate_temp_email():
    response = requests.get(f"{GUERRILLA_API}?f=get_email_address")
    data = response.json()
    if 'email_addr' not in data:
        raise Exception(f"Failed to generate temp email")
    sid_token = data['sid_token']
    local_part = data['email_addr'].split('@')[0]
    email = f"{local_part}@sharklasers.com"
    return email, sid_token

def _buzzy_generate_random_password():
    upper = random.choice(string.ascii_uppercase)
    lower = ''.join(random.choices(string.ascii_lowercase, k=3))
    nums = str(random.randint(1000, 9999))
    return upper + lower + nums

def _buzzy_send_verification_code(email):
    response = requests.post(
        'https://api.buzzy.now/api/v1/user/send-email-code',
        json={'email': email, 'type': 1},
        headers={'Content-Type': 'application/json'}
    )
    data = response.json()
    if data.get('code') != 200:
        raise Exception(f"Failed to send verification code")
    return True

def _buzzy_wait_for_code(sid_token, max_attempts=30, interval=4):
    current_seq = 0
    seen_ids = set()
    for attempt in range(max_attempts):
        response = requests.get(
            f"{GUERRILLA_API}?f=check_email&sid_token={sid_token}&seq={current_seq}"
        )
        data = response.json()
        if 'seq' in data:
            current_seq = data['seq']

        for mail in data.get('list', []):
            mail_id = mail.get('mail_id')
            if mail_id in seen_ids:
                continue
            seen_ids.add(mail_id)

            code = (
                _extract_code_from_text(mail.get('mail_subject', '')) or
                _extract_code_from_text(mail.get('mail_from', ''))
            )

            if not code:
                try:
                    full = requests.get(
                        f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={sid_token}"
                    ).json()
                    body = full.get('mail_body', '') or full.get('mail_excerpt', '')
                    code = (
                        _extract_code_from_text(_strip_html(body)) or
                        _extract_code_from_text(body)
                    )
                except Exception:
                    pass

            if code:
                return code

        time.sleep(interval)
    return None

def _buzzy_register_user(email, password, email_code):
    response = requests.post(
        'https://api.buzzy.now/api/v1/user/register',
        json={'email': email, 'password': password, 'emailCode': email_code},
        headers={'Content-Type': 'application/json'}
    )
    data = response.json()
    if data.get('code') == 200:
        return data['data']['token']
    raise Exception(f"Registration failed")

def _buzzy_create_video_project(token, prompt):
    response = requests.post(
        'https://api.buzzy.now/api/app/v1/project/create',
        json={
            'name': 'Untitled',
            'workflowType': 'SOTA',
            'instructionSegments': [{'type': 'text', 'content': prompt}],
            'imageUrls': [],
            'duration': 10,
            'aspectRatio': '16:9',
            'prompt': prompt
        },
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
    )
    data = response.json()
    if data.get('code') == 201:
        return data['data']['id']
    raise Exception(f"Failed to create video project")

def _buzzy_poll_for_video(token, project_id, interval=5):
    while True:
        response = requests.get(
            'https://api.buzzy.now/api/app/v1/project/list?pageNumber=1&pageSize=100',
            headers={
                'Authorization': f'Bearer {token}',
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        data = response.json()
        if data.get('code') != 200:
            time.sleep(interval)
            continue

        records = data.get('data', {}).get('records', [])
        target = next((p for p in records if p.get('id') == project_id), None)

        if target:
            status = target.get('status', 'unknown')

            if status == 'success':
                results = target.get('results', [])
                if results and len(results) > 0:
                    video_url = results[0].get('videoUrl')
                    if video_url:
                        return video_url

                video_urls = target.get('videoUrls', [])
                if video_urls and len(video_urls) > 0:
                    video_url = video_urls[0]
                    if video_url:
                        return video_url

            elif status == 'failed':
                raise Exception(f"Video generation failed")

        time.sleep(interval)

def run_seedance2_generation(prompt: str) -> dict:
    email, sid_token = _buzzy_generate_temp_email()
    password = _buzzy_generate_random_password()
    _buzzy_send_verification_code(email)

    code = _buzzy_wait_for_code(sid_token)
    if not code:
        raise Exception("Did not receive a verification code")

    token = _buzzy_register_user(email, password, code)
    project_id = _buzzy_create_video_project(token, prompt)
    video_url = _buzzy_poll_for_video(token, project_id)

    return {
        "url": video_url,
        "download_url": video_url,
    }

# ─── Dispatch ─────────────────────────────────────────────────────────────────

def run_generation(prompt: str, size: str, model: str, ref_images: list = None) -> dict:
    if model == "nanobanana_2":
        return run_oreate_generation(prompt, size, ref_images or [])
    if model == "gptimage_2":
        return run_gptimage2_generation(prompt, ref_images or [])
    if model == "seedance_2":
        return run_seedance2_generation(prompt)
    if model == "wan_2_6":
        return run_wan26_generation(prompt, size, ref_images or [])
    return run_synthesia_generation(prompt, size, model)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",         "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",     "emoji": "📧"},
    {"threshold": 15,  "label": "Verifying email",      "emoji": "✉️"},
    {"threshold": 30,  "label": "Setting up workspace", "emoji": "🛠️"},
    {"threshold": 65,  "label": "Generating media",     "emoji": "🎨"},
    {"threshold": 120, "label": "Rendering",            "emoji": "🎬"},
    {"threshold": 300, "label": "Finalizing",           "emoji": "✨"},
]

NB2_PROGRESS_STAGES = [
    {"threshold": 0,  "label": "Initializing",     "emoji": "⚙️"},
    {"threshold": 3,  "label": "Creating account", "emoji": "📧"},
    {"threshold": 10, "label": "Generating image", "emoji": "🎨"},
    {"threshold": 60, "label": "Finalizing",       "emoji": "✨"},
]

GPTIMAGE2_PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",      "emoji": "⚙️"},
    {"threshold": 3,   "label": "Creating account",  "emoji": "📧"},
    {"threshold": 8,   "label": "Setting up session","emoji": "🔐"},
    {"threshold": 15,  "label": "Uploading images",  "emoji": "📤"},
    {"threshold": 25,  "label": "Generating image",  "emoji": "🎨"},
    {"threshold": 60,  "label": "Finalizing",        "emoji": "✨"},
]

WAN26_PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",       "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",   "emoji": "📧"},
    {"threshold": 10,  "label": "Uploading images",   "emoji": "📤"},
    {"threshold": 20,  "label": "Generating video",   "emoji": "🎨"},
    {"threshold": 90,  "label": "Rendering",          "emoji": "🎬"},
    {"threshold": 105, "label": "Finalizing",         "emoji": "✨"},
]

SEEDANCE2_PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",       "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",   "emoji": "📧"},
    {"threshold": 15,  "label": "Verifying email",    "emoji": "✉️"},
    {"threshold": 30,  "label": "Registering user",   "emoji": "📝"},
    {"threshold": 60,  "label": "Generating video",   "emoji": "🎨"},
    {"threshold": 300, "label": "Rendering",          "emoji": "🎬"},
    {"threshold": 600, "label": "Finalizing",         "emoji": "✨"},
]

def get_stage(elapsed, stages):
    current = stages[0]
    for stage in stages:
        if elapsed >= stage["threshold"]:
            current = stage
    return current

def build_progress_embed(prompt, size_label, elapsed, model_label, model_value="", ref_count=0):
    if model_value == "nanobanana_2":
        stages = NB2_PROGRESS_STAGES
        estimated_total = 60
    elif model_value == "gptimage_2":
        stages = GPTIMAGE2_PROGRESS_STAGES
        estimated_total = 60
    elif model_value == "seedance_2":
        stages = SEEDANCE2_PROGRESS_STAGES
        estimated_total = 840
    elif model_value == "wan_2_6":
        stages = WAN26_PROGRESS_STAGES
        estimated_total = 120
    else:
        stages = PROGRESS_STAGES
        estimated_total = 180

    stage = get_stage(elapsed, stages)

    bar_length = 20
    progress = min(elapsed / estimated_total, 0.95)
    filled = int(bar_length * progress)
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title="🎨  Generating Your Media",
        color=PROGRESS_COLOR,
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    if ref_count > 0:
        embed.add_field(name="🖼️ Reference Images", value=f"`{ref_count} image(s)`", inline=True)
    embed.add_field(name="⏱️ Elapsed", value=f"`{format_duration(elapsed)}`", inline=True)
    embed.add_field(name=f"{stage['emoji']} Status", value=f"**{stage['label']}**", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress * 100)}%", inline=False)
    embed.set_footer(text=f"Powered by {model_label}  |  Please wait...")
    return embed

def build_success_embed(prompt, size_label, duration, model_label, model_value="", ref_images=None):
    embed = discord.Embed(
        title="✅  Media Generated Successfully!",
        color=SUCCESS_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="⏱️ Time Taken", value=f"`{format_duration(duration)}`", inline=True)
    
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (_, filename, _) in enumerate(ref_images[:4], 1):
            ref_text += f"📷 **Ref {idx}:** `{filename}`\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.set_footer(text=f"Powered by {model_label}")
    return embed

def build_error_embed(error_msg, prompt, size_label, model_label, model_value="", ref_images=None):
    embed = discord.Embed(
        title="❌  Generation Failed",
        color=ERROR_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (_, filename, _) in enumerate(ref_images[:4], 1):
            ref_text += f"📷 **Ref {idx}:** `{filename}`\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.add_field(name="⚠️ Error", value=f"```{str(error_msg)[:500]}```", inline=False)
    embed.set_footer(text="Please try again later")
    return embed

# ─── Discord commands ─────────────────────────────────────────────────────────

SIZE_LABELS = {
    "1080x1080": "1:1",
    "720x1280":  "9:16",
    "1280x720":  "16:9",
    "ai_decide": "AI decided",
}

size_choices = [
    app_commands.Choice(name="16:9",       value="1280x720"),
    app_commands.Choice(name="9:16",       value="720x1280"),
    app_commands.Choice(name="AI decided", value="ai_decide"),
]

NBP_AI_SIZES = ["1080x1080", "1280x720", "720x1280"]

model_choices = [
    app_commands.Choice(name="GPT Image 2",       value="gptimage_2"),
    app_commands.Choice(name="Nano Banana Pro",   value="nanobanana_pro"),
    app_commands.Choice(name="Nano Banana 2",     value="nanobanana_2"),
    app_commands.Choice(name="Sora 2",            value="sora_2"),
    app_commands.Choice(name="Veo 3.1",           value="fal_veo3"),
    app_commands.Choice(name="Veo 3.1 Fast",      value="fal_veo3_fast"),
    app_commands.Choice(name="Seedance 2",        value="seedance_2"),
    app_commands.Choice(name="Wan 2.6",           value="wan_2_6"),
]

MODEL_LABELS = {
    "gptimage_2":     "GPT Image 2",
    "nanobanana_pro": "Nano Banana Pro",
    "nanobanana_2":   "Nano Banana 2",
    "sora_2":         "Sora 2",
    "fal_veo3":       "Veo 3.1",
    "fal_veo3_fast":  "Veo 3.1 Fast",
    "seedance_2":     "Seedance 2",
    "wan_2_6":        "Wan 2.6",
}

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online! Logged in as: {client.user}")
    print(f"🚀 Commands available in: Servers and DMs")
    print(f"🌐 Web server running on port {int(os.environ.get('PORT', 8080))}")
    
    # Get application owner info
    try:
        app_info = await client.application_info()
        print(f"👑 Application Owner: {app_info.owner} (ID: {app_info.owner.id})")
    except:
        print("👑 Could not fetch application owner info")

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="generate", description="Generate AI media")
@app_commands.describe(
    prompt="What the media should show",
    model="AI model to use (default: Nano Banana Pro)",
    size="Video resolution",
    ref1="Reference image 1 (GPT Image 2 / Nano Banana 2 / Wan 2.6 only)",
    ref2="Reference image 2",
    ref3="Reference image 3",
    ref4="Reference image 4",
    ref5="Reference image 5 (Nano Banana 2 / Wan 2.6 only)",
    ref6="Reference image 6 (Nano Banana 2 / Wan 2.6 only)",
    ref7="Reference image 7 (Nano Banana 2 / Wan 2.6 only)",
    ref8="Reference image 8 (Nano Banana 2 / Wan 2.6 only)",
    ref9="Reference image 9 (Nano Banana 2 / Wan 2.6 only)",
)
@app_commands.choices(size=size_choices, model=model_choices)
async def generate(
    interaction: discord.Interaction,
    prompt: str,
    model: app_commands.Choice[str] = None,
    size: app_commands.Choice[str] = None,
    ref1: discord.Attachment = None,
    ref2: discord.Attachment = None,
    ref3: discord.Attachment = None,
    ref4: discord.Attachment = None,
    ref5: discord.Attachment = None,
    ref6: discord.Attachment = None,
    ref7: discord.Attachment = None,
    ref8: discord.Attachment = None,
    ref9: discord.Attachment = None,
):
    if await is_user_banned(interaction):
        return
    if await is_user_timeout(interaction):
        return
    
    model_value = model.value if model else "nanobanana_pro"
    model_label = MODEL_LABELS.get(model_value, model_value)

    raw_size = size.value if size else None

    if model_value == "nanobanana_2":
        size_value = raw_size or "ai_decide"
        size_label = "AI decided"
    elif model_value == "gptimage_2":
        size_value = "ai_decide"
        size_label = "AI decided"
    elif model_value == "seedance_2":
        size_value = "1280x720"
        size_label = "16:9"
    elif model_value == "wan_2_6":
        size_value = "1280x720"
        size_label = "16:9"
    elif raw_size == "ai_decide" or raw_size is None:
        if model_value in VIDEO_MODELS:
            size_value = random.choice(["1280x720", "720x1280"])
        else:
            size_value = random.choice(NBP_AI_SIZES)
        size_label = "AI decided"
    else:
        size_value = raw_size
        size_label = SIZE_LABELS.get(size_value, size_value)

    actual_prompt = prompt

    ref_images = []
    if model_value in ["gptimage_2", "nanobanana_2", "wan_2_6"]:
        raw_refs = [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]
        bad_refs = []
        
        max_refs = 4 if model_value == "gptimage_2" else 9
        
        for attachment in raw_refs[:max_refs]:
            if attachment is None:
                continue
            fname = attachment.filename
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if not ext or f".{ext}" not in VALID_IMAGE_EXTENSIONS:
                bad_refs.append(fname)
            else:
                ref_images.append((attachment, fname, ext))

        if bad_refs:
            await interaction.response.send_message(
                f"⚠️ Invalid images: `{'`, `'.join(bad_refs)}`",
                ephemeral=True,
            )
            return

        downloaded = []
        for attachment_obj, fname, ext in ref_images:
            try:
                img_bytes = await attachment_obj.read()
                downloaded.append((img_bytes, fname, ext))
            except Exception as e:
                print(f"Failed to download {fname}: {e}")
        ref_images = downloaded
    else:
        if any(r is not None for r in [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]):
            await interaction.response.send_message(
                "⚠️ Reference images only work with **GPT Image 2**, **Nano Banana 2**, or **Wan 2.6**.",
                ephemeral=True,
            )
            return

    start_embed = build_progress_embed(prompt, size_label, 0, model_label, model_value, len(ref_images))
    await interaction.response.send_message(embed=start_embed)
    status_msg = await interaction.original_response()

    start_time = time.time()
    generation_done = asyncio.Event()
    generation_result = {"data": None, "error": None}

    async def run_gen():
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, run_generation, actual_prompt, size_value, model_value, ref_images
            )
            generation_result["data"] = result
        except Exception as exc:
            generation_result["error"] = str(exc)
        finally:
            generation_done.set()

    async def update_timer():
        while not generation_done.is_set():
            await asyncio.sleep(3)
            if generation_done.is_set():
                break
            elapsed = time.time() - start_time
            try:
                progress_embed = build_progress_embed(prompt, size_label, elapsed, model_label, model_value, len(ref_images))
                await status_msg.edit(embed=progress_embed)
            except Exception:
                pass

    asyncio.create_task(run_gen())
    timer_task = asyncio.create_task(update_timer())

    await generation_done.wait()
    timer_task.cancel()
    try:
        await timer_task
    except asyncio.CancelledError:
        pass

    total_time = time.time() - start_time

    if generation_result["error"]:
        error_embed = build_error_embed(generation_result["error"], prompt, size_label, model_label, model_value, ref_images)
        await status_msg.edit(embed=error_embed)
        return

    result = generation_result["data"]
    success_embed = build_success_embed(prompt, size_label, total_time, model_label, model_value, ref_images)

    media_file = None
    download_url = result.get("download_url") or result.get("url")
    if download_url:
        try:
            response = download_session.get(download_url, timeout=60)
            response.raise_for_status()
            media_bytes = response.content
            
            is_image = model_value not in VIDEO_MODELS or model_value in ["gptimage_2", "nanobanana_2"]
            ext = "png" if is_image else "mp4"
            filename = f"generated_media.{ext}"
            
            if not is_image and len(media_bytes) > 25 * 1024 * 1024:
                success_embed.add_field(
                    name="📥 Download",
                    value=f"[Click to download video]({download_url})",
                    inline=False,
                )
            else:
                media_file = discord.File(io.BytesIO(media_bytes), filename=filename)
                if is_image:
                    success_embed.set_image(url=f"attachment://{filename}")
                else:
                    success_embed.add_field(
                        name="📥 Download",
                        value=f"[Click to download video]({download_url})",
                        inline=False,
                    )
        except Exception as dl_err:
            print(f"Download error: {dl_err}")
            if download_url:
                success_embed.add_field(
                    name="📥 Download",
                    value=f"[Click to download]({download_url})",
                    inline=False,
                )

    if media_file:
        await status_msg.edit(embed=success_embed, attachments=[media_file])
    else:
        await status_msg.edit(embed=success_embed)

    await interaction.followup.send(
        f"{interaction.user.mention} Media ready! Took **{format_duration(total_time)}**."
    )

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="ping", description="Check if bot is alive")
async def ping_cmd(interaction: discord.Interaction):
    if await is_user_banned(interaction):
        return
    if await is_user_timeout(interaction):
        return
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{round(client.latency * 1000)}ms`\nStatus: ✅ Online",
        color=SUCCESS_COLOR,
    )
    await interaction.response.send_message(embed=embed)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="sizes", description="View all available media sizes")
async def sizes_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📏  Available Sizes",
        description="Use these with `/generate` to pick your resolution.",
        color=INFO_COLOR,
    )
    landscape, portrait, square = [], [], []
    for size in VIDEO_SIZES:
        w, h = map(int, size.split("x"))
        entry = f"`{size}`"
        if w == h:
            square.append(entry)
        elif w > h:
            landscape.append(entry)
        else:
            portrait.append(entry)
    if landscape:
        embed.add_field(name="🌅 Landscape", value="\n".join(landscape), inline=False)
    if portrait:
        embed.add_field(name="📱 Portrait", value="\n".join(portrait), inline=False)
    if square:
        embed.add_field(name="⬛ Square", value="\n".join(square), inline=False)
    await interaction.response.send_message(embed=embed)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="models", description="View all available AI models")
async def models_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🧠  Available Models",
        color=INFO_COLOR,
    )
    embed.add_field(
        name="Image models",
        value=(
            "`GPT Image 2` — OpenAI GPT Image 2 with up to 4 reference images\n"
            "`Nano Banana Pro` — fast AI image generation\n"
            "`Nano Banana 2` — image generation with up to 9 reference images"
        ),
        inline=False,
    )
    embed.add_field(
        name="Video models (with audio)",
        value=(
            "`Sora 2` — OpenAI Sora v2\n"
            "`Veo 3.1` — Google Veo 3.1\n"
            "`Veo 3.1 Fast` — Google Veo 3.1 (faster)\n"
            "`Seedance 2` — Seedance v2\n"
            "`Wan 2.6` — Wan 2.6 video generation with reference images"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed)

# ─── Owner Info Command ──────────────────────────────────────────────────────

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="owner", description="Show bot owner information")
async def owner_cmd(interaction: discord.Interaction):
    try:
        app_info = await client.application_info()
        owner = app_info.owner
        embed = discord.Embed(
            title="👑 Bot Owner",
            description=f"**Name:** {owner.name}\n**ID:** `{owner.id}`",
            color=BRAND_COLOR
        )
        embed.set_thumbnail(url=owner.display_avatar.url)
        await interaction.response.send_message(embed=embed)
    except:
        embed = discord.Embed(
            title="👑 Bot Owner",
            description=f"**Owner ID:** `Application Owner`",
            color=BRAND_COLOR
        )
        await interaction.response.send_message(embed=embed)

# ─── تشغيل البوت ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    keep_alive()
    
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    
    print("🚀 Starting Discord Bot on Render...")
    print("📡 Bot will run 24/7!")
    client.run(TOKEN)
