from aiohttp import web
from asyncio import sleep
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bot import GatekeeperBot


class RecieverWebServer():
    def __init__(self, bot):
        self.bot: GatekeeperBot = bot
        self.port = 3824
        self.discord_url = "https://discord.com/api"
        self.web_server = web.Application()
        #self.web_server.add_routes([web.route('*', '/', self.main)])
        self.web_server.add_routes([web.route('*', '/authorize', self.authorize)])
        #self.web_server.add_routes([web.route('*', '/done', self.success)])
        #self.web_server.add_routes([web.route('*', '/error', self.error)])
        #self.web_server.add_routes([web.static('/', "html")])

    @staticmethod
    def index_factory(path, filename):
        async def static_view(request):
            # prefix not needed
            route = web.StaticRoute(None, '/', path)
            request.match_info['filename'] = filename
            return await route.handle(request)
        return static_view

    async def start(self):
        runner = web.AppRunner(self.web_server)
        await runner.setup()
        await web.TCPSite(runner, host="localhost", port=self.port).start()
        self.bot.log.info(f"Webserver running on localhost:{self.port}")
        return self.web_server

    #Commented stuff below allows aiohttp to serve the static pages. This is slow, so we used nginx

    # async def main(self, request):
    #     return web.FileResponse("html/index.html")

    # async def success(self, request):
    #     return web.FileResponse("html/done.html")

    # async def error(self, request):
    #     await self.bot.wait_until_ready()
    #     return web.FileResponse("html/error.html")

    async def authorize(self, request):
        await self.bot.wait_until_ready()

        #Check if user needs to be redirected so a code can be aquired
        if request.query.get("code-required", "false") == "true":
            scopes = "identify guilds.join guilds"
            url = f"https://discord.com/oauth2/authorize?client_id={self.bot.config['client_id']}&redirect_uri={self.bot.config['server_url']}/authorize&response_type=code&scope={scopes}"
            return web.HTTPSeeOther(url)

        #Discord errors return here, redirect to error page if this is the case
        if request.query.get("error", None) is not None:
            err_code = request.query.get("error", "")
            error_description = request.query.get("error_description", "")
            self.bot.log.warning(f"Discord returned error {err_code}: {error_description}")
            return web.HTTPSeeOther(f"{self.bot.config['server_url']}/error?error={err_code}&error_description={error_description}")

        # Get oauth code
        if request.query.get("code", None) is None:
            self.bot.log.debug("No code provided, ignoring")
            return web.Response(body="No code provided", status=400)
        else:
            oauth = request.query.get("code", None)
        self.bot.log.debug(f"Oauth2 code: {oauth}")
        # Get access token
        data = {
            "client_id": self.bot.config["client_id"],
            "client_secret": self.bot.config["client_secret"],
            "grant_type": "authorization_code",
            "code": oauth,
            "redirect_uri": f'{self.bot.config["server_url"]}/authorize'
        }

        r = await self.bot.aSession.post(f"{self.discord_url}/oauth2/token", headers={"Content-Type": "application/x-www-form-urlencoded"}, data=data)
        token = await r.json()
        if token.get("error", None) is not None:
            self.bot.log.error(f"Error authorising: {token['error_description']}")
            err_code = ""
            error_description = "Invalid authorization code"
            return web.HTTPSeeOther(f"{self.bot.config['server_url']}/error?error={err_code}&error_description={error_description}")
        self.bot.log.debug(f"Token data: {token}")

        # #Get User Information, mainly ID
        r = await self.bot.aSession.get(f"{self.discord_url}/users/@me", headers={"Authorization": f"Bearer {token['access_token']}"})
        user = await r.json()
        self.bot.log.debug(f"User Details: {user}")

        g = self.bot.get_guild(int(self.bot.config["guild_id"]))
        if g is None:
            self.bot.log.error("Failed to get guild object")
            err_code = ""
            error_description = "Unable to get guild"
            return web.HTTPSeeOther(f"{self.bot.config['server_url']}/error?error={err_code}&error_description={error_description}")
        
        member = g.get_member(int(user['id']))
        if member is None: #Assume user is not in guild if member object is None
            # #Join Guild
            self.bot.log.debug(f"Member object returned none assuming user {user['username']}{user['discriminator']} not in guild, joining them")
            url = f"{self.discord_url}/v8/guilds/{self.bot.config['guild_id']}/members/{user['id']}"
            headers = {"Authorization": f"Bot {self.bot.config['bot_token']}"}
            self.bot.log.debug(
                f"Joining user {user['username']}{user['discriminator']} ({user['id']})")
            data = {"access_token": token["access_token"]}
            response = await self.bot.aSession.put(url, headers=headers, json=data)
            join_json = await response.json()
            self.bot.log.debug(join_json)
            if join_json.get("message", None) is not None:
                err_code = join_json["code"]
                error_description = join_json["message"]
                return web.HTTPSeeOther(f"{self.bot.config['server_url']}/error?error={err_code}&error_description={error_description}")
            await sleep(1)
            member = g.get_member(int(user['id']))
            if int(user["id"]) not in self.bot.pending_users and member.pending:
                self.bot.pending_users.append(int(user["id"]))
            await self.bot.member_join(member)
            return web.HTTPSeeOther(f"{self.bot.config['server_url']}/done")
        else:
            self.bot.log.debug(f"{user['username']}{user['discriminator']} in guild already, assigning role")
            await self.bot.member_join(member)
            return web.HTTPSeeOther(f"{self.bot.config['server_url']}/done")
