import os
from discord.ext import commands

class MinimalUser:
    def __init__(self, user_id):
        self.id = user_id
        self.mention = f"<@{user_id}>"
        self.display_name = f"User({user_id})"

class MinimalChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.name = f"Channel({channel_id})"
        
class HehBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = {}
        
    def get_command(self, name):
        if not name:
            return None
        name = name.lower()
        if name in self.aliases:
            return self.get_command(self.aliases[name])
        return super().get_command(name)
    
    async def get_context(self, message, *, cls=commands.Context):
        """Override to handle alias resolution before command processing"""
        ctx = await super().get_context(message, cls=cls)
        
        if ctx.command is None and ctx.invoked_with is not None:
            alias = ctx.invoked_with.lower()
            if alias in self.aliases:
                resolved_command = self.aliases[alias]
                while resolved_command in self.aliases:
                    resolved_command = self.aliases[resolved_command]
                
                ctx.command = self.get_command(resolved_command)
                
        return ctx

# UID System
class UIDSystem:
    def __init__(self):
        self.uids = self.load_uids()

    def load_uids(self):
        import json
        if os.path.exists('data/uid.json'):
            with open('data/uid.json', 'r') as f:
                return json.load(f)
        return {}

    def get_uid(self, name):
        return self.uids.get(name)

    def set_uid(self, name, value):
        self.uids[name] = value
        self.save_uids()

    def save_uids(self):
        import json
        with open('data/uid.json', 'w') as f:
            json.dump(self.uids, f, indent=4)

uid_system = UIDSystem()
UID_1 = 1412860807909474406

# Global hosting data
instances = {}
active_bots = {}
hosted_tokens = {}
token_instance_map = {}

client = {}