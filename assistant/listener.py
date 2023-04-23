import logging

import discord
from openai.error import InvalidRequestError
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta

log = logging.getLogger("red.vrt.assistant.listener")


class AssistantListener(MixinMeta):
    @commands.Cog.listener("on_message_without_command")
    async def handler(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Ignore messages without content
        if not message.content:
            return
        # Ignore if channel doesn't exist
        if not message.channel:
            return
        # Ignore references to other members
        if hasattr(message, "reference"):
            ref = message.reference.resolved
            if ref and ref.author.id != self.bot.user.id:
                return

        conf = self.db.get_conf(message.guild)
        if not conf.enabled:
            return
        if not conf.api_key:
            return
        channel = message.channel
        if channel.id != conf.channel_id:
            return
        content = message.content
        mentions = [member.id for member in message.mentions]
        if (
            not content.endswith("?")
            and conf.endswith_questionmark
            and self.bot.user.id not in mentions
        ):
            return
        if len(content.strip()) < conf.min_length:
            return
        async with channel.typing():
            try:
                reply = await self.get_chat_response(
                    content, message.author, conf
                )
                parts = [p for p in pagify(reply, page_length=2000)]
                for index, p in enumerate(parts):
                    if not index:
                        await message.reply(p, mention_author=conf.mention)
                    else:
                        await message.channel.send(p)
            except InvalidRequestError as e:
                if error := e.error:
                    await message.reply(
                        error["message"], mention_author=conf.mention
                    )
            except Exception as e:
                await message.channel.send(f"**Error**\n```py\n{e}\n```")