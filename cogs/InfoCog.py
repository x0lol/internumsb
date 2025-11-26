import os
import sys
import time
import json
import discord
import random
import aiohttp
import psutil
import platform
from pathlib import Path
from typing import Union
from discord.ext import commands
from requestcord import HeaderGenerator
from datetime import datetime, timedelta

class InfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.token = bot.token
        self.start_time = time.time()
        from main import colors
        self.colors = colors
        self.HeaderGen = HeaderGenerator()
        self.afk_users = {}
        self.afk_cooldowns = {}
        self.webhooks = {}
        self.main_bot_id = None
        self.prefix = "> "

        for cmd in self.get_commands():
            cmd.category = "info"

    def get_logo(self):
        return ""

    def read_tokens(self):
        try:
            token_file = Path("input/tokens.txt")
            if not token_file.exists():
                return []
            with token_file.open("r") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception:
            return []
            
    def get_token_source(self):
        """Integrated token source from MultiCog"""
        host_cog = getattr(self.bot, 'host_cog', None)
        
        if host_cog:
            instance_name = host_cog.token_instance_map.get(self.bot.token)
            if instance_name and instance_name in host_cog.hosted_tokens:
                return {
                    'source': 'hosted',
                    'tokens': host_cog.hosted_tokens[instance_name],
                    'instance': instance_name
                }
        
        global_host_cog = self.bot.get_cog('HostCog')
        if global_host_cog:
            instance_name = global_host_cog.token_instance_map.get(self.bot.token)
            if instance_name and instance_name in global_host_cog.hosted_tokens:
                return {
                    'source': 'hosted',
                    'tokens': global_host_cog.hosted_tokens[instance_name],
                    'instance': instance_name
                }
        
        return {
            'source': 'global',
            'tokens': self.read_tokens(),
            'instance': None
        }

    def load_webhooks(self):
        """Load webhooks configuration"""
        if not self.main_bot_id:
            return
            
        path = f"data/webhooks_{self.main_bot_id}.json"
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.webhooks = json.load(f)
            else:
                self.webhooks = {}
        except Exception as e:
            print(f"[InfoCog] ERROR loading webhooks: {e}")
            self.webhooks = {}

    async def send_afk_webhook(self, afk_user, mentioner, message):
        """Send AFK ping notification to webhook"""
        if "afk_mentions" not in self.webhooks:
            return
            
        webhook_url = self.webhooks["afk_mentions"]["url"]
        if not webhook_url:
            return
            
        reason, afk_start = self.afk_users[afk_user.id]
        duration = self._format_afk_time(datetime.utcnow() - afk_start)
        
        embed = discord.Embed(
            title="AFK Mention Notification",
            color=0x3498db,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="AFK User", value=f"{afk_user} ({afk_user.id})", inline=False)
        embed.add_field(name="Mentioned By", value=f"{mentioner} ({mentioner.id})", inline=False)
        embed.add_field(name="Channel", value=f"<#{message.channel.id}>", inline=False)
        embed.add_field(name="Server", value=f"{message.guild.name if message.guild else 'DM'}", inline=False)
        embed.add_field(name="Duration", value=duration, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Message Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
        
        if message.content:
            content_preview = message.content[:500] + ("..." if len(message.content) > 500 else "")
            embed.add_field(name="Message Preview", value=content_preview, inline=False)
        
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    webhook_url,
                    json={
                        "embeds": [embed.to_dict()],
                        "content": f"🔔 You were mentioned while AFK!"
                    }
                )
        except Exception as e:
            print(f"[InfoCog] ERROR sending AFK webhook: {e}")

    @commands.command()
    async def serverinfo(self, ctx):
        """Show server details
        Usage: serverinfo"""
        guild = ctx.guild
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        if ctx.guild is None:
            content = f"""> ```ansi
> {main}This command can only be used in servers.{reset}```"""
            return await ctx.send(content)
        
        content = f"""> ```ansi
> {main}─── {sub}SERVER INFO{main} ───
> {main}Name:{reset} {sub}{guild.name}{reset}
> {main}ID:{reset} {sub}{guild.id}{reset}
> {main}Owner:{reset} {sub}{guild.owner}{reset}
> {main}Members:{reset} {sub}{guild.member_count}{reset}
> {main}Channels:{reset} {sub}{len(guild.channels)}{reset}
> {main}Roles:{reset} {sub}{len(guild.roles)}{reset}
> {main}Created:{reset} {sub}{guild.created_at.strftime('%Y-%m-%d %H:%M')}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def userinfo(self, ctx, member: discord.User = None):
        """Show user information
        Usage: userinfo [@user]"""
        member = member or ctx.author
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        headers = self.HeaderGen.generate_headers(token=self.token)
    
        banner_url = "None"
        nitro_type = "No"
        mutual_servers = []
        mutual_friend_count = 0
    
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://discord.com/api/v9/users/{member.id}/profile", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    banner = data.get("user", {}).get("banner")
                    banner_color = data.get("user", {}).get("banner_color")
    
                    if banner:
                        banner_url = f"https://cdn.discordapp.com/banners/{member.id}/{banner}.{'gif' if banner.startswith('a_') else 'png'}?size=1024"
                    elif banner_color:
                        banner_url = f"Solid Color: {banner_color}"
    
                    premium_type = data.get("premium_type", 0)
                    if premium_type:
                        nitro_type = "Yes"
    
            async with session.get(f"https://discord.com/api/v9/users/{member.id}/relationships", headers=headers) as resp:
                if resp.status == 200:
                    relationships = await resp.json()
                    mutual_friend_count = len(relationships)
    

            for guild in self.bot.guilds:
                if guild.get_member(member.id):
                    mutual_servers.append(guild.name)
            mutual_servers_text = ", ".join(mutual_servers) if mutual_servers else "None"
    
        content = f"""> ```ansi
> {main}─── {sub}USER INFO{main} ───
> {main}Name:{reset} {sub}{member.display_name}{reset}
> {main}ID:{reset} {sub}{member.id}{reset}
> {main}Created:{reset} {sub}{member.created_at.strftime('%Y-%m-%d %H:%M')}{reset}
> {main}Avatar:{reset} {sub}{member.avatar_url}{reset}
> {main}Banner:{reset} {sub}{banner_url}{reset}
> {main}Bot:{reset} {sub}{'Yes' if member.bot else 'No'}{reset}
> {main}Nitro:{reset} {sub}{nitro_type}{reset}
> {main}Mutual Friends:{reset} {sub}{mutual_friend_count}{reset}
> {main}Mutual Servers:{reset} {sub}{mutual_servers_text}{reset}```"""
    
        await ctx.send(content)

    @commands.command()
    async def avatar(self, ctx, member: discord.User = None):
        """Show user avatar
        Usage: avatar [@user]"""
        member = member or ctx.author
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        content = f"""> ```ansi
> {main}─── {sub}AVATAR{main} ───
> {main}User:{reset} {sub}{member.display_name}{reset}
> {main}Avatar URL:{reset} {sub}{member.avatar_url}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def translate(self, ctx, *, text: str):
        """Translate text to English using Google Translate
        Usage: translate <text>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={text}"
                async with session.get(url) as response:
                    data = await response.json()
                    translated = data[0][0][0]
    
            content = f"""> ```ansi

