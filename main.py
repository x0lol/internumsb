import os
import re
import time
import json
import random
import aiohttp
import asyncio
import discord
import threading

from colorama           import Fore
from datetime           import datetime
from discord.ext        import commands
from typing             import Dict
from concurrent.futures import ThreadPoolExecutor
from curl_cffi.requests import AsyncSession


from requestcord        import *
from core.globals       import client
from core.globals       import HehBot


logs = []
client_ready = asyncio.Event()

red = Fore.RED
yellow = Fore.YELLOW
green = Fore.GREEN
cyan = Fore.CYAN
lightcyan = Fore.LIGHTCYAN_EX
blue = Fore.BLUE
reset = Fore.RESET
grey = Fore.LIGHTBLACK_EX
black = Fore.BLACK
magenta = Fore.MAGENTA

good_sign = f"{reset}[{green}+{reset}]"
bad_sign = f"{reset}[{red}-{reset}]"
mid_sign = f"{reset}[{yellow}/{reset}]"

with open('input/config.json', 'r') as f:
    config = json.load(f)
colors = config['colors']
prefix = config.get('prefix')

available_colors = {
    "pink": "\033[1;35m",
    "cyan": "\033[1;36m",
    "blue": "\033[1;34m",
    "yellow": "\033[1;33m",
    "green": "\033[1;32m",
    "red": "\033[1;31m",
    "white": "\033[1;37m",
    "black": "\033[1;30m"
}


def load_tokens():
    with open("input/tokens.txt", "r") as file:
        return [line.strip() for line in file.readlines() if line.strip()]

def remove_token_from_file(bad_token):
    with open("input/tokens.txt", 'r') as file:
        lines = file.readlines()
    with open("input/tokens.txt", 'w') as file:
        for line in lines:
            if line.strip() != bad_token:
                file.write(line)

tokens = load_tokens()


def banner(ascii):
    lines = ascii.split('\n')
    for line in lines:
        print(line)
        time.sleep(0.03)

def log_action(action, channel=None):
    timestamp = datetime.now().strftime('%H:%M:%S')
    location = "Start"
    if channel:
        if isinstance(channel, discord.DMChannel):
            location = "DM"
        elif isinstance(channel, discord.TextChannel):
            location = f"#{channel.name}"
        elif isinstance(channel, discord.GroupChannel):
            location = "GC"
    log_entry = f"{grey}{timestamp}{reset} - in {magenta}{location}{reset}: {grey}{action}{reset}"
    logs.append(log_entry)
    print(log_entry)

HeaderGen = HeaderGenerator()
curlSession = AsyncSession()
async def edit_message(message_id: int, channel_id: int, content: str, token: str):
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}"
    headers = HeaderGen.generate_headers(token=token)

    json_data = {"content": content}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=json_data) as response:
                if 200 <= response.status < 300:
                    return True
                else:
                    log_action(f"Failed to edit message: {response.status} - {await response.text()}")
                    return False

    except Exception as e:
        log_action(f"URL error: {str(e)}")
        return False

cogs_dir = 'cogs'
xvx_cogs = [f'cogs.{f[:-3]}' for f in os.listdir(cogs_dir) if f.endswith('.py')]

def load_single_cog(bot, cog):
    """Load a single cog"""
    try:
        bot.load_extension(cog)
    except Exception as e:
        log_action(f"{bad_sign} Failed to load cog {magenta}{cog}{reset}: {str(e)}")

def load_cogs(bot, cogs, max_workers=8):
    """Load cogs synchronously in parallel."""
    log_entries = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(lambda cog: load_single_cog(bot, cog), cogs)
        log_entries.extend(results)

def load_cogs_in_background(bot, cogs, loop):
    """Run cog loading in a separate thread."""
    load_cogs(bot, cogs)

