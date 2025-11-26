import re
import random
import discord
from pathlib import Path
from discord.ext import commands
from requestcord import HeaderGenerator
from curl_cffi.requests import AsyncSession

reaction_storage = {}
super_reaction_storage = {}
random_reaction_storage = {}
random_super_reaction_storage = {}

CUSTOM_EMOJI_PATTERN = re.compile(r'<a?:([a-zA-Z0-9_]+):(\d+)>')
REACTION_URL_TEMPLATE = (
    "https://discord.com/api/v9/channels/{channel_id}/"
    "messages/{message_id}/reactions/{emoji}/@me"
    "?location=Message%20Reaction%20Picker&type=1"
)

class ReactionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from main import colors
        self.colors = colors
        self.header_generator = HeaderGenerator()
        self.session = AsyncSession()
        
        token = self.bot.token
        if token not in reaction_storage:
            reaction_storage[token] = {}
        if token not in super_reaction_storage:
            super_reaction_storage[token] = {}
        if token not in random_reaction_storage:
            random_reaction_storage[token] = {}
        if token not in random_super_reaction_storage:
            random_super_reaction_storage[token] = {}
        
        for cmd in self.get_commands():
            cmd.category = "reactions"

    def get_logo(self):
        return ""
    
    def encode_super_emoji(self, emoji: str) -> str:
        """Encodes emoji for URL use, handling both standard and custom emojis."""
        custom_match = CUSTOM_EMOJI_PATTERN.match(emoji)
        if custom_match:
            animated = "a" if emoji.startswith("<a") else ""
            return f"{animated}:{custom_match.group(1)}:{custom_match.group(2)}"
        return "".join(f"%{b:02X}" for b in emoji.encode("utf-8"))
    
    async def react_via_api(self, message: discord.Message, emoji: str) -> None:
        """Add reaction to a message using Discord API"""
        encoded_emoji = self.encode_super_emoji(emoji)
        url = REACTION_URL_TEMPLATE.format(
            channel_id=message.channel.id,
            message_id=message.id,
            emoji=encoded_emoji
        )

        headers = self.header_generator.generate_headers(token=self.bot.token)
        
        try:
            await self.session.put(
                url,
                headers=headers,
                impersonate="chrome120"
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Automatically react to messages from tracked users"""
        if message.author.bot:
            return
            
        token = self.bot.token
        
        if token in reaction_storage and message.author.id in reaction_storage[token]:
            for emoji in reaction_storage[token][message.author.id]:
                try:
                    await message.add_reaction(emoji)
                except discord.errors.HTTPException:
                    continue
        
        if token in random_reaction_storage and message.author.id in random_reaction_storage[token]:
            emojis = list(random_reaction_storage[token][message.author.id])
            if emojis:
                try:
                    await message.add_reaction(random.choice(emojis))
                except discord.errors.HTTPException:
                    pass
        
        if token in super_reaction_storage and message.author.id in super_reaction_storage[token]:
            for emoji in super_reaction_storage[token][message.author.id]:
                await self.react_via_api(message, emoji)
        
        if token in random_super_reaction_storage and message.author.id in random_super_reaction_storage[token]:
            emojis = list(random_super_reaction_storage[token][message.author.id])
            if emojis:
                await self.react_via_api(message, random.choice(emojis))

    def update_reactions(self, storage, user_id, emojis, add=True):
        """Update reaction tracking for any storage type"""
        token = self.bot.token
        
        if token not in storage:
            if not add:
                return False
            storage[token] = {}
    
        if user_id not in storage[token]:
            if not add:
                return False
            storage[token][user_id] = set(emojis)
            return True
    
        if add:
            storage[token][user_id].update(emojis)
            return True
        
        if emojis:
            storage[token][user_id] -= set(emojis)
        
        if not storage[token][user_id]:
            del storage[token][user_id]
        
        if not storage[token]:
            del storage[token]
        
        return True

    def parse_react_args(self, ctx, args):
        """Parse arguments for react/stopreact commands"""
        emojis = []
        users = []
        
        for arg in args:
            if arg.startswith('<@') and arg.endswith('>'):
                try:
                    user_id = int(arg[2:-1].replace('!', ''))
                    if user := self.bot.get_user(user_id):
                        users.append(user)
                except ValueError:
                    continue
            elif arg.startswith('<:') or arg.startswith('<a:'):
                emojis.append(arg)
            else:
                if arg.isdigit() or not arg.strip():
                    continue
                emojis.append(arg)
        
        users = users or ctx.message.mentions or [ctx.author]
        return emojis, users

    @commands.command()
    async def react(self, ctx, *args):
        """Automatically react to user's messages with emojis
        Usage: react <emoji1> <emoji2> ... [@user1 @user2 ...]
        If no users mentioned, reacts to your messages"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        try:
            emojis, users = self.parse_react_args(ctx, args)
            
            if not emojis:
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}REACTION ERROR{main} ───
> {sub}Error:{reset} {main}No emojis provided```""")
            
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            for user_id in user_ids:
                self.update_reactions(reaction_storage, user_id, emojis)
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}REACTION STARTED{main} ───
> {main}Target Users:{reset} {sub}{user_list}
> {main}Emojis:{reset} {sub}{' '.join(emojis)}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}REACTION ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def rreact(self, ctx, *args):
        """React with ONE RANDOM emoji from list to user's messages
        Usage: rreact <emoji1> <emoji2> ... [@user1 @user2 ...]
        Requires at least 2 emojis"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        try:
            emojis, users = self.parse_react_args(ctx, args)
            
            if len(emojis) < 2:
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}RREACTION ERROR{main} ───
> {sub}Error:{reset} {main}At least 2 emojis required for random reactions```""")
            
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            for user_id in user_ids:
                self.update_reactions(random_reaction_storage, user_id, emojis)
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM REACTION STARTED{main} ───
> {main}Target Users:{reset} {sub}{user_list}
> {main}Emojis:{reset} {sub}{' '.join(emojis)}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RREACTION ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def superreact(self, ctx, *args):
        """Automatically react to user's messages with emojis
        Usage: superreact <emoji1> <emoji2> ... [@user1 @user2 ...]
        If no users mentioned, reacts to your messages"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        try:
            emojis, users = self.parse_react_args(ctx, args)
            
            if not emojis:
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}SUPER REACTION ERROR{main} ───
> {sub}Error:{reset} {main}No emojis provided```""")
            
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            for user_id in user_ids:
                self.update_reactions(super_reaction_storage, user_id, emojis)
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}SUPER REACTION STARTED{main} ───
> {main}Target Users:{reset} {sub}{user_list}
> {main}Emojis:{reset} {sub}{' '.join(emojis)}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}SUPER REACTION ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def rsuperreact(self, ctx, *args):
        """React with ONE RANDOM emoji from list
        Usage: rsuperreact <emoji1> <emoji2> ... [@user1 @user2 ...]
        Requires at least 2 emojis"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        
        try:
            emojis, users = self.parse_react_args(ctx, args)
            
            if len(emojis) < 2:
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}RSUPER REACTION ERROR{main} ───
> {sub}Error:{reset} {main}At least 2 emojis required for random reactions```""")
            
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            for user_id in user_ids:
                self.update_reactions(random_super_reaction_storage, user_id, emojis)
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM SUPER REACTION STARTED{main} ───
> {main}Target Users:{reset} {sub}{user_list}
> {main}Emojis:{reset} {sub}{' '.join(emojis)}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RSUPER REACTION ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def stopreact(self, ctx, *args):
        """Stop automatic reactions for users
        Usage: 
          stopreact - Stops ALL reactions for current token
          stopreact [emojis] [@user1 @user2 ...] - Stops specific reactions"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        token = self.bot.token
        
        try:
            if not args:
                if token in reaction_storage:
                    del reaction_storage[token]
                if token in random_reaction_storage:
                    del random_reaction_storage[token]
                action = "Stopped ALL reactions for this token"
                
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}REACTIONS STOPPED{main} ───
> {main}{action}```""")

            emojis, users = self.parse_react_args(ctx, args)
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            if not emojis:
                for user_id in user_ids:
                    if token in reaction_storage and user_id in reaction_storage[token]:
                        del reaction_storage[token][user_id]
                    if token in random_reaction_storage and user_id in random_reaction_storage[token]:
                        del random_reaction_storage[token][user_id]
                action = f"Stopped ALL reactions for: {user_list}"
            else:
                for user_id in user_ids:
                    self.update_reactions(reaction_storage, user_id, emojis, add=False)
                    self.update_reactions(random_reaction_storage, user_id, emojis, add=False)
                action = f"Stopped reactions for: {user_list} - Emojis: {' '.join(emojis)}"
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}REACTIONS STOPPED{main} ───
> {main}{action}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}STOP ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def stoprreact(self, ctx, *args):
        """Stop random reactions for users
        Usage: 
          stoprreact - Stops ALL random reactions
          stoprreact [emojis] [@user1 @user2 ...] - Stops specific"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        token = self.bot.token
        
        try:
            if not args:
                if token in random_reaction_storage:
                    del random_reaction_storage[token]
                    action = "Stopped ALL random reactions for this token"
                else:
                    action = "No active random reactions found"
                
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM REACTIONS STOPPED{main} ───
> {main}{action}```""")

            emojis, users = self.parse_react_args(ctx, args)
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)

            if not emojis:
                for user_id in user_ids:
                    if token in random_reaction_storage and user_id in random_reaction_storage[token]:
                        del random_reaction_storage[token][user_id]
                action = f"Stopped ALL random reactions for: {user_list}"
            else:
                for user_id in user_ids:
                    self.update_reactions(random_reaction_storage, user_id, emojis, add=False)
                action = f"Stopped random reactions for: {user_list} - Emojis: {' '.join(emojis)}"
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM REACTIONS STOPPED{main} ───
> {main}{action}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}STOP ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def stopsuperreact(self, ctx, *args):
        """Stop automatic super reactions for users
        Usage: stopsuperreact [emojis] [@user1 @user2 ...] - Stops specific"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        token = self.bot.token
        
        try:
            if not args:
                if token in super_reaction_storage:
                    del super_reaction_storage[token]
                if token in random_super_reaction_storage:
                    del random_super_reaction_storage[token]
                action = "Stopped ALL super reactions for this token"
                
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}SUPER REACTIONS STOPPED{main} ───
> {main}{action}```""")
    
            emojis, users = self.parse_react_args(ctx, args)
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            if not emojis:
                for user_id in user_ids:
                    if token in super_reaction_storage and user_id in super_reaction_storage[token]:
                        del super_reaction_storage[token][user_id]
                    if token in random_super_reaction_storage and user_id in random_super_reaction_storage[token]:
                        del random_super_reaction_storage[token][user_id]
                action = f"Stopped ALL super reactions for: {user_list}"
            else:
                for user_id in user_ids:
                    self.update_reactions(super_reaction_storage, user_id, emojis, add=False)
                    self.update_reactions(random_super_reaction_storage, user_id, emojis, add=False)
                action = f"Stopped super reactions for: {user_list} - Emojis: {' '.join(emojis)}"
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}SUPER REACTIONS STOPPED{main} ───
> {main}{action}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}STOP ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")

    @commands.command()
    async def stoprsuperreact(self, ctx, *args):
        """Stop random super reactions for users
        Usage: stoprsuperreact [emojis] [@user1 @user2 ...] - Stops specific"""
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        token = self.bot.token
        
        try:
            if not args:
                if token in random_super_reaction_storage:
                    del random_super_reaction_storage[token]
                    action = "Stopped ALL random super reactions for this token"
                else:
                    action = "No active random super reactions found"
                
                return await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM SUPER REACTIONS STOPPED{main} ───
> {main}{action}```""")

            emojis, users = self.parse_react_args(ctx, args)
            user_ids = [u.id for u in users]
            user_list = ", ".join(u.display_name for u in users)
            
            if not emojis:
                for user_id in user_ids:
                    if token in random_super_reaction_storage and user_id in random_super_reaction_storage[token]:
                        del random_super_reaction_storage[token][user_id]
                action = f"Stopped ALL random super reactions for: {user_list}"
            else:
                for user_id in user_ids:
                    self.update_reactions(random_super_reaction_storage, user_id, emojis, add=False)
                action = f"Stopped random super reactions for: {user_list} - Emojis: {' '.join(emojis)}"
                
            await ctx.send(f"""> ```ansi
> {main}─── {sub}RANDOM SUPER REACTIONS STOPPED{main} ───
> {main}{action}```""")
        
        except Exception as e:
            await ctx.send(f"""> ```ansi
> {main}─── {sub}STOP ERROR{main} ───
> {sub}Error:{reset} {main}{str(e)}```""")
            
def setup(bot):
    bot.add_cog(ReactionsCog(bot))