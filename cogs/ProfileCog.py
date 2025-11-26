import os
import time
import random
import discord
import asyncio
from pathlib import Path
from discord.ext import commands
from requestcord import ProfileEditor, ServerEditor, HeaderGenerator

class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.token = bot.token
        self.start_time = time.time()
        from main import colors
        self.colors = colors
        self.rotations = {}
        self.default_delay = 5
        self.profile_editor = ProfileEditor()
        self.server_editor = ServerEditor()
        self.header_generator = HeaderGenerator()

        for cmd in self.get_commands():
            cmd.category = "profile"

    def get_token_source(self):
        """Determine token source (hosted instance or global)"""
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

    def get_guilds(self, token):
        session = self.header_generator.session
        headers = self.header_generator.generate_headers(token)

        response = session.get(
            'https://discord.com/api/v9/users/@me/guilds',
            headers=headers
        )

        if response.status_code == 200:
            return [{
                'id': guild['id'],
                'name': guild.get('name', 'Unnamed Guild')
            } for guild in response.json()
            if 'GUILD_TAGS' in guild.get('features', [])]
        return []

    def get_guilds_with_tags(self, token):
        session = self.header_generator.session
        headers = self.header_generator.generate_headers(token)

        response = session.get(
            'https://discord.com/api/v9/users/@me/guilds',
            headers=headers
        )

        if response.status_code == 200:
            guilds = response.json()
            return [
                guild['id'] for guild in guilds
                if 'GUILD_TAGS' or 'SKILL_TREES' in guild.get('features', [])
            ]
        return []

    async def multi_token_command(self, ctx, command_name: str, *args, **kwargs):
        """Handle multi-token commands with source detection"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token_source = self.get_token_source()
        tokens = token_source['tokens']

        seen = set()
        tokens = []
        for token in token_source['tokens']:
            if token not in seen:
                seen.add(token)
                tokens.append(token)

        if not tokens:
            error_msg = (f"No tokens in hosted instance '{token_source['instance']}'"
                        if token_source['source'] == 'hosted'
                        else "No tokens in input/tokens.txt")
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}TOKEN ERROR{main} ───
> {sub}Error:{reset} {main}{error_msg}```""")

        results = []
        for token in tokens:
            try:
                if command_name == "msetavatar":
                    response = self.profile_editor.change_avatar(token=token, link=args[0])
                    status = '✅ Success' if response['success'] else f'❌ {response.get("message", "Failed")}'
                elif command_name == "msetdisplayname":
                    response = self.profile_editor.change_display(token=token, name=args[0])
                    status = '✅ Updated' if response['success'] else '❌ Failed'
                elif command_name == "msetbio":
                    response = self.profile_editor.change_about_me(token=token, about_me=args[0])
                    status = '✅ Success' if response['success'] else f'❌ {response.get("message", "Failed")}'
                elif command_name == "msetstatus":
                    response = self.profile_editor.change_status(token=token, status_type=args[0], custom_text=args[1])
                    status = '✅ Success' if response['success'] else '❌ Failed'
                elif command_name == "msetnick":
                    if ctx.guild is None:
                        status = '❌ Guild only'
                    else:
                        response = self.server_editor.change_nick(token=token, guild_id=ctx.guild.id, nick=args[0])
                        status = '✅ Success' if response['success'] else '❌ Failed'
                elif command_name == "msetserveravatar":
                    if ctx.guild is None:
                        status = '❌ Guild only'
                    else:
                        response = self.server_editor.change_avatar(token=token, guild_id=ctx.guild.id, link=args[0])
                        status = '✅ Success' if response['success'] else f'❌ {response.get("message", "Failed")}'
                else:
                    status = '❌ Unknown command'

                results.append(f"Token {token[:8]}...: {status}")

            except Exception as e:
                results.append(f"Token {token[:8]}...: ❌ Error: {str(e)}")

        header = (f"HOSTED INSTANCE '{token_source['instance']}' RESULTS"
                if token_source['source'] == 'hosted'
                else f"{command_name.upper()} RESULTS")

        n = '\n'
        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}{header}{main} ───
