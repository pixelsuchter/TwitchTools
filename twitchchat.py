from twitchio.ext import commands


class Bot(commands.Bot):
    def __init__(self, token, client_id, nickname, command_prefix, channels_to_join):
        super().__init__(irc_token=token, client_id=client_id, nick=nickname, prefix=command_prefix,
                         initial_channels=channels_to_join)

    async def event_pubsub(self, data):
        pass

    # Events don't need decorators when subclassed
    async def event_ready(self):
        print(f'Ready | {self.nick}')
        self.progress_callback.emit("hello")

    async def event_message(self, message):
        self.progress_callback.emit((message.timestamp, message.author, message.content))
        await self.handle_commands(message)

    # Commands use a decorator...
    @commands.command(name='test')
    async def my_command(self, ctx):
        await ctx.send(f'Hello {ctx.author.name}!')