> {main}─── {sub}TRANSLATION{main} ───
> {main}Original:{reset} {sub}{text}{reset}
> {main}Translated (en):{reset} {sub}{translated}{reset}```"""
            await ctx.send(content)
            
        except Exception as e:
            content = f"""> ```ansi

> {main}─── {sub}TRANSLATION FAILED{main} ───
> {sub}Error:{reset} {main}{str(e)}{reset}```"""
            await ctx.send(content)

    def get_uptime(self):
        seconds = int(time.time() - self.start_time)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m {seconds}s"

    @commands.command()
    async def uptime(self, ctx):
        """Show bot uptime
        Usage: uptime"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        uptime_str = self.get_uptime()
        content = f"""> ```ansi
> {main}─── {sub}UPTIME{main} ───
> {main}Uptime:{reset} {sub}{uptime_str}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def ping(self, ctx):
        """Show bot latency
        Usage: ping"""
        latency = round(self.bot.latency * 1000)
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        content = f"""> ```ansi
> {main}─── {sub}PING{main} ───
> {main}Latency:{reset} {sub}{latency}ms{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def time(self, ctx):
        """Show current time in UTC
        Usage: time"""
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        content = f"""> ```ansi
> {main}─── {sub}TIME{main} ───
> {main}UTC Time:{reset} {sub}{now}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def stats(self, ctx):
        """Show system stats
        Usage: stats"""
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        plat = platform.system()
        pyver = platform.python_version()
        botver = discord.__version__

        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        content = f"""> ```ansi
