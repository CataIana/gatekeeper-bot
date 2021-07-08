from discord import Intents, Colour, Activity, ActivityType, Embed, Forbidden
from aiohttp import ClientSession
from discord.ext import commands
from aiohttp import ClientSession
import json
import logging
from datetime import datetime
import sys
from webserver import RecieverWebServer


class GatekeeperBot(commands.Bot):
    def __init__(self):
        intents = Intents.none()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), case_insensitive=True, intents=intents)

        self.format = logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s: %(message)s')
        self.log_level = logging.INFO
        self.log = logging.getLogger("Gatekeeper")
        self.log.setLevel(self.log_level)

        fhandler = logging.FileHandler(filename="gatekeeper.log", encoding="utf-8", mode="w+")
        fhandler.setLevel(logging.WARNING)
        fhandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        self.log.addHandler(fhandler)

        chandler = logging.StreamHandler(sys.stdout)
        chandler.setLevel(self.log_level)
        chandler.setFormatter(self.format)
        self.log.addHandler(chandler)

        with open("config.json") as f:
            self.config = json.load(f)

        self.web_server = RecieverWebServer(self)
        self.loop.run_until_complete(self.web_server.start())

        self.colour = Colour.from_rgb(128, 0, 128)
        self.bot_token = self.config["bot_token"]
        self.pending_users = []

    async def close(self):
        await self.aSession.close()
        self.log.info("Shutting down...")
        await super().close()

    async def member_join(self, member):
        if member.guild.id != int(self.config["guild_id"]):
            return
        if not member.pending:
            self.log.debug(f"{member} not pending on join, assigning role")
            role = member.guild.get_role(int(self.config["role_id"]))
            if role is not None and role not in member.roles:
                await member.add_roles(role)
                await self.log_authorization(member, role_added=True)
            else:
                await self.log_authorization(member)
        else:
            if member.id not in self.pending_users:
                self.pending_users.append(member.id)
            await self.log_authorization(member)

    async def log_authorization(self, member, role_added=False):
        embed = Embed(title="User Authorized", colour=self.colour, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member.mention} ({member})")
        if role_added:
            embed.add_field(name="Verified Role Added", value=role_added)
        elif member.pending:
            embed.add_field(name="Verified Role Added", value="False, user still pending")
        else:
            embed.add_field(name="Verified Role Added", value=role_added)
        channel = self.get_channel(self.config.get("log_channel", None))
        if channel is not None:
            try:
                await channel.send(embed=embed)
            except Forbidden:
                self.log.error("No permissions to send messages in log channel!")
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.guild.id != int(self.config["guild_id"]):
            return
        if before.id in self.pending_users:
            if before.pending and not after.pending:
                self.log.debug(f"{before} is no longer pending and is verified, assigning role")
                await self.member_join(after)

    @commands.Cog.listener()
    async def on_ready(self):
        self.aSession = ClientSession()
        self.log.info(f"------ Logged in as {self.user.name} - {self.user.id} ------")
        self.log.info(f"Invite URL: https://discord.com/oauth2/authorize?client_id={self.user.id}&scope=bot&permissions=268435457")
        self.log.info(f"Gatekeeper URL: {self.config['server_url']}")
        #Available status types - Playing/Listening to/Streaming
        #await self.change_presence(activity=Activity(type=ActivityType.playing, name="absolutely nothing"))
        ##await self.change_presence(activity=Activity(type=ActivityType.listening, name="absolutely nothing"))
        await self.change_presence(activity=Activity(type=ActivityType.streaming, name="absolutely nothing"))

    async def on_message(self, message): return


bot = GatekeeperBot()
bot.run(bot.bot_token)