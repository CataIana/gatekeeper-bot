import discord
from discord.ext import commands, tasks
try:
    from discord.utils import utcnow
except ImportError:
    from datetime import datetime
    utcnow = datetime.utcnow
from aiohttp import ClientSession
import json
import logging
from time import time
import sys
from webserver import RecieverWebServer


class GatekeeperBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True

        # Available status types - Playing/Listening to/Streaming
        activity = discord.Activity(type=discord.ActivityType.playing, name="absolutely nothing")
        #activity = discord.Activity(type=discord.ActivityType.listening, name="absolutely nothing")
        #activity = discord.Activity(type=discord.ActivityType.streaming, name="absolutely nothing")

        super().__init__(command_prefix=commands.when_mentioned_or("!"),
                         case_insensitive=True, intents=intents, activity=activity)

        self.format = logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s')
        self.log_level = logging.DEBUG
        self.log = logging.getLogger("Gatekeeper")
        self.log.setLevel(self.log_level)

        fhandler = logging.FileHandler(
            filename="gatekeeper.log", encoding="utf-8", mode="w+")
        fhandler.setLevel(logging.DEBUG)
        fhandler.setFormatter(logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.log.addHandler(fhandler)

        chandler = logging.StreamHandler(sys.stdout)
        chandler.setLevel(self.log_level)
        chandler.setFormatter(self.format)
        self.log.addHandler(chandler)

        with open("config.json") as f:
            self.config = json.load(f)

        self.web_server = RecieverWebServer(self)
        self.loop.run_until_complete(self.web_server.start())

        self.colour = discord.Colour.from_rgb(128, 0, 128)
        self.bot_token = self.config["bot_token"]
        self.pending_users = []

    async def close(self):
        await self.aSession.close()
        self.log.info("Shutting down...")
        await super().close()

    @tasks.loop(seconds=600)
    async def cleanup_ids(self):
        await self.wait_until_ready()
        self.bot.log.debug("Cleaning up old state cookies")
        deleted = 0
        for state_value in self.web_server.states.keys():
            if (time() - self.web_server.states[state_value]) > 600:
                del self.web_server.states[state_value]
                deleted += 1
        self.bot.log.debug(f"Deleted {deleted} old state cookies")

    async def member_join(self, member: discord.Member):
        if member.guild.id != int(self.config["guild_id"]):
            return
        if not member.pending:
            self.log.debug(f"{member} not pending on join, assigning role")
            role = member.guild.get_role(int(self.config["role_id"]))
            if role is not None and role not in member.roles:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    pass
                await self.log_authorization(member, role_added=True)
            else:
                await self.log_authorization(member)
        else:
            if member.id not in self.pending_users:
                self.pending_users.append(member.id)
            await self.log_authorization(member)

    async def log_authorization(self, member: discord.Member, role_added=False):
        embed = discord.Embed(title="User Verified",
                              colour=self.colour, timestamp=utcnow())
        if discord.__version__ == "2.0.0a":
            embed.set_author(name=member, icon_url=member.display_avatar)
        else:
            embed.set_author(name=member, icon_url=member.avatar_url)
        embed.add_field(name="User", value=f"{member.mention}")
        embed.set_footer(text=f"User ID: {member.id}")
        if member.pending:
            embed.add_field(name="Verified Role Added",
                            value="No, user pending")
        else:
            embed.add_field(name="Verified Role Added",
                            value="Yes" if role_added else "No")
        channel = self.get_channel(self.config.get("log_channel", None))
        if channel is not None:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                self.log.error(
                    "No permissions to send messages in log channel!")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.guild.id != int(self.config["guild_id"]):
            return
        if before.id in self.pending_users:
            if before.pending and not after.pending:
                self.log.debug(
                    f"{before} is no longer pending and is verified, assigning role")
                await self.member_join(after)

    @commands.Cog.listener()
    async def on_ready(self):
        self.aSession = ClientSession()
        self.log.info(
            f"------ Logged in as {self.user.name} - {self.user.id} ------")
        self.log.info(
            f"Invite URL: https://discord.com/oauth2/authorize?client_id={self.user.id}&scope=bot&permissions=268435457")
        self.log.info(f"Gatekeeper URL: {self.config['server_url']}")

    async def on_message(self, message): return


bot = GatekeeperBot()
bot.run(bot.bot_token)
