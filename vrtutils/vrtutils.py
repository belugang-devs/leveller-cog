import subprocess
from pathlib import Path
from io import StringIO, BytesIO
import json
import datetime
import speedtest
import os
import sys
import platform
import cpuinfo
import logging

import discord
import pkg_resources
import psutil
from redbot.cogs.downloader.repo_manager import Repo
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from typing import Dict, List, Literal, Optional, Tuple, Union, cast
from redbot.core.utils.chat_formatting import (
    bold,
    box,
    escape,
    humanize_list,
    humanize_number,
    humanize_timedelta,
    pagify,
)
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

_ = Translator("VrtUtils", __file__)
log = logging.getLogger("red.vrt.vrtutils")
dpy = discord.__version__
if dpy > "1.7.3":
    DPY2 = True
else:
    DPY2 = False


class VrtUtils(commands.Cog):
    """
    Random utility commands
    """
    __author__ = "Vertyco"
    __version__ = "1.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.LIB_PATH = cog_data_path(self) / "lib"

    # -/-/-/-/-/-/-/-/FORMATTING-/-/-/-/-/-/-/-/
    @staticmethod
    def get_size(num: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
            if abs(num) < 1024.0:
                return "{0:.1f}{1}".format(num, unit)
            num /= 1024.0
        return "{0:.1f}{1}".format(num, "YB")

    @staticmethod
    def get_bitsize(num: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
            if abs(num) < 1000.0:
                return "{0:.1f}{1}".format(num, unit)
            num /= 1000.0
        return "{0:.1f}{1}".format(num, "YB")

    @staticmethod
    def get_bar(progress, total, perc=None, width: int = 20) -> str:
        if perc is not None:
            ratio = perc / 100
        else:
            ratio = progress / total
        bar = "█" * round(ratio * width) + "-" * round(width - (ratio * width))
        return f"|{bar}| {round(100 * ratio)}%"

    # -/-/-/-/-/-/-/-/COMMANDS-/-/-/-/-/-/-/-/
    @commands.command()
    @commands.is_owner()
    async def getlibs(self, ctx):
        """Get all current installed packages on the bots venv"""
        async with ctx.typing():
            packages = [str(p) for p in pkg_resources.working_set]
            packages = sorted(packages, key=str.lower)
            text = ""
            for package in packages:
                text += f"{package}\n"
            embeds = []
            page = 1
            for p in pagify(text):
                embed = discord.Embed(
                    description=box(p)
                )
                embed.set_footer(text=f"Page {page}")
                page += 1
                embeds.append(embed)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def updatelibs(self, ctx):
        """Update all installed packages on the bots venv"""
        async with ctx.typing():
            packages = [dist.project_name for dist in pkg_resources.working_set]
            deps = ' '.join(packages)
            repo = Repo("", "", "", "", Path.cwd())
            async with ctx.typing():
                success = await repo.install_raw_requirements(deps, self.LIB_PATH)

            if success:
                await ctx.send(_("Libraries updated."))
            else:
                await ctx.send(_("Some libraries failed to update. Check your logs for details."))

    @commands.command()
    @commands.is_owner()
    async def pip(self, ctx, *, command: str):
        """Run a pip command"""
        async with ctx.typing():
            command = f"pip {command}"

            def pipexe():
                results = subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8")
                return results

            res = await self.bot.loop.run_in_executor(None, pipexe)
            embeds = []
            page = 1
            for p in pagify(res):
                embed = discord.Embed(
                    title="Packages Updated",
                    description=box(p)
                )
                embed.set_footer(text=f"Page {page}")
                page += 1
                embeds.append(embed)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def findguildbyid(self, ctx, guild_id: int):
        """Find a guild by ID"""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.Forbidden:
                guild = None
        if not guild:
            return await ctx.send(_("Could not find that guild"))
        await ctx.send(_(f"That ID belongs to the guild `{guild.name}`"))

    @commands.command()
    @commands.is_owner()
    async def botstats(self, ctx):
        """
        Get info about the bot

        Inspired by kennnyshiwa's imperialtoolkit botstat command
        https://github.com/kennnyshiwa/kennnyshiwa-cogs
        """
        async with ctx.typing():
            # -/-/-/CPU-/-/-/
            cpu_count = psutil.cpu_count()  # Int
            cpu_perc = await self.bot.loop.run_in_executor(
                None, lambda: psutil.cpu_percent(interval=3, percpu=True)
            )  # List of floats
            cpu_freq = psutil.cpu_freq(percpu=True)  # List of Objects
            cpu_info = cpuinfo.get_cpu_info()  # Dict
            cpu_type = cpu_info["brand_raw"] if "brand_raw" in cpu_info else "Unknown"

            # -/-/-/MEM-/-/-/
            ram = psutil.virtual_memory()  # Obj
            ram_total = self.get_size(ram.total)
            ram_used = self.get_size(ram.used)
            disk = psutil.disk_usage(os.getcwd())
            disk_total = self.get_size(disk.total)
            disk_used = self.get_size(disk.used)

            # -/-/-/NET-/-/-/
            net = psutil.net_io_counters()  # Obj
            sent = self.get_size(net.bytes_sent)
            recv = self.get_size(net.bytes_recv)

            # -/-/-/OS-/-/-/
            if os.name == "nt":
                osdat = platform.uname()
                ostype = f"{osdat.system} {osdat.release} (version {osdat.version})"
            elif sys.platform == "darwin":
                osdat = platform.mac_ver()
                ostype = f"Mac OS {osdat[0]} {osdat[1]}"
            elif sys.platform == "linux":
                import distro
                ostype = f"{distro.name()} {distro.version()}"
            else:
                ostype = "Unknown"

            td = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(psutil.boot_time())
            sys_uptime = humanize_timedelta(timedelta=td)

            # -/-/-/BOT-/-/-/
            servers = "{:,}".format(len(self.bot.guilds))
            shards = self.bot.shard_count
            users = "{:,}".format(len(self.bot.users))
            channels = "{:,}".format(sum(len(guild.channels) for guild in self.bot.guilds))
            emojis = "{:,}".format(len(self.bot.emojis))
            cogs = "{:,}".format(len(self.bot.cogs))
            commandcount = 0
            for cog in self.bot.cogs:
                for __ in self.bot.get_cog(cog).walk_commands():
                    commandcount += 1
            commandcount = "{:,}".format(commandcount)
            td = datetime.datetime.utcnow() - self.bot.uptime
            uptime = humanize_timedelta(timedelta=td)

            # -/-/-/LIBS-/-/-/
            red_version = version_info

            embed = discord.Embed(
                title=_(f"Stats for {self.bot.user.name}"),
                description=_(f"Below are various stats about the bot and the system it runs on."),
                color=await ctx.embed_color()
            )

            botstats = f"Servers:     {servers} ({shards} {'shard' if shards == 1 else 'shards'})\n" \
                       f"Users:       {users}\n" \
                       f"Channels:    {channels}\n" \
                       f"Emojis:      {emojis}\n" \
                       f"Cogs:        {cogs}\n" \
                       f"Commands:    {commandcount}\n" \
                       f"Uptime:      {uptime}\n" \
                       f"Red Version: {red_version}\n" \
                       f"dpy Version: {dpy}"
            embed.add_field(
                name="\N{ROBOT FACE} BOT",
                value=box(_(botstats), lang="python"),
                inline=False
            )

            cpustats = f"CPU:    {cpu_type}\n" \
                       f"Cores:  {cpu_count}\n"
            if len(cpu_freq) == 1:
                cpustats += f"{cpu_freq[0].current}/{cpu_freq[0].max} Mhz\n"
            else:
                for i, obj in enumerate(cpu_freq):
                    maxfreq = f"/{round(obj.max, 2)}" if obj.max else ""
                    cpustats += f"Core {i}: {round(obj.current, 2)}{maxfreq} Mhz\n"
            if isinstance(cpu_perc, list):
                for i, perc in enumerate(cpu_perc):
                    space = " "
                    if i >= 10:
                        space = ""
                    bar = self.get_bar(0, 0, perc)
                    cpustats += f"Core {i}:{space} {bar}\n"
            embed.add_field(
                name="\N{DESKTOP COMPUTER} CPU",
                value=box(_(cpustats), lang="python"),
                inline=False
            )

            rambar = self.get_bar(0, 0, ram.percent, width=30)
            diskbar = self.get_bar(0, 0, disk.percent, width=30)
            memtext = f"RAM ({ram_used}/{ram_total})\n" \
                      f"{rambar}\n" \
                      f"DISK ({disk_used}/{disk_total})\n" \
                      f"{diskbar}"
            embed.add_field(
                name=f"\N{FLOPPY DISK} MEM",
                value=box(memtext, lang="python"),
                inline=False
            )

            netstat = f"Sent:     {sent}\n" \
                      f"Received: {recv}"
            embed.add_field(
                name="\N{SATELLITE ANTENNA} Network",
                value=box(_(netstat), lang="python"),
                inline=False
            )

            if DPY2:
                bot_icon = self.bot.user.avatar.url.format("png")
            else:
                bot_icon = self.bot.user.avatar_url_as(format="png")
            embed.set_thumbnail(url=bot_icon)
            embed.set_footer(text=_(f"System: {ostype}\nUptime: {sys_uptime}"))
            await ctx.send(embed=embed)

    @commands.command()
    async def getuser(self, ctx, *, user_id: Union[int, discord.Member, discord.User]):
        """Find a user by ID"""
        member = await self.bot.get_or_fetch_user(int(user_id))
        since_created = f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
        user_created = f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
        created_on = _(
            f"Joined Discord on {user_created}\n"
            f"({since_created})"
        )
        embed = discord.Embed(
            title=f"{member.name} - {member.id}",
            description=created_on,
            color=await ctx.embed_color()
        )
        if DPY2:
            embed.set_image(url=member.avatar.url)
        else:
            embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def botip(self, ctx):
        """Get the bots public IP address"""
        async with ctx.typing():
            test = speedtest.Speedtest(secure=True)
            embed = discord.Embed(
                title=f"{self.bot.user.name}'s public IP",
                description=test.results.dict()["client"]["ip"]
            )
            await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def usersjson(self, ctx):
        """Get a json file containing all usernames/ID's in this guild"""
        members = {}
        for member in ctx.guild.members:
            members[str(member.id)] = member.name
        iofile = StringIO(json.dumps(members))
        filename = f"users.json"
        file = discord.File(iofile, filename=filename)
        await ctx.send("Here are all usernames and their ID's for this guild", file=file)