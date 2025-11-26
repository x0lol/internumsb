import os
import random
from collections import deque
from datetime import datetime
from discord.ext import commands
from requestcord import HeaderGenerator

from core.message import Message, MessageUpdate, MessageDelete , MessageHandler

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.header_generator = HeaderGenerator()
        from main import colors
        self.colors = colors

        self.handler = MessageHandler(
            bot=bot,
            on_message=self.on_message_event,
            on_message_update=self.on_message_update_event,
            on_message_delete=self.on_message_delete_event,
            cache_size=10000
        )
        self.handler.start()

        for cmd in self.get_commands():
            cmd.category = "events"

        os.makedirs("data", exist_ok=True)

        self.snipe_data = {}
        self.edit_snipe_data = {}
        self.snipe_limit = 10

    async def on_message_event(self, message: Message):
        """Handle new messages from the improved MessageHandler"""
        try:
            await self.cache_message(message)

        except Exception as e:
            print(f"[EventsCog] Error processing message: {e}")

    async def on_message_update_event(self, message_update: MessageUpdate):
        """Handle message updates from the improved MessageHandler"""
        try:
            channel_id = str(message_update.channel_id)

            if message_update.before and message_update.after:
                if channel_id not in self.edit_snipe_data:
                    self.edit_snipe_data[channel_id] = deque(maxlen=self.snipe_limit)

                entry = {
                    "before": message_update.before,
                    "after": message_update.after,
                    "author": {
                        "id": message_update.author_id or 0,
                        "username": message_update.author_name or "Unknown",
                        "discriminator": "0"
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "edit_time": message_update.edit_timestamp or datetime.utcnow().isoformat(),
                    "attachments": message_update.attachments or []
                }
                self.edit_snipe_data[channel_id].appendleft(entry)

        except Exception as e:
            print(f"[EventsCog] Error processing message update: {e}")

    async def on_message_delete_event(self, message_delete: MessageDelete):
        """Handle message deletions from the improved MessageHandler"""
        try:
            channel_id = str(message_delete.channel_id)

            if channel_id not in self.snipe_data:
                self.snipe_data[channel_id] = deque(maxlen=self.snipe_limit)

            entry = {
                "content": message_delete.content or "*Message content unavailable*",
                "author": {
                    "id": message_delete.author_id or 0,
                    "username": message_delete.author_name or "Unknown",
                    "discriminator": "0"
                },
                "timestamp": message_delete.timestamp or datetime.utcnow().isoformat(),
                "attachments": message_delete.attachments or []
            }
            self.snipe_data[channel_id].appendleft(entry)

        except Exception as e:
            print(f"[EventsCog] Error processing message delete: {e}")

    async def cache_message(self, message: Message):
        """Cache message details for snipe functionality"""

        pass

    def get_logo(self):
        return ""

    @commands.command()
    async def snipe(self, ctx, index: int = 0):
        """Show recently deleted messages in this channel
        Usage: snipe [index]"""
        channel_id = str(ctx.channel.id)
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        snipe_list = self.snipe_data.get(channel_id, [])
        if not snipe_list:
            content = f"""> ```ansi
> {sub}No deleted messages found in this channel
> ```"""
            return await ctx.send(content)

        if index < 0 or index >= len(snipe_list):
            max_index = len(snipe_list) - 1
            content = f"""> ```ansi
> {main}─── {sub}INVALID INDEX{main} ───
> {sub}Please use index between {main}0{sub} and {main}{max_index}
> ```"""
            return await ctx.send(content)

        message = snipe_list[index]
        timestamp = datetime.fromisoformat(message["timestamp"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{message['author']['username']}#{message['author']['discriminator']}"

        content = message["content"] or "*No text content*"
        content = content.replace('```', '`\u200b`\u200b`')

        attachments = "\n".join(
            (att.get("url") if isinstance(att, dict) and att.get("url") else str(att))
            for att in message["attachments"]
        ) or "No attachments"

        response = f"""> ```ansi
> {main}─── {sub}SNIPE (INDEX: {index}){main} ───
> {sub}Author:{reset} {main}{author}
> {sub}Time:{reset}   {main}{timestamp}
> {sub}Content:{reset} {main}{content[:150]}{'...' if len(content) > 150 else ''}
> {sub}Attachments:{reset} {main}{attachments}
> ```"""

        await ctx.send(response)

    @commands.command()
    async def editsnipe(self, ctx, index: int = 0):
        """Show recently edited messages in this channel
        Usage: editsnipe [index]"""
        channel_id = str(ctx.channel.id)
        main = self.colors['main']
        sub = self.colors['sub']
        reset = self.colors['reset']

        edit_snipe_list = self.edit_snipe_data.get(channel_id, [])
        if not edit_snipe_list:
            content = f"""> ```ansi
> {sub}No edited messages found in this channel
> ```"""
            return await ctx.send(content)

        if index < 0 or index >= len(edit_snipe_list):
            max_index = len(edit_snipe_list) - 1
            content = f"""> ```ansi
> {main}─── {sub}INVALID INDEX{main} ──────────────────────
> {sub}Please use index between {main}0{sub} and {main}{max_index}
> ```"""
            return await ctx.send(content)

        message = edit_snipe_list[index]
        timestamp = datetime.fromisoformat(message["timestamp"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        edit_time = datetime.fromisoformat(message["edit_time"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{message['author']['username']}#{message['author']['discriminator']}"
        before_content = message["before"] or "*No content before edit*"
        after_content = message["after"] or "*No content after edit*"
        attachments = "\n".join(
    (att.get("url") if isinstance(att, dict) and att.get("url") else str(att))
    for att in message["attachments"]
) or "No attachments"

        response = f"""> ```ansi
> {main}─── {sub}EDIT SNIPE (INDEX: {index}){main} ───
> {sub}Author:{reset}    {main}{author}
> {sub}Edited:{reset}    {main}{edit_time}
> {sub}Before:{reset}    {main}{before_content[:150]}{'...' if len(before_content) > 150 else ''}
> {sub}After:{reset}     {main}{after_content[:150]}{'...' if len(after_content) > 150 else ''}
> {sub}Attachments:{reset} {main}{attachments}
> ```"""

        await ctx.send(response)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.handler.stop()

def setup(bot):
    bot.add_cog(EventsCog(bot))