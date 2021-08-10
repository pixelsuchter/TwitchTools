import asyncio
import time
from typing import List

from twitchio.ext import commands

chat_timeout = 0.4


class Bot(commands.Bot):
    def __init__(self, token, client_id, nickname, command_prefix, channels_to_join):
        self.eventloop = asyncio.get_event_loop()
        super().__init__(irc_token=token, client_id=client_id, nick=nickname, prefix=command_prefix,
                         initial_channels=channels_to_join, loop=self.eventloop)

    def stop_loop(self):
        for task in asyncio.Task.all_tasks():
            task.cancel()

    async def event_pubsub(self, data):
        pass

    # Events don't need decorators when subclassed
    async def event_ready(self):
        print(f'Ready | {self.nick}')
        self.progress_callback.emit("hello")

    async def event_message(self, message):
        # self.progress_callback.emit((message.timestamp, message.author, message.content))
        await self.handle_commands(message)

    async def _ban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        chnl = self.get_channel(channel)
        num_of_names_to_ban = len(namelist)
        for num, name in enumerate(namelist):
            await chnl.ban(name)
            if progress_callback:
                progress_callback.emit(f"Banned {num} out of {num_of_names_to_ban} Users")
            await asyncio.sleep(chat_timeout)

    def ban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        task = self.loop.create_task(self._ban_namelist(channel, namelist, progress_callback))
        while not task.done():
            time.sleep(2)
