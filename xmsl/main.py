import contextlib

from pagermaid.enums import Message, Client
from pagermaid.listener import listener


@listener(
    command="xm",
    need_admin=True,
    description=f"羡慕死了！"
    )
async def xmsl(message: Message):
    with contextlib.suppress(Exception):
        if message.arguments:
            await message.edit(f"羡慕{message.arguments}！")
        else:
            await message.edit("羡慕死了！")