def setup_core_features(bot_instance, log_action):
    @bot_instance.event
    async def on_ready():
        global client_ready
        if not client_ready.is_set():
            os.system("cls")
            print(name)
            client_ready.set()

        twitch_url = "https://www.twitch.tv/discord"
        stream_name = "Requestcord"
        username = getattr(bot_instance.user, 'name', 'Hosted Instance')
        await bot_instance.change_presence(activity=discord.Streaming(name=stream_name, url=twitch_url))
        log_action(f"{good_sign} Client Connected To -> {magenta}{username}{reset}")

    @bot_instance.event
    async def on_command_error(ctx, error):
        """Handle command errors with consistent formatting"""
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']

        if isinstance(error, commands.CommandNotFound):
            error_msg = f"""> ```ansi
> {main}─── {sub}COMMAND ERROR{main} ────────────────────────────
> {sub}Command not found:{reset} {main}{ctx.invoked_with}
> {sub}Use {main}{ctx.prefix}help{sub} for available commands
> ```"""
            await ctx.send(error_msg, delete_after=6)
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            usage_line = ctx.command.help.split('Usage: ')[1].split('\n')[0] if 'Usage: ' in ctx.command.help else 'No usage info'
            error_msg = f"""> ```ansi
> {main}─── {sub}ARGUMENT ERROR{main} ───────────────────────────
> {sub}Missing required argument:{reset} {main}{error.param.name}
> {sub}Usage:{reset} {main}{ctx.prefix}{usage_line}
> ```"""
            await ctx.send(error_msg, delete_after=6)

        else:
            error_msg = f"""> ```ansi
> {main}─── {sub}UNHANDLED ERROR{main} ──────────────────────────
> {sub}Error Type:{reset} {main}{type(error).__name__}
> {sub}Details:{reset} {main}{str(error)[:50]}...
> ```"""
            await ctx.send(error_msg, delete_after=6)
            
    bot_instance.remove_command("help")

    @bot_instance.command()
    async def help(ctx, category: str = None, page: int = 1):
        """Show help information
        Usage: help [command/category] [page]
        """
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']
        box_width = 83
        prefix = ctx.bot.custom_prefix
        username = getattr(bot_instance.user, 'name', 'Hosted Instance')
        footer = f"> ```ansi\n> Dev: @ratherdietrying    Prefix: {ctx.bot.custom_prefix}    Version: 1.0.0\n> ```"

        if category:
            cat_lower = category.lower()
        
            cmd = bot_instance.get_command(cat_lower)
            if cmd:
                doc = cmd.help or "No description available."
                parts = doc.strip().split('\n')
                description = parts[0]
                usage = "No usage specified"
                example = ""
        
                for part in parts[1:]:
                    part = part.strip()
                    if part.lower().startswith("usage:"):
                        usage_raw = part[len("usage:"):].strip()
                        usage_parts = usage_raw.split()
                        if usage_parts and usage_parts[0].lower() == category.lower():
                            usage = ' '.join(usage_parts[1:])
                        else:
                            usage = usage_raw
        
                aliases = ', '.join(cmd.aliases) if cmd.aliases else 'None'
                help_msg = f"""> ```ansi
> {sub}Command {sub}| {main}{ctx.bot.custom_prefix}{cmd.name}{reset}
> ```
> ```ansi
> {main}Details{reset}
> {main}Info {sub}| {main}{description}{reset}
> {main}Usage {sub}| {main}{usage}{reset}
> {main}Aliases {sub}| {main}{aliases}{reset}
> ```
> ```ansi
> {main}Dev:{sub}: {sub}@hmmmmmmmmmmmmmmmmmmmmmmmmm x @xzcvxvczxvzx{reset}
> ```"""
                await ctx.send(help_msg, delete_after=120)
                return
        
            matching = []
            for c in bot_instance.commands:
                if (hasattr(c, 'category') and c.category and c.category.lower() == cat_lower) or \
                   (c.cog and c.cog.__class__.__name__.lower() == cat_lower + 'cog'):
                    doc = c.help or "No description available."
                    desc = doc.split("\n")[0].strip()
                    matching.append((c.name.capitalize(), desc))
        
            if matching:
                CHUNK_SIZE = 5  # smaller chunks for the new format
                command_chunks = [matching[i:i+CHUNK_SIZE]
                                for i in range(0, len(matching), CHUNK_SIZE)]

                if page < 1 or page > len(command_chunks):
                    await ctx.send(f"""> ```ansi
> {main}Error:{reset} {sub}Invalid page number pages: 1-{len(command_chunks)}{reset}```""")
                    return

                chunk = command_chunks[page - 1]
                cmd_block = []
                for name, desc in chunk:
                    line = f"> {main}{name}{sub} | {main}{desc}{reset}"
                    cmd_block.append(line)

                message_part = f"""> ```ansi
> {main}{category.capitalize()} {sub}| {main}Page {page}/{len(command_chunks)}{reset}
> ```
> ```ansi
> {main}Commands{reset}
"""
                message_part += "\n".join(cmd_block)
                message_part += f"""
> ```
> ```ansi
> {main}Navigation {sub}| {main}{ctx.bot.custom_prefix}help {category.lower()} [1-{len(command_chunks)}]{reset}
> ```"""

                if len(message_part) > 2000:
                    await ctx.send(f"""> ```ansi
> {main}Error:{reset} {sub}Message too long{reset}```""")
                else:
                    await ctx.send(message_part, delete_after=120)

                return
        
            await ctx.send(f"```ansi\n{main}Error:{reset} Unknown command or category '{category}'.```", delete_after=5)
            return
        
        allowed_users = [1412860807909474406, 1061664535410393148]
        categories = set()
        for cog in xvx_cogs:
            cat = cog.split('.')[-1].replace('Cog', '').lower()
            if cat != "developer" or ctx.author.id in allowed_users:
                categories.add(cat)

        max_len = max(len(cat.capitalize()) for cat in sorted(categories)) + 1
        category_menu = f"""> ```ansi
> Category{sub}: {main}{ctx.bot.custom_prefix}help <category> [page]{reset}
> Commands{sub}: {main}{ctx.bot.custom_prefix}help <command>{reset}
> ```
> ```ansi
> {main}\033[1m\033[4mCategories\033[0m{reset}
"""
        for cat in sorted(categories):
            desc = f"{cat.capitalize()} Category"
            category_menu += f"> {main}{cat.capitalize().ljust(max_len)}{sub} | {main}{desc}{reset}\n"
        category_menu += f"""> ```
> ```ansi
> Ver{sub}: {main}1.0{reset}
> ```"""
        await ctx.send(category_menu, delete_after=120)




    @bot_instance.command()
    async def setprefix(ctx, new_prefix: str = None):
        """Set a new command prefix
        Usage: setprefix [new_prefix]
        Example: setprefix !
        """
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']

        if new_prefix is None:
            current_prefix = ctx.bot.custom_prefix
            response = f"""> ```ansi
> {main}Current Prefix:{reset} {sub}{current_prefix}{reset}
> ```"""
        else:
            old_prefix = ctx.bot.custom_prefix
            ctx.bot.custom_prefix = new_prefix

            response = f"""> ```ansi
> {main}New Prefix:{reset} {sub}{new_prefix}{reset}
> ```"""
        await ctx.send(response, delete_after=6)
    setprefix.category = "misc"

    @bot_instance.command()
    async def restart(ctx):
        """Restart the current bot client"""
        logo = ""
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']

        initial_content = f"""> ```ansi
> {main}Client restarting...{reset}
> ```"""
        msg = await ctx.send(initial_content)

        current_token = ctx.bot.http.token
        user_name = ctx.bot.user.name

        try:
            await ctx.bot.close()
            log_action(f"{mid_sign} Restarting client -> {magenta}{user_name}{reset}")

            if current_token in client:
                del client[current_token]

            await setup_client(current_token)

            success_msg = f"""> ```ansi
> {main}Client restarted successfully!{reset}
> ```"""
            await edit_message(msg.id, ctx.channel.id, success_msg, current_token)

        except Exception as e:
            error_msg = f"""> ```ansi
> {main}─── {sub}RESTART FAILED{main} ───
> {sub}Error:{reset} {main}{str(e)}{reset}
> ```"""
            await ctx.send(error_msg, delete_after=6)
            log_action(f"{bad_sign} Restart failed for {magenta}{user_name}{reset} - {str(e)}")

    restart.category = "misc"

    @bot_instance.command(name="exit")
    async def quit(ctx):
        """Terminate the current bot connection"""
        logo = ""
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']
    
        exit_msg = f"""> ```ansi
> {main}Terminating connection...{reset}```"""
        msg = await ctx.send(exit_msg, delete_after=6)
    
        current_token = ctx.bot.http.token
        user_name = ctx.bot.user.name
    
        try:
            await ctx.bot.close()
            if current_token in client:
                del client[current_token]
    
            success_content = f"""> ```ansi
> {main}Successfully disconnected from Discord.{reset}```"""
            await edit_message(msg.id, ctx.channel.id, success_content, current_token)
    
        except Exception as e:
            error_content = f"""> ```ansi
> {main}─── {sub}EXIT FAILED{main} ───
> {sub}Error:{reset} {main}{str(e)}{reset}```"""
            await edit_message(msg.id, ctx.channel.id, error_content, current_token)
            log_action(f"{bad_sign} Exit failed for {magenta}{user_name}{reset} - {str(e)}")
    
    quit.category = "misc"