> {main}─── {sub}SYSTEM STATS{main} ───
> {main}Platform:{reset} {sub}{plat}{reset}
> {main}CPU Usage:{reset} {sub}{cpu}%{reset}
> {main}Memory Usage:{reset} {sub}{mem}%{reset}
> {main}Python:{reset} {sub}{pyver}{reset}
> {main}discord.py:{reset} {sub}{botver}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def botinfo(self, ctx):
        """Show info about the bot
        Usage: botinfo"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        logo = self.get_logo()
    
        total_lines = 0
        for root, _, files in os.walk('.'):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            total_lines += len(f.readlines())
                    except Exception:
                        pass
    
        token_info = self.get_token_source()
        source_type = token_info['source']
        tokens = token_info['tokens']
        instance = token_info['instance']
        
        if source_type == 'hosted':
            token_source = f"Hosted Instance: {instance}"
            available_tokens = len(tokens) if tokens else 0
        else:
            token_source = "Global Token Pool"
            available_tokens = len(tokens) if tokens else 0
    
        content = f"""> ```ansi
> {main}─── {sub}BOT INFO{main} ───
> {main}Name:{reset} {sub}{self.bot.user.name}{reset}
> {main}ID:{reset} {sub}{self.bot.user.id}{reset}
> {main}Servers:{reset} {sub}{len(self.bot.guilds)}{reset}
> {main}Commands Loaded:{reset} {sub}{len(self.bot.commands)}{reset}
> {main}Total Lines:{reset} {sub}{total_lines}{reset}
> {main}Token Source:{reset} {sub}{token_source}{reset}
> {main}Available Tokens:{reset} {sub}{available_tokens}```"""
        await ctx.send(content)

    @commands.command()
    async def joinedat(self, ctx, member: discord.Member = None):
        """Show when a member joined this server
        Usage: joinedat [@user]"""
        member = member or ctx.author
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
    
        content = f"""> ```ansi
> {main}─── {sub}JOINED AT{main} ───
> {main}User:{reset} {sub}{member.display_name}{reset}
> {main}Joined:{reset} {sub}{member.joined_at.strftime('%Y-%m-%d %H:%M')}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def createdat(self, ctx, member: discord.User = None):
        """Show when a user created their Discord account
        Usage: createdat [@user]"""
        member = member or ctx.author
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        content = f"""> ```ansi
> {main}─── {sub}ACCOUNT CREATED{main} ───
> {main}User:{reset} {sub}{member.display_name}{reset}
> {main}Created At:{reset} {sub}{member.created_at.strftime('%Y-%m-%d %H:%M')}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def roleinfo(self, ctx, *, role: discord.Role = None):
        """Show info about a role
        Usage: roleinfo <role name>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
    
        if role is None:
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}ROLE INFO ERROR{main} ───
> {main}Please specify a role name.{reset}```""")
    
        content = f"""> ```ansi
> {main}─── {sub}ROLE INFO{main} ───
> {main}Name:{reset} {sub}{role.name}{reset}
> {main}ID:{reset} {sub}{role.id}{reset}
> {main}Color:{reset} {sub}{role.color}{reset}
> {main}Position:{reset} {sub}{role.position}{reset}
> {main}Mentionable:{reset} {sub}{'Yes' if role.mentionable else 'No'}{reset}
> {main}Created:{reset} {sub}{role.created_at.strftime('%Y-%m-%d %H:%M')}{reset}```"""
        await ctx.send(content)

    @commands.command()
    async def channelinfo(self, ctx, channel: discord.TextChannel = None):
        """Show info about a channel
        Usage: channelinfo [#channel]"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
    
        channel = channel or ctx.channel
    
        content = f"""> ```ansi
> {main}─── {sub}CHANNEL INFO{main} ───
> {main}Name:{reset} {sub}{channel.name}{reset}
> {main}ID:{reset} {sub}{channel.id}{reset}
> {main}Topic:{reset} {sub}{channel.topic or 'None'}{reset}
> {main}NSFW:{reset} {sub}{'Yes' if channel.is_nsfw() else 'No'}{reset}
> {main}Category:{reset} {sub}{channel.category.name if channel.category else 'None'}{reset}
> {main}Created:{reset} {sub}{channel.created_at.strftime('%Y-%m-%d %H:%M')}{reset}```"""
        await ctx.send(content)
    
    @commands.command()
    async def serveremojis(self, ctx):
        """List server emojis
        Usage: serveremojis"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
        
        emojis = list(ctx.guild.emojis)
        chunk_size = 10
        emoji_chunks = [emojis[i:i+chunk_size] for i in range(0, len(emojis), chunk_size)]
    
        for index, chunk in enumerate(emoji_chunks):
            emoji_list = []
            for i, emoji in enumerate(chunk):
                status = "Animated" if emoji.animated else "Static"
                line = f"{main}• {sub}{emoji.name} {main}({sub}{status}{main}) {sub}{str(emoji)}"
                emoji_list.append("    " + line)
        
            content = f"""> ```ansi
> {main}─── {sub}SERVER EMOJIS{main} ───
> {main}Total Emojis: {sub}{len(emojis)}
> {main}Page {index+1}/{len(emoji_chunks)}:{reset}
> """ + '\n'.join(emoji_list) + "```"
            await ctx.send(content)

    
    @commands.command()
    async def serverroles(self, ctx):
        """List server roles
        Usage: serverroles"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
        
        roles = sorted(ctx.guild.roles[1:], key=lambda r: r.position, reverse=True)
        chunk_size = 10
        role_chunks = [roles[i:i+chunk_size] for i in range(0, len(roles), chunk_size)]
        
        for index, chunk in enumerate(role_chunks):
            role_list = []
            for i, role in enumerate(chunk):
                member_count = sum(1 for member in ctx.guild.members if role in member.roles)
                line = f"{main}• {sub}{role.name} {main}({sub}{member_count} members{main})"
                if i == 0:
                    role_list.append(line)
                else:
                    role_list.append("    " + line)
            
            content = f"""> ```ansi
> {main}─── {sub}SERVER ROLES{main} ───
> {main}Total Roles: {sub}{len(roles)}
> {main}Page {index+1}/{len(role_chunks)}:{reset}
>     """ + '\n'.join(role_list) + "```"
            await ctx.send(content)
    
    @commands.command()
    async def permissions(self, ctx, target: Union[discord.Member, discord.Role] = None):
        """Show permissions for a user or role
        Usage: permissions [@user/role]"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
    
        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
    
        target = target or ctx.author
        perms = target.permissions_in(ctx.channel) if isinstance(target, discord.Member) else target.permissions_in(ctx.channel)
        perm_list = [perm[0].replace("_", " ").title() for perm in perms if perm[1]]
    
        chunk_size = 15
        perm_chunks = [perm_list[i:i+chunk_size] for i in range(0, len(perm_list), chunk_size)]
    
        for index, chunk in enumerate(perm_chunks):
            lines = []
            for perm in chunk:
                line = f"{main}• {sub}{perm}"
                lines.append("    " + line)
    
            content = f"""> ```ansi
> {main}─── {sub}PERMISSIONS{main} ───
> {main}Target: {sub}{target.name}
> {main}Type: {sub}{'User' if isinstance(target, discord.Member) else 'Role'}
> {main}Page {index+1}/{len(perm_chunks)}:{reset}
> """ + '\n'.join(lines) + "```"
            await ctx.send(content)

    
    @commands.command()
    async def platform(self, ctx, member: discord.Member = None):
        """Show user's active platforms
        Usage: platform [@user]"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}This command can only be used in servers.{reset}```""")
        
        member = member or ctx.author
        platforms = []
        
        if member.desktop_status != discord.Status.offline:
            platforms.append("Desktop")
        if member.mobile_status != discord.Status.offline:
            platforms.append("Mobile")
        if member.web_status != discord.Status.offline:
            platforms.append("Web")
        
        platform_text = ', '.join(platforms) if platforms else "Unknown"
        
        content = f"""> ```ansi
> {main}─── {sub}ACTIVE PLATFORMS{main} ───
> {main}User: {sub}{member.display_name}
> {main}Platforms: {sub}{platform_text}```"""
        await ctx.send(content)

    @commands.command()
    async def afk(self, ctx, *, reason: str = "No reason provided"):
        """Set your AFK status
        Usage: afk [reason]"""
        
        if not self.main_bot_id:
            self.main_bot_id = self.bot.user.id
            self.load_webhooks()
        
        self.afk_users[ctx.author.id] = (reason, datetime.utcnow())
        await ctx.send(f"**AFK** status set. Reason: {reason}", delete_after=10)

    @commands.command()
    async def mention(self, ctx, index: int = None):
        """Show bot retrieve past mention by index
        Usage: mention index"""
        
        if index is not None:
            await self._handle_mention_search(ctx, index)
        else:
            main = self.colors['main']
            sub = self.colors['sub']
            reset = self.colors['reset']
    
            content = f"""> ```ansi
    {main}─── {sub}mention error{main} ───
    {main}Error: {sub}Use index{reset}
    {main}Example: {sub}mention 5{reset}```"""
            await ctx.send(content)

    async def _handle_mention_search(self, ctx, index: int):
        """Handle mention search functionality"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        if ctx.guild is None:
            content = f"""> ```ansi
> {main}This command can only be used in servers.{reset}```"""
            return await ctx.send(content)
    
        if index < 1:
            content = f"""> ```ansi
> {main}Index must be a positive integer.{reset}```"""
            return await ctx.send(content)
    
        progress_msg = await ctx.send(f"""> ```ansi
> {main}Searching last 1000 messages for mentions...```""")
    
        try:
            mentions = []
            async for message in ctx.channel.history(limit=1000):
                if ctx.author in message.mentions:
                    mentions.append(message)
                if len(mentions) >= index:
                    break
    
            if len(mentions) < index:
                content = f"""> ```ansi
> {main}─── {sub}MENTION NOT FOUND{main} ───
> {main}Only {len(mentions)} mentions found.{reset}```"""
                return await ctx.send(content)
    
            message = mentions[index-1]
            content = f"""{self.prefix}```ansi
{self.prefix}{main}─── {sub}MENTION FOUND ({index}/{len(mentions)}){main} ───
{self.prefix}{main}Author:{reset} {sub}{message.author.display_name}{reset}
{self.prefix}{main}Content:{reset} {sub}{message.clean_content[:75].replace('`', "'")}{'...' if len(message.clean_content) > 75 else ''}{reset}
{self.prefix}{main}Time:{reset} {sub}{message.created_at.strftime('%Y-%m-%d %H:%M')}{reset}
{self.prefix}{main}Jump URL:{reset} {sub}{message.jump_url}{reset}```"""
    
            await ctx.send(content)
        except Exception as e:
            content = f"""{self.prefix}```ansi
{self.prefix}{main}─── {sub}SEARCH ERROR{main} ───
{self.prefix}{sub}Error:{reset} {main}{str(e)}{reset}```"""
            await ctx.send(content)
        finally:
            await progress_msg.delete()


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
    
        if "<!--afk-bot-->" in message.content:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
    
        await self._handle_afk_mentions(message)
        await self._handle_afk_return(message)

    async def _handle_afk_return(self, message):
        """Handle AFK status removal ONLY when user sends a message"""
        if message.author.id not in self.afk_users:
            return
    
        reason, timestamp = self.afk_users.pop(message.author.id)
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        away_time = self._format_afk_time(datetime.utcnow() - timestamp)
    
        content = f"""<!--afk-bot-->
> ```ansi
> {main}─── {sub}WELCOME BACK{main} ───
> {main}User:{reset} {sub}{message.author.name}
> {main}Status:{reset} {sub}✅ AFK removed
> {main}Away For:{reset} {sub}{away_time}```"""
    
        await message.channel.send(content, delete_after=10)

    async def _handle_afk_mentions(self, message):
        """Handle AFK notifications for mentioned users"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        current_time = datetime.utcnow()
    
        for mention in message.mentions:
            if mention.id not in self.afk_users:
                continue
    
            if self._afk_cooldown_active(mention.id):
                continue
    
            reason, timestamp = self.afk_users[mention.id]
            time_ago = self._format_afk_time(current_time - timestamp)
            
            content = "<!--afk-bot-->\n" + f"""{self.prefix}```ansi
{self.prefix}{main}─── {sub}AFK NOTICE{main} ───
{self.prefix}{main}User:{reset} {sub}{mention.name}
{self.prefix}{main}Reason:{reset} {sub}{reason}
{self.prefix}{main}Duration:{reset} {sub}{time_ago}```"""

            
            await message.channel.send(content, delete_after=10)
            self.afk_cooldowns[mention.id] = current_time

            if self.main_bot_id and self.webhooks:
                await self.send_afk_webhook(mention, message.author, message)

    def _afk_cooldown_active(self, user_id):
        """Check AFK notification cooldown"""
        cooldown = timedelta(seconds=30)
        return (
            user_id in self.afk_cooldowns and 
            (datetime.utcnow() - self.afk_cooldowns[user_id]) < cooldown
        )

    def _format_afk_time(self, delta):
        """Format time delta for AFK display"""
        seconds = delta.total_seconds()
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

def setup(bot):
    bot.add_cog(InfoCog(bot))