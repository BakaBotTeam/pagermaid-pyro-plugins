import contextlib

from pagermaid.enums import Message, Client
from pagermaid.listener import listener


@listener(incoming=False, outgoing=True)
async def auto_del_cmd(message: Message):
    with contextlib.suppress(Exception):
        if message.text and message.text.strip().startswith("/"):
                await message.delete()