async def setup_client(token):
    intents = discord.Intents.all()
    xvx = HehBot(
        command_prefix=lambda bot, message: bot.custom_prefix, 
        self_bot=True, 
        intents=intents,
        timeout=60
    )
    xvx.custom_prefix = prefix
    client[token] = xvx
    
    xvx.token = token
    xvx.xvx_cogs = xvx_cogs

    cog_thread = threading.Thread(
        target=load_cogs_in_background,
        args=(xvx, xvx_cogs, asyncio.get_event_loop())
    )
    cog_thread.start()

    @xvx.event
    async def on_ready():
        global client_ready
        if not client_ready.is_set():
            os.system("cls")
            client_ready.set()

        twitch_url = "https://www.twitch.tv/discord"
        stream_name = "Requestcord"
        #await xvx.change_presence(activity=discord.Streaming(name=stream_name, url=twitch_url))
        log_action(f"{good_sign} Client Connected To -> {magenta}{xvx.user.name}{reset}")

    @xvx.event
    async def on_command_error(ctx, error):
        """Handle command errors with consistent formatting"""
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']

        if isinstance(error, commands.CommandNotFound):
            error_msg = f"""> ```ansi
> {main}─── {sub}COMMAND ERROR{main} ───
> {sub}Command not found:{reset} {main}{ctx.invoked_with}
> {sub}Use {main}{ctx.prefix}help{sub} for available commands
> ```"""
            await ctx.send(error_msg, delete_after=6)
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            usage_line = ctx.command.help.split('Usage: ')[1].split('\n')[0] if 'Usage: ' in ctx.command.help else 'No usage info'
            error_msg = f"""> ```ansi
> {main}─── {sub}ARGUMENT ERROR{main} ───
> {sub}Missing required argument:{reset} {main}{error.param.name}
> {sub}Usage:{reset} {main}{ctx.prefix}{usage_line}
> ```"""
            await ctx.send(error_msg, delete_after=6)

        else:
            error_msg = f"""> ```ansi
> {main}─── {sub}UNHANDLED ERROR{main} ───
> {sub}Error Type:{reset} {main}{type(error).__name__}
> {sub}Details:{reset} {main}{str(error)}...
> ```"""
            await ctx.send(error_msg, delete_after=6)
            
    xvx.remove_command("help")

    @xvx.command()
    async def help(ctx, category: str = None, page: int = 1):
        """Show help information
        Usage: help [command/category] [page]
        """
        logo = ""
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']
        box_width = 83
        prefix = ctx.bot.custom_prefix
        footer = f"> ```ansi\n> Dev: @ratherdietrying    Prefix: {ctx.bot.custom_prefix}    Version: 1.0.0\n> ```"

        if category:
            cat_lower = category.lower()
        
            cmd = xvx.get_command(cat_lower)
            if cmd:
                doc = cmd.help or "No description available."
                parts = doc.strip().split('\n')
                description = parts[0]
                usage = "No usage specified"
                example = ""
        
                for part in parts[1:]:
                    part = part.strip()
                    if part.lower().startswith("usage:"):
                        usage_raw = part[len("usage:"):].strip()
                        usage_parts = usage_raw.split()
                        if usage_parts and usage_parts[0].lower() == category.lower():
                            usage = ' '.join(usage_parts[1:])
                        else:
                            usage = usage_raw
        
                aliases = ', '.join(cmd.aliases) if cmd.aliases else 'None'
                help_msg = f"""> ```ansi
> {sub}Command {sub}| {main}{ctx.bot.custom_prefix}{cmd.name}{reset}
> ```
> ```ansi
> {main}Details{reset}
> {main}Info {sub}| {main}{description}{reset}
> {main}Usage {sub}| {main}{usage}{reset}
> {main}Aliases {sub}| {main}{aliases}{reset}
> ```
> ```ansi
> {main}Dev:{sub}: {sub}@xzcvxvczxvzx x @hmmmmmmmmmmmmmmmmmmmmmmmmm{reset}
> ```"""
                await ctx.send(help_msg, delete_after=120)
                return
        
            matching = []
            for c in xvx.commands:
                if (hasattr(c, 'category') and c.category and c.category.lower() == cat_lower) or \
                   (c.cog and c.cog.__class__.__name__.lower() == cat_lower + 'cog'):
                    doc = c.help or "No description available."
                    desc = doc.split("\n")[0].strip()
                    matching.append((c.name.capitalize(), desc))
        
            if matching:
                CHUNK_SIZE = 5  # smaller chunks for the new format
                command_chunks = [matching[i:i+CHUNK_SIZE]
                                for i in range(0, len(matching), CHUNK_SIZE)]

                if page < 1 or page > len(command_chunks):
                    await ctx.send(f"""> ```ansi
> {main}Error:{reset} {sub}Invalid page number. Available pages: 1-{len(command_chunks)}{reset}```""")
                    return

                chunk = command_chunks[page - 1]
                cmd_block = []
                for name, desc in chunk:
                    line = f"> {main}{name}{sub} | {main}{desc}{reset}"
                    cmd_block.append(line)

                message_part = f"""> ```ansi
> {main}{category.capitalize()} {sub}| {main}Page {page}/{len(command_chunks)}{reset}
> ```
> ```ansi
> {main}Commands{reset}
"""
                message_part += "\n".join(cmd_block)
                message_part += f"""
> ```
> ```ansi
> {main}Navigation {sub}| {main}{ctx.bot.custom_prefix}help {category.lower()} [1-{len(command_chunks)}]{reset}
> ```"""

                if len(message_part) > 2000:
                    await ctx.send(f"""> ```ansi
> {main}Error:{reset} {sub}Message too long{reset}```""")
                else:
                    await ctx.send(message_part, delete_after=120)

            return
        
            await ctx.send(f"```ansi\n{main}Error:{reset} Unknown command or category '{category}'.```", delete_after=120)
            return
        
        allowed_users = [1412860807909474406, 1061664535410393148]
        categories = set()
        for cog in xvx_cogs:
            cat = cog.split('.')[-1].replace('Cog', '').lower()
            if cat != "developer" or ctx.author.id in allowed_users:
                categories.add(cat)

        max_len = max(len(cat.capitalize()) for cat in sorted(categories)) + 1
        category_menu = f"""> ```ansi
> Category{sub}: {main}{ctx.bot.custom_prefix}help <category> [page]{reset}
> Commands{sub}: {main}{ctx.bot.custom_prefix}help <command>{reset}
> ```
> ```ansi
> {main}\033[1m\033[4mCategories\033[0m{reset}
"""
        for cat in sorted(categories):
            desc = f"{cat.capitalize()} Category"
            category_menu += f"> {main}{cat.capitalize().ljust(max_len)}{sub} | {main}{desc}{reset}\n"
        category_menu += f"""> ```
> ```ansi
> Ver{sub}: {main}1.0{reset}
> ```"""
        await ctx.send(category_menu, delete_after=120)


    @xvx.command()
    async def setprefix(ctx, new_prefix: str = None):
        """Set a new command prefix
        Usage: setprefix [new_prefix]
        Example: setprefix !
        """
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']

        if new_prefix is None:
            current_prefix = ctx.bot.custom_prefix
            response = f"""> ```ansi
> {main}Current Prefix:{reset} {sub}{current_prefix}{reset}
> ```"""
        else:
            old_prefix = ctx.bot.custom_prefix
            ctx.bot.custom_prefix = new_prefix

            response = f"""> ```ansi
> {main}─── {sub}PREFIX CHANGED{main} ───────────────────────────────
> {main}Old Prefix:{reset} {sub}{old_prefix}{reset}
> {main}New Prefix:{reset} {sub}{new_prefix}{reset}
> ```"""
        await ctx.send(response, delete_after=6)
    setprefix.category = "misc"

    @xvx.command()
    async def restart(ctx, scope: str = None):
        """Restart bot client(s)
        Usage: restart [all]
        Example: restart all
        """
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']
    
        if scope and scope.lower() == "all":
            initial_content = f"""> ```ansi
> {main}─── {sub}MASS RESTART{main} ───────────────────────────
> {main}Restarting all clients...{reset}
> ```"""
            msg = await ctx.send(initial_content, delete_after=6)

            success = []
            failed = []
            clients_copy = list(client.items())
            token = ctx.bot.http.token

            for index, (token_key, bot_instance) in enumerate(clients_copy):
                try:
                    user_name = str(bot_instance.user)

                    await bot_instance.close()
                    del client[token_key]

                    await setup_client(token_key)

                    success.append(f"> {main}• {sub}{user_name}")

                    success_content = f"""> ```ansi
> {main}─── {sub}MASS RESTART{main} ───────────────────────────
> {main}Progress: {sub}{index+1}/{len(clients_copy)}{main}

> {main}Successful:{reset}
{n.join(success)[:900]}
> ```"""
                    await edit_message(msg.id, ctx.channel.id, success_content, token)

                except Exception as e:
                    error_msg = str(e)
                    failed.append(f"> {main}• {sub}{user_name} {main}- {sub}{error_msg[:30]}...")
                    n = '\n'
                    error_content = f"""> ```ansi
> {main}─── {sub}MASS RESTART{main} ───────────────────────────
> {main}Progress: {sub}{index+1}/{len(clients_copy)}{main}
> {main}Successful:{reset}
{n.join(success)[:400]}
> {main}Failed:{reset}
{n.join(failed)[:400]}
> ```"""
                    await edit_message(msg.id, ctx.channel.id, error_content, token)

            n = '\n'
            final_content = f"""> ```ansi
> {main}─── {sub}RESTART SUMMARY{main} ───
> {main}Total: {sub}{len(clients_copy)}{reset}
> {main}Success: {sub}{len(success)}{reset}
> {main}Failed: {sub}{len(failed)}{reset}
> {main}Successful Clients:{reset}
{n.join(success)[:800]}
> {main}Failed Clients:{reset}
{n.join(failed)[:800]}
> ```"""
            await edit_message(msg.id, ctx.channel.id, final_content, token)
            return
    
        initial_content = f"""> ```ansi
> {main}Client restarting...{reset}
> ```"""
        msg = await ctx.send(initial_content, delete_after=6)

        current_token = ctx.bot.http.token
        user_name = ctx.bot.user.name

        try:
            await ctx.bot.close()
            log_action(f"{mid_sign} Restarting client -> {magenta}{user_name}{reset}")

            if current_token in client:
                del client[current_token]

            await setup_client(current_token)

            success_msg = f"""> ```ansi
> {main}Client restarted successfully!{reset}
> ```"""
            await edit_message(msg.id, ctx.channel.id, success_msg, current_token)

        except Exception as e:
            error_msg = f"""> ```ansi
> {main}─── {sub}RESTART FAILED{main} ───
> {sub}Error:{reset} {main}{str(e)}{reset}
> ```"""
            await ctx.send(error_msg, delete_after=6)
            log_action(f"{bad_sign} Restart failed for {magenta}{user_name}{reset} - {str(e)}")
    
    restart.category = "misc"

    @xvx.command(name='exit')
    async def quit(ctx, scope: str = None):
        """Terminate bot connection(s)
        Usage: exit [all]
        Example: exit all
        """
        main = colors['main']
        sub = colors['sub']
        reset = colors['reset']
    
        if scope and scope.lower() == "all":
            initial_content = f"""> ```ansi
> {main}─── {sub}MASS EXIT{main} ───
> {main}Disconnecting all clients...{reset}
> ```"""
            msg = await ctx.send(initial_content, delete_after=6)
            token = ctx.bot.http.token
            clients_copy = list(client.items())

            exited = []
            for token_key, bot_instance in clients_copy:
                try:
                    user_name = str(bot_instance.user)
                    await bot_instance.close()
                    del client[token_key]
                    exited.append(f"> {main}• {sub}{user_name}")
                except Exception as e:
                    pass

            n = '\n'
            final_content = f"""> ```ansi
> {main}─── {sub}EXIT COMPLETE{main} ───
> {main}Disconnected: {sub}{len(exited)}{main} clients
> {main}Successful exits:{reset}
{n.join(exited)[:800]}
> ```"""
            await edit_message(msg.id, ctx.channel.id, final_content, token)
            return
    

        exit_msg = f"""> ```ansi
> {main}─── {sub}EXITING{main} ───
> {main}Terminating connection...{reset}
> ```"""
        msg = await ctx.send(exit_msg, delete_after=6)

        current_token = ctx.bot.http.token
        user_name = ctx.bot.user.name

        try:

            await ctx.bot.close()
            if current_token in client:
                del client[current_token]


            success_content = f"""> ```ansi
> {main}─── {sub}CONNECTION TERMINATED{main} ───
> {main}Successfully disconnected from Discord.{reset}
> ```"""
            await edit_message(msg.id, ctx.channel.id, success_content, current_token)
        except Exception as e:
            error_content = f"""> ```ansi
> {main}─── {sub}EXIT FAILED{main} ───────────────────────────────
> {sub}Error:{reset} {main}{str(e)}{reset}
> ```"""
            await edit_message(msg.id, ctx.channel.id, error_content, current_token)
            log_action(f"{bad_sign} Exit failed for {magenta}{user_name}{reset} - {str(e)}")
    
    quit.category = "misc"



    try:
        await xvx.login(token, bot=False)
        asyncio.create_task(xvx.connect())
    except discord.errors.LoginFailure:
        log_action(f"{bad_sign} Login failed for token: {blue}{token[:15]}...{reset}")
        remove_token_from_file(token)
        if token in client: del client[token]
    except Exception as e:
        log_action(f"{bad_sign} Error with token: {blue}{token[:15]}...{reset} - {str(e)}")
        if token in client: del client[token]
        
