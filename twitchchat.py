import asyncio
import time
from typing import List

import twitchio
from twitchio.ext import commands

mod_timeout = 0.4
non_mod_timeout = 1.7


class Bot(commands.Bot):
    def __init__(self, token, client_id, nickname, command_prefix, channels_to_join, message_timeout=non_mod_timeout):
        self.eventloop = asyncio.get_event_loop()
        self.message_timeout = message_timeout
        super().__init__(irc_token=f"oauth:{token}", client_id=client_id, nick=nickname, prefix=command_prefix,
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
        self.progress_callback.emit(message)
        # await self.handle_commands(message)

    async def _ban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        chnl: twitchio.dataclasses.Channel = self.get_channel(channel)
        num_of_names_to_ban = len(namelist)
        for num, name in enumerate(namelist):
            await chnl.ban(name)
            if progress_callback:
                progress_callback.emit(f"Banned {num} out of {num_of_names_to_ban} Users")
            await asyncio.sleep(self.message_timeout)
        if progress_callback:
            progress_callback.emit(f"Done")

    def ban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        task = self.loop.create_task(self._ban_namelist(channel, namelist, progress_callback))
        while not task.done():
            time.sleep(2)

    async def _unban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        chnl = self.get_channel(channel)
        num_of_names_to_unban = len(namelist)
        for num, name in enumerate(namelist):
            await chnl.unban(name)
            print(f"unbanned {name} in channel {channel}")
            if progress_callback:
                progress_callback.emit(f"Unbanned {num} out of {num_of_names_to_unban} Users")
            await asyncio.sleep(self.message_timeout)
        if progress_callback:
            progress_callback.emit(f"Done")

    def unban_namelist(self, channel: str, namelist: List[str], progress_callback=None):
        task = self.loop.create_task(self._unban_namelist(channel, namelist, progress_callback))
        while not task.done():
            time.sleep(2)
