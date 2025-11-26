import os
import re
import sys
import time
import random
import asyncio
import aiohttp
import json
import discord
from pathlib import Path
from datetime import timedelta
from discord.ext import commands
from core.globals import HehBot, uid_system, UID_1, instances, active_bots, hosted_tokens, token_instance_map
from requestcord import HeaderGenerator

class HostCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        sys.path.append(str(Path(__file__).parent.parent))
        from main import colors, log_action
        self.colors = colors
        self.log = log_action
        self.red_color = "\u001b[1;31m"
        self.yellow_color = "\u001b[1;33m"
        self.green_color = "\u001b[1;32m"

        with open('input/developers.json', 'r') as f:
            data = json.load(f)
        self.host_whitelist = set(data.get('host_whitelist', []))
        self.host_blacklist = set(data.get('host_blacklist', []))
        self.active_tasks = {}
        self.active_bots = active_bots
        self.hosted_tokens = hosted_tokens
        self.token_instance_map = token_instance_map

        self.xvx_cogs = [cog for cog in self.bot.xvx_cogs if cog != "cogs.HostCog"]

        for cmd in self.get_commands():
            cmd.category = "hosting"

    def get_logo(self):
        return ""  # Placeholder

    async def validate_token(self, token: str):
        """Validate a Discord token"""
        headers = HeaderGenerator().generate_headers(token=token)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://discord.com/api/v9/users/@me", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['username'], data['id']
                    return None, None
        except Exception:
            return None, None

    async def start_instance_bot(self, instance_name: str, token: str):
        """Start a bot instance with full tracking"""
        from main import setup_core_features

        intents = discord.Intents.all()
        bot = HehBot(
            command_prefix=lambda bot, msg: bot.custom_prefix,
            self_bot=True,
            intents=intents
        )

        bot.token = token
        bot.custom_prefix = self.bot.custom_prefix
        bot.log_action = self.log
        bot.host_cog = self

        self.hosted_tokens.setdefault(instance_name, []).append(token)
        self.token_instance_map[token] = instance_name
        self.active_bots.setdefault(instance_name, []).append(bot)

        setup_core_features(bot, self.log)

        @bot.event
        async def on_ready():
            try:
                await bot.change_presence(activity=discord.Streaming(
                    name=">.< hosted by saith",
                    url="https://twitch.tv/discord"
                ))
                self.log(f"Hosted instance {instance_name} started as {bot.user.name}")
            except Exception as e:
                self.log(f"Presence error: {str(e)}")
                bot.user.name = "Hosted Instance"

        for cog in self.xvx_cogs:
            try:
                bot.load_extension(cog)
            except Exception as e:
                self.log(f"Failed to load cog {cog} for {instance_name}: {str(e)}")

        task = asyncio.create_task(self._run_bot_instance(bot, token))
        self.active_tasks[token] = task

        return True

    async def _run_bot_instance(self, bot, token):
        """Wrapper for safe bot execution"""
        try:
            await bot.start(token, bot=False)
        except Exception as e:
            self.log(f"Bot instance crashed: {str(e)}")
        finally:
            if not bot.is_closed():
                await bot.close()
            if token in self.token_instance_map:
                instance = self.token_instance_map[token]
                self._cleanup_instance(instance, token)

    async def _stop_instance(self, name: str) -> int:
        """Internal helper to stop an instance and return terminated bot count"""
        if name not in instances:
            return 0

        terminated = 0
        instance_tokens = hosted_tokens.get(name, []).copy()

        for token in instance_tokens:
            if task := self.active_tasks.pop(token, None):
                task.cancel()
                terminated += 1
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        bots = active_bots.pop(name, [])
        for bot in bots:
            if not bot.is_closed():
                try:
                    await bot.close()
                    terminated += 1
                except Exception as e:
                    self.log(f"Force close failed: {str(e)}")

        for token in instance_tokens:
            if token in token_instance_map:
                del token_instance_map[token]

        hosted_tokens.pop(name, None)
        instances.pop(name, None)

        return terminated

    def _cleanup_instance(self, instance_name: str, token: str):
        if instance_name in hosted_tokens:
            if token in hosted_tokens[instance_name]:
                hosted_tokens[instance_name].remove(token)
                if not hosted_tokens[instance_name]:
                    instances.pop(instance_name, None)
                    hosted_tokens.pop(instance_name, None)

        token_instance_map.pop(token, None)

        if instance_name in active_bots:
            active_bots[instance_name] = [
                bot for bot in active_bots[instance_name] if getattr(bot, 'token', None) != token
            ]
            if not active_bots[instance_name]:
                active_bots.pop(instance_name, None)

        if token in self.active_tasks:
            task = self.active_tasks.pop(token)
            if not task.done():
                task.cancel()

    @commands.group(invoke_without_command=True)
    async def host(self, ctx, owner_token: str = None):
        """Host a token or show help"""
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        if owner_token is None:
            # Show help
            main = self.colors['main']
            sub = self.colors['sub']
            reset = self.colors['reset']

            content = f"""> ```ansi
> {main}─── {sub}HOST COMMANDS{main} ───────────────────────────
> {sub}Usage:{reset}
> {main}• {sub}host {main}<token>{reset} - Host a new instance
> {main}• {sub}host unhost {main}<name>{reset} - Stop instance
> {main}• {sub}host list{reset} - Show all instances```"""
            await ctx.send(content)
            return

        # Host the token
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        # Check if token already hosted
        if owner_token in token_instance_map:
            existing_uid = None
            for uid, data in uid_system.uids.items():
                if isinstance(data, dict) and data.get('token') == owner_token:
                    existing_uid = uid
                    break
            if existing_uid:
                existing_data = uid_system.uids[existing_uid]
                content = f"""> ```ansi
> {self.yellow_color}⚠ This account is already hosted and running
> {sub}UID: {existing_uid} | Account: {existing_data.get('username', 'Unknown')} ({existing_data.get('user_id', 'Unknown')})
> {sub}Token is valid. Use host unhost first if you want to replace it```"""
                await ctx.send(content)
                return

        await ctx.send(f"> ```ansi\n> {self.yellow_color}⏳ Validating token...```")

        username, user_id = await self.validate_token(owner_token)
        if not username:
            content = f"""> ```ansi
> {self.red_color}✗ Invalid token: invalid token (401 Unauthorized)```"""
            await ctx.send(content)
            return

        # Find next UID
        uid_num = None
        for i in range(1, 1000):
            if str(i) not in uid_system.uids:
                uid_num = i
                break
        if uid_num is None:
            content = f"""> ```ansi
> {self.red_color}✗ No available UIDs```"""
            await ctx.send(content)
            return

        # Auto-generate name
        name = f"instance_{uid_num}"

        instances[name] = {
            'tokens': [owner_token],
            'restrictions': [],
            'owner_id': user_id,
            'owner_name': username,
            'active': True,
            'created_at': time.time()
        }

        hosted_tokens[name] = [owner_token]
        token_instance_map[owner_token] = name

        uid_system.uids[str(uid_num)] = {
            'token': owner_token,
            'username': username,
            'user_id': user_id,
            'created_at': time.time()
        }
        uid_system.save_uids()

        asyncio.create_task(self.start_instance_bot(name, owner_token))

        content = f"""> ```ansi
> {self.green_color}✓ Hosted new user with UID: {uid_num}```"""
        await ctx.send(content)

    @host.command()
    async def unhost(self, ctx, name: str):
        """Stop an instance"""
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        logo = self.get_logo()

        if name not in instances:
            content = f"""> ```ansi
> {self.red_color}✗ Instance not found```"""
            await ctx.send(content)
            return

        terminated = await self._stop_instance(name)

        content = f"""> ```ansi
> {self.green_color}✓ Instance stopped: {name} ({terminated} bots terminated)```"""
        await ctx.send(content)

    @host.command()
    async def list(self, ctx):
        """List all hosted instances"""
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        current_count = len(uid_system.uids)

        msg = f"> ```ansi\n> {sub}\033[1m\033[4mHosted Accounts ({current_count}/5)\033[0m{reset}\n"

        if not uid_system.uids:
            msg += "> No hosted accounts\n> ```"
            await ctx.send(msg)
            return

        for uid_str, uid_data in uid_system.uids.items():
            if not isinstance(uid_data, dict):
                continue
            username = uid_data.get('username', 'Unknown')
            user_id = uid_data.get('user_id', 'Unknown')
            token = uid_data.get('token', '')

            # Find instance
            instance_name = token_instance_map.get(token)
            instance_data = instances.get(instance_name, {}) if instance_name else {}

            # Status
            status = "✅ Online" if instance_name and active_bots.get(instance_name) else "❌ Offline"

            # Guilds
            guilds = 0
            prefix = "-"
            if instance_name and active_bots.get(instance_name):
                bot = active_bots[instance_name][0] if active_bots[instance_name] else None
                if bot:
                    guilds = len(bot.guilds)
                    prefix = getattr(bot, 'custom_prefix', '-')

            # Hosted time
            hosted_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(uid_data.get('created_at', time.time())))

            msg += f"> {sub}UID: {main}{uid_str}\n"
            msg += f"> {sub}ID: {main}{user_id}\n"
            msg += f"> {sub}Name: {main}{username}\n"
            msg += f"> {sub}Prefix: {main}{prefix}\n"
            msg += f"> {sub}Guilds: {main}{guilds}\n"
            msg += f"> {sub}Status: {main}{status}\n"
            msg += f"> {sub}Hosted: {main}{hosted_time}\n"
            msg += f"> {sub}────────────────────\n"

        msg += f"> Page {reset}\033[1m{sub}1/1{reset}\n> ```"
        await ctx.send(msg)

def setup(bot):
    bot.add_cog(HostCog(bot))