def change_cmd_title():
    if not client_ready.is_set():
        os.system("title Loading Best Client Ever Made .")
        time.sleep(0.25)
        os.system("title Loading Best Client Ever Made ..")
        time.sleep(0.25)
        os.system("title Loading Best Client Ever Made ...")
        time.sleep(0.25)
    os.system('title "Hehselfbot - Made by saith - @xzcvxvczxvzx & saint - @hmmmmmmmmmmmmmmmmmmmmmmmmm"')

def show_loading_screen():
    pass

async def main():
    os.system("cls")
    title_thread = threading.Thread(target=change_cmd_title)
    title_thread.start()

    loading_thread = threading.Thread(target=show_loading_screen)
    loading_thread.start()

    tokens = load_tokens()
    if not tokens:
        log_action(f"{bad_sign} No tokens found in input/tokens.txt")
        return

    batch_size = 10
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        await asyncio.gather(*(setup_client(t) for t in batch))

    # Auto-start hosted tokens
    await asyncio.sleep(15)  # Wait for clients to be ready
    from core.globals import uid_system, instances, active_bots, hosted_tokens, token_instance_map
    if client:
        first_client = list(client.values())[0]
        host_cog = first_client.get_cog('HostCog')
        if host_cog:
            uids_to_remove = []
            for uid, uid_data in uid_system.uids.items():
                if isinstance(uid_data, dict) and 'token' in uid_data:
                    token = uid_data['token']
                    try:
                        name = f"instance_{uid}"
                        instances[name] = {
                            'tokens': [token],
                            'restrictions': [],
                            'owner_id': first_client.user.id,
                            'owner_name': first_client.user.display_name,
                            'active': True,
                            'created_at': uid_data.get('created_at', time.time())
                        }
                        hosted_tokens[name] = [token]
                        token_instance_map[token] = name
                        asyncio.create_task(host_cog.start_instance_bot(name, token))
                        log_action(f"Auto-hosted instance {name} with UID {uid}")
                    except Exception as e:
                        log_action(f"Failed to auto-host UID {uid}: {str(e)}")
                        uids_to_remove.append(uid)
            # Remove invalid UIDs
            for uid in uids_to_remove:
                if uid in uid_system.uids:
                    del uid_system.uids[uid]
            if uids_to_remove:
                uid_system.save_uids()
                log_action(f"Removed invalid UIDs: {uids_to_remove}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())