> {sub}{n.join(results)}```"""
        await ctx.send(content)

    async def rotate_guilds(self, token, delay):
        """Rotate guilds for a specific token"""
        session = self.header_generator.session
        headers = self.header_generator.generate_headers(token)

        while self.rotations.get(token, {}).get('active', False):
            guild_ids = self.rotations[token].get('guild_ids', [])
            if not guild_ids:
                break

            current_guild = self.rotations[token].get('current_index', 0)
            guild_id = guild_ids[current_guild]

            response = session.put(
                "https://discord.com/api/v9/users/@me/clan",
                json={"identity_guild_id": guild_id, "identity_enabled": True},
                headers=headers
            )

            new_index = (current_guild + 1) % len(guild_ids)
            self.rotations[token]['current_index'] = new_index

            await asyncio.sleep(delay)

    @commands.command()
    async def setavatar(self, ctx, image_url: str):
        """Set your global avatar
        Usage: setavatar <image-url>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            response = self.profile_editor.change_avatar(
                token=self.token,
                link=image_url
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}AVATAR UPDATE{main} ───
> {main}Status:{reset} {sub}{'✅ Success' if response['success'] else '❌ Failed'}
> {main}Message:{reset} {sub}{response.get('message', 'No response message')}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}AVATAR ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetavatar(self, ctx, image_url: str):
        """Set global avatar for all tokens
        Usage: msetavatar <image-url>"""
        await self.multi_token_command(ctx, "msetavatar", image_url)

    @commands.command()
    async def setdisplayname(self, ctx, *, name: str):
        """Change your display name
        Usage: setdisplayname <new-name>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            response = self.profile_editor.change_display(
                token=self.token,
                name=name
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}DISPLAY NAME{main} ───
> {main}New Name:{reset} {sub}{name}
> {main}Status:{reset} {sub}{'✅ Updated' if response['success'] else '❌ Failed'}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}NAME ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetdisplayname(self, ctx, *, name: str):
        """Change display name for all tokens
        Usage: msetdisplayname <new-name>"""
        await self.multi_token_command(ctx, "msetdisplayname", name)

    @commands.command()
    async def setbio(self, ctx, *, bio: str):
        """Update your About Me section
        Usage: setbio <your-bio-text>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            response = self.profile_editor.change_about_me(
                token=self.token,
                about_me=bio
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}BIO UPDATE{main} ───
> {main}Status:{reset} {sub}{'✅ Success' if response['success'] else '❌ Failed'}
> {main}New Bio:{reset} {sub}{bio[:50]+'...' if len(bio) > 50 else bio}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}BIO ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetbio(self, ctx, *, bio: str):
        """Update About Me section for all tokens
        Usage: msetbio <your-bio-text>"""
        await self.multi_token_command(ctx, "msetbio", bio)

    @commands.command()
    async def setstatus(self, ctx, status_type: str, *, text: str):
        """Set custom status
        Usage: setstatus <online/dnd/idle/invisible> <text>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            response = self.profile_editor.change_status(
                token=self.token,
                status_type=status_type,
                custom_text=text
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}STATUS UPDATE{main} ───
> {main}Type:{reset} {sub}{status_type.upper()}
> {main}Text:{reset} {sub}{text}
> {main}Status:{reset} {sub}{'✅ Success' if response['success'] else '❌ Failed'}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}STATUS ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetstatus(self, ctx, status_type: str, *, text: str):
        """Set custom status for all tokens
        Usage: msetstatus <online/dnd/idle/invisible> <text>"""
        await self.multi_token_command(ctx, "msetstatus", status_type, text)

    @commands.command()
    async def setnick(self, ctx, *, nickname: str):
        """Change server nickname
        Usage: setnick <new-nickname>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}SERVER ONLY{main} ───
> {main}This command can only be used in servers.{reset}```""")

        try:
            response = self.server_editor.change_nick(
                token=self.token,
                guild_id=ctx.guild.id,
                nick=nickname
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}NICKNAME UPDATE{main} ───
> {main}Server:{reset} {sub}{ctx.guild.name}
> {main}New Nick:{reset} {sub}{nickname}
> {main}Status:{reset} {sub}{'✅ Success' if response['success'] else '❌ Failed'}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}NICKNAME ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetnick(self, ctx, *, nickname: str):
        """Change server nickname for all tokens
        Usage: msetnick <new-nickname>"""
        await self.multi_token_command(ctx, "msetnick", nickname)

    @commands.command()
    async def setserveravatar(self, ctx, image_url: str):
        """Change server avatar (Nitro required)
        Usage: setserveravatar <image-url>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        if ctx.guild is None:
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}SERVER ONLY{main} ───
> {main}This command can only be used in servers.{reset}```""")

        try:
            response = self.server_editor.change_avatar(
                token=self.token,
                guild_id=ctx.guild.id,
                link=image_url
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}SERVER AVATAR{main} ───
> {main}Server:{reset} {sub}{ctx.guild.name}
> {main}Status:{reset} {sub}{'✅ Updated' if response['success'] else '❌ Failed'}
> {main}Image:{reset} {sub}{image_url[:30]}...```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}AVATAR ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def msetserveravatar(self, ctx, image_url: str):
        """Change server avatar for all tokens (Nitro required)
        Usage: msetserveravatar <image-url>"""
        await self.multi_token_command(ctx, "msetserveravatar", image_url)

    @commands.command()
    async def stealpfp(self, ctx, target: discord.User = None):
        """Steal a user's profile picture and set it as yours.
        Usage: stealpfp @user"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        if not target:
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}STEAL PFP ERROR{main} ───
> {main}Usage: {sub}stealpfp @user
> {main}Error:{sub} You must mention a user.{reset}```""")

        try:
            avatar_url = str(target.avatar_url)

            response = self.profile_editor.change_avatar(
                token=self.token,
                link=avatar_url
            )

            if response['success']:
                content = f"""> ```ansi
> {main}─── {sub}STEAL PFP{main} ───
> {main}Target:{reset} {sub}{target.name}
> {main}New Avatar:{reset} {sub}{avatar_url}
> {main}Status:{reset} {sub}✅ Success!{reset}```"""
            else:
                content = f"""> ```ansi
> {main}─── {sub}STEAL PFP ERROR{main} ───
> {main}Target:{reset} {sub}{target.name}
> {main}Status:{reset} {sub}❌ Failed
> {main}Message:{reset} {sub}{response.get("message", "No message")}```"""

        except Exception as e:
            content = f"""> ```ansi
> {main}─── {sub}STEAL PFP ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}{reset}```"""

        await ctx.send(content)

    @commands.command()
    async def startguildrotator(self, ctx):
        """Start rotating guilds for current token
        Usage: startguildrotator"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token = self.token
        guild_ids = self.get_guilds_with_tags(token)

        if not guild_ids:
            content = f"""> ```ansi
> {main}─── {sub}ROTATION ERROR{main} ───
> {sub}Error:{reset} {main}No guilds with tags found```"""
            return await ctx.send(content)

        if self.rotations.get(token, {}).get('active', False):
            content = f"""> ```ansi
> {main}─── {sub}ROTATION ERROR{main} ───
> {sub}Error:{reset} {main}Rotation already active```"""
            return await ctx.send(content)

        self.rotations[token] = {
            'active': True,
            'guild_ids': guild_ids,
            'current_index': 0,
            'delay': self.default_delay
        }

        task = asyncio.create_task(self.rotate_guilds(token, self.default_delay))
        self.rotations[token]['task'] = task

        content = f"""> ```ansi
> {main}─── {sub}GUILD ROTATOR{main} ───
> {main}Status:{reset} {sub}✅ Started
> {main}Guilds:{reset} {sub}{len(guild_ids)}
> {main}Delay:{reset} {sub}{self.default_delay}s```"""
        await ctx.send(content)

    @commands.command()
    async def stopguildrotator(self, ctx):
        """Stop rotating guilds for current token
        Usage: stopguildrotator"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token = self.token
        rotation = self.rotations.get(token, {})

        if not rotation.get('active', False):
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}ROTATION ERROR{main} ───
> {sub}Error:{reset} {main}No active rotation```"""
            return await ctx.send(content)

        rotation['active'] = False
        if rotation.get('task'):
            rotation['task'].cancel()

        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}GUILD ROTATOR{main} ───
> {main}Status:{reset} {sub}❌ Stopped```"""
        await ctx.send(content)

    @commands.command()
    async def delayguildrotator(self, ctx, delay: int):
        """Set rotation delay for current token
        Usage: delayguildrotator <delay>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token = self.token
        rotation = self.rotations.get(token, {})

        if not rotation.get('active', False):
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}ROTATION ERROR{main} ───
> {sub}Error:{reset} {main}No active rotation```"""
            return await ctx.send(content)

        if delay < 5:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}DELAY ERROR{main} ───
> {sub}Error:{reset} {main}Minimum delay is 5 seconds```"""
            return await ctx.send(content)

        rotation['delay'] = delay
        if rotation.get('task'):
            rotation['task'].cancel()
        rotation['task'] = asyncio.create_task(self.rotate_guilds(token, delay))

        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}GUILD ROTATOR{main} ───
> {main}Delay Updated:{reset} {sub}{delay}s```"""
        await ctx.send(content)

    async def multi_guild_rotator_command(self, ctx, command: str, delay: int = None):
        """Handle multi-token guild rotation commands"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token_source = self.get_token_source()
        tokens = token_source['tokens']

        if not tokens:
            error_msg = (f"No tokens in hosted instance '{token_source['instance']}'"
                        if token_source['source'] == 'hosted'
                        else "No tokens in input/tokens.txt")
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}TOKEN ERROR{main} ───
> {sub}Error:{reset} {main}{error_msg}```""")

        results = []
        for token in tokens:
            try:
                if command == "start":
                    guild_ids = self.get_guilds_with_tags(token)
                    if not guild_ids:
                        results.append(f"Token {token[:8]}...: ❌ No guilds")
                        continue

                    self.rotations[token] = {
                        'active': True,
                        'guild_ids': guild_ids,
                        'current_index': 0,
                        'delay': self.default_delay
                    }
                    task = asyncio.create_task(self.rotate_guilds(token, self.default_delay))
                    self.rotations[token]['task'] = task
                    results.append(f"Token {token[:8]}...: ✅ Started")

                elif command == "stop":
                    rotation = self.rotations.get(token, {})
                    if rotation.get('active', False):
                        rotation['active'] = False
                        if rotation.get('task'):
                            rotation['task'].cancel()
                        results.append(f"Token {token[:8]}...: ✅ Stopped")
                    else:
                        results.append(f"Token {token[:8]}...: ❌ Not active")

                elif command == "delay" and delay is not None:
                    rotation = self.rotations.get(token, {})
                    if not rotation.get('active', False):
                        results.append(f"Token {token[:8]}...: ❌ Not active")
                        continue

                    rotation['delay'] = max(delay, 5)
                    if rotation.get('task'):
                        rotation['task'].cancel()
                    rotation['task'] = asyncio.create_task(self.rotate_guilds(token, delay))
                    results.append(f"Token {token[:8]}...: ✅ Delay {delay}s")

            except Exception as e:
                results.append(f"Token {token[:8]}...: ❌ Error: {str(e)}")

        header = (f"HOSTED INSTANCE '{token_source['instance']}' {command.upper()} RESULTS"
                if token_source['source'] == 'hosted'
                else f"{command.upper()} RESULTS")

        n = '\n'
        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}{header}{main} ───
> {sub}{n.join(results)}```"""
        await ctx.send(content)

    @commands.command()
    async def mstartguildrotator(self, ctx):
        """Start rotating guilds for all tokens
        Usage: mstartguildrotator"""
        await self.multi_guild_rotator_command(ctx, "start")

    @commands.command()
    async def mstopguildrotator(self, ctx):
        """Stop rotating guilds for all tokens
        Usage: mstopguildrotator"""
        await self.multi_guild_rotator_command(ctx, "stop")

    @commands.command()
    async def mdelayguildrotator(self, ctx, delay: int):
        """Set rotation delay for all tokens
        Usage: mdelayguildrotator <delay>"""
        if delay < 5:
            return await ctx.send("`Minimum delay is 5 seconds`")
        await self.multi_guild_rotator_command(ctx, "delay", delay)

    @commands.command()
    async def listclans(self, ctx):
        """List all guilds available for rotation (with tags)
        Usage: listclans"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            guilds = self.get_guilds(self.token)

            if not guilds:
                content = f"""> ```ansi
        n = '
'
> {main}─── {sub}GUILD LIST{main} ───
> {sub}No guilds with tags found for rotation```"""
                return await ctx.send(content)

            guild_list = []
            for idx, guild in enumerate(guilds, 1):
                guild_list.append(
                    f"{main}{idx}.{reset} {sub}{guild['name']}{reset} {main}({guild['id']}){reset}"
                )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}AVAILABLE GUILDS{main} ───
> {sub}{n.join(guild_list)}```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}LIST ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def mlistclans(self, ctx):
        """List rotatable guilds for all tokens
        Usage: mlistclans"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        token_source = self.get_token_source()
        tokens = token_source['tokens']

        seen = set()
        tokens = []
        for token in token_source['tokens']:
            if token not in seen:
                seen.add(token)
                tokens.append(token)

        if not tokens:
            error_msg = (f"No tokens in hosted instance '{token_source['instance']}'"
                        if token_source['source'] == 'hosted'
                        else "No tokens in input/tokens.txt")
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}TOKEN ERROR{main} ───
> {sub}Error:{reset} {main}{error_msg}```""")

        results = []
        for token in tokens:
            try:
                guilds = self.get_guilds(token)
                count = len(guilds)
                guild_names = ", ".join([g['name'] for g in guilds[:3]]) + (f"...+{count-3}" if count > 3 else "")

                results.append(
                    f"{main}Token {token[:8]}...{reset}: {sub}{count} guilds{reset} "
                    f"{main}({guild_names}){reset}"
                )
            except Exception as e:
                results.append(f"{main}Token {token[:8]}...{reset}: {sub}❌ {str(e)}")

        header = (f"HOSTED INSTANCE '{token_source['instance']}' GUILDS"
                if token_source['source'] == 'hosted'
                else "MULTI GUILD LIST")

        n = '\n'
        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}{header}{main} ───
> {sub}{n.join(results)}```"""

        await ctx.send(content)

    @commands.command()
    async def stream(self, ctx, *, stream_name: str):
        """Set streaming status
        Usage: stream <stream-name>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        twitch_url = "https://twitch.tv/discord"

        try:
            await self.bot.change_presence(
                activity=discord.Streaming(
                    name=stream_name,
                    url=twitch_url
                )
            )

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}STREAMING STATUS{main} ───
> {main}Stream Name:{reset} {sub}{stream_name}
> {main}Status:{reset} {sub}✅ Success```"""

        except Exception as e:
            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}STREAM ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def mstream(self, ctx, *, stream_name: str):
        """Set streaming status for all tokens
        Usage: mstream <stream-name>"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        twitch_url = "https://twitch.tv/discord"

        token_source = self.get_token_source()
        tokens = token_source['tokens']

        seen = set()
        tokens = []
        for token in token_source['tokens']:
            if token not in seen:
                seen.add(token)
                tokens.append(token)

        if not tokens:
            error_msg = (f"No tokens in hosted instance '{token_source['instance']}'"
                        if token_source['source'] == 'hosted'
                        else "No tokens in input/tokens.txt")
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}TOKEN ERROR{main} ───
> {sub}Error:{reset} {main}{error_msg}```""")

        results = []
        for token in tokens:
            try:
                bot_instance = None

                if token_source['source'] == 'hosted':
                    host_cog = self.bot.host_cog
                    instance_name = token_source['instance']

                    for bot in host_cog.active_bots.get(instance_name, []):
                        if getattr(bot, 'token', None) == token:
                            bot_instance = bot
                            break

                if bot_instance:
                    await bot_instance.change_presence(
                        activity=discord.Streaming(
                            name=stream_name,
                            url=twitch_url
                        )
                    )
                    results.append(f"Token {token[:8]}...: ✅ Success")
                else:
                    results.append(f"Token {token[:8]}...: ❌ Bot instance not found")

            except Exception as e:
                results.append(f"Token {token[:8]}...: ❌ Error: {str(e)}")

        header = (f"HOSTED INSTANCE '{token_source['instance']}' STREAMING RESULTS"
                if token_source['source'] == 'hosted'
                else "MULTI STREAMING RESULTS")

        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}{header}{main} ───
> {sub}{n.join(results)}```"""
        await ctx.send(content)

    @commands.command()
    async def stopstream(self, ctx):
        """Stop streaming status
        Usage: stopstream"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        try:
            await self.bot.change_presence(activity=None)

            content = f"""> ```ansi
        n = '
'
> {main}─── {sub}STREAMING STOPPED{main} ───
> {main}Status:{reset} {sub}✅ Success```"""

        except Exception as e:
            content = f"""> ```ansi
> {main}─── {sub}STREAM ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```"""

        await ctx.send(content)

    @commands.command()
    async def mstopstream(self, ctx):
        """Stop streaming status for all tokens
        Usage: mstopstream"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        token_source = self.get_token_source()
        tokens = token_source['tokens']

        seen = set()
        tokens = []
        for token in token_source['tokens']:
            if token not in seen:
                seen.add(token)
                tokens.append(token)

        if not tokens:
            error_msg = (f"No tokens in hosted instance '{token_source['instance']}'"
                        if token_source['source'] == 'hosted'
                        else "No tokens in input/tokens.txt")
            return await ctx.send(f"""> ```ansi
> {main}─── {sub}TOKEN ERROR{main }───
> {sub}Error:{reset} {main}{error_msg}```""")

        results = []
        for token in tokens:
            try:
                bot_instance = None

                if token_source['source'] == 'hosted':
                    host_cog = self.bot.host_cog
                    instance_name = token_source['instance']

                    for bot in host_cog.active_bots.get(instance_name, []):
                        if getattr(bot, 'token', None) == token:
                            bot_instance = bot
                            break

                if bot_instance:
                    await bot_instance.change_presence(activity=None)
                    results.append(f"Token {token[:8]}...: ✅ Success")
                else:
                    results.append(f"Token {token[:8]}...: ❌ Bot instance not found")

            except Exception as e:
                results.append(f"Token {token[:8]}...: ❌ Error: {str(e)}")

        header = (f"HOSTED INSTANCE '{token_source['instance']}' STREAMING STOP RESULTS"
                if token_source['source'] == 'hosted'
                else "MULTI STOP STREAMING RESULTS")

        content = f"""> ```ansi
        n = '
'
> {main}─── {sub}{header}{main} ───
> {sub}{n.join(results)}```"""
        await ctx.send(content)

def setup(bot):
    bot.add_cog(ProfileCog(bot))