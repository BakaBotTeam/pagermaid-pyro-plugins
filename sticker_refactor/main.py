# This plugin is a plugin of Pagermaid-Pyro.
# This file is a part of repo BakaBotTeam/pagermaid-pyro-plugins
# Copyright 2023 Guimc(xiluo@guimc.ltd), the owner of BakaBotTeam, All rights reserved.
import os.path
import tempfile
import traceback
import typing

from PIL import Image
from pyrogram.errors import PeerIdInvalid, RPCError
from pyrogram.file_id import FileId
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.functions.stickers import CreateStickerSet
from pyrogram.raw.types import InputStickerSetShortName, InputStickerSetItem, InputDocument

from pagermaid import bot
from pagermaid.listener import listener
from pagermaid.single_utils import sqlite, Message
from pagermaid.utils import alias_command, pip_install
from pyromod.utils.conversation import Conversation

pip_install("emoji")

import emoji

SUPPORTED_IMAGE_FILE = (".png", ".jpg", ".jpeg", ".bmp", ".cur", ".dcx", ".fli",
                        ".flc", ".fpx", ".gbr", ".gd", ".ico", ".im", ".imt", ".psd")
IMAGE_IMPROVE = Image.LANCZOS


class GeneralError(Exception):
    def __init__(self, msg: str = ""):
        super().__init__(msg)


def get_tempfile(suffix: str = ".png") -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        return f.name


def get_emoji() -> str:
    return sqlite.get("ltd.guimc.sticker_refactor.custom_emoji", "⭐️")


def set_emoji(e: str) -> None:
    sqlite["ltd.guimc.sticker_refactor.custom_emoji"] = e


def is_emoji(content: str) -> bool:
    if content and (u"\U0001F600" <= content <= u"\U0001F64F" or u"\U0001F300" <= content <= u"\U0001F5FF" or
                    u"\U0001F680" <= content <= u"\U0001F6FF" or u"\U0001F1E0" <= content <= u"\U0001F1FF" or
                    emoji.is_emoji(content) or content in ["⭐️", "❌"]):
        return True
    else:
        return False


async def create_sticker_set(name):
    try:
        empty_image = gen_empty_image()
        msgs = await push_file(empty_image)
        if msgs.document is None:
            raise GeneralError()

        file: FileId = FileId.decode(msgs.document.file_id)
        me = await bot.get_me()
        await bot.invoke(
            CreateStickerSet(
                user_id=await bot.resolve_peer(me.id),
                title=f"@{me.username} 的私藏",
                short_name=name,
                stickers=[
                    InputStickerSetItem(
                        document=InputDocument(
                            id=file.media_id,
                            access_hash=file.access_hash,
                            file_reference=file.file_reference
                        ),
                        emoji=get_emoji()
                    )
                ],
                animated=False,
                videos=False,
            )
        )
        await msgs.delete()

    except Exception as e:
        raise GeneralError(f"创建贴纸包失败: {e}") from e


async def check_pack(name: str):
    try:
        if (await bot.invoke(GetStickerSet(
                stickerset=InputStickerSetShortName(short_name=name),
                hash=0
        ))).set.count == 120:
            return False
        return True
    except RPCError as e:
        traceback.print_exception(e)
        await create_sticker_set(name)
        return True


async def generate_sticker_set(time: int = 1) -> str:
    if time >= 20:
        raise GeneralError("尝试了很多次获取可用的贴纸包...但是都失败了. 尝试手动指定一个?")

    me = await bot.get_me()
    if not me.username:
        raise GeneralError("无法获取你的用户名...要不然咱去设置一个?")

    sticker_pack_name = f"{me.username}_{time}"
    if not await check_pack(sticker_pack_name):
        sticker_pack_name = await generate_sticker_set(time + 1)

    return sticker_pack_name


async def easy_ask(msg: typing.List, conv: Conversation):
    for i in msg:
        await conv.ask(i)
        await conv.mark_as_read()


async def add_to_stickers(sticker: Message, e: str):
    await get_sticker_set()  # To avoid some exception
    async with bot.conversation(429000) as conv:
        await easy_ask(["/start", "/cancel", "/addsticker"], conv)

        # Check Sticker pack
        resp: Message = await conv.ask(await get_sticker_set())
        if resp.text == "Invalid set selected.":
            raise GeneralError("无法指定贴纸包,请检查.")
        await conv.mark_as_read()
        await sticker.forward(429000)
        resp: Message = await conv.get_response()
        await conv.mark_as_read()
        if not resp.text.startswith("Thanks!"):
            await easy_ask(["/cancel"], conv)
            raise GeneralError(f"无法添加贴纸, @Stickers 回复:\n{resp.text}")
        await easy_ask([e, "/done", "/done"], conv)


async def download_photo(msg: Message) -> str:
    try:
        filename = get_tempfile()
        await bot.download_media(msg, filename)
        return filename
    except Exception as e:
        raise GeneralError("下载媒体失败.") from e


async def download_sticker(msg: Message) -> str:
    try:
        filename = get_tempfile(".webp")
        await bot.download_media(msg, filename)
        return filename
    except Exception as e:
        raise GeneralError("下载媒体失败.") from e


def convert_image(imgfile: str) -> str:
    try:
        img = Image.open(imgfile)
        width, height = img.size

        if (width >= 512 or height >= 512) or (width <= 512 and height <= 512):
            scaling = height / width

            if scaling <= 1:
                img = img.resize((512, int(512 * scaling)), IMAGE_IMPROVE)
            else:
                img = img.resize((int(512 / scaling), 512), IMAGE_IMPROVE)
        img.save(imgfile + "_patched.png")

        return imgfile + "_patched.png"
    except Exception as e:
        raise GeneralError(f"在转换图片时出现了错误 {e}") from e


async def push_file(imgfile: str) -> Message:
    try:
        me = await bot.get_me()

        async with bot.conversation(me.id) as conv:
            with open(imgfile, "rb") as f:
                msg = await conv.send_document(f, file_name=f"{os.path.basename(imgfile)}")

        return msg
    except Exception as e:
        raise GeneralError("上传文件失败.") from e


def get_custom_sticker() -> str | None:
    return sqlite.get("sticker_set", None)


def set_custom_sticker(name: str):
    sqlite["sticker_set"] = name


def del_custom_sticker():
    try:
        del sqlite["sticker_set"]
    except NameError as e:
        raise GeneralError("你好像没有设置自定义贴纸包.") from e


def gen_empty_image() -> str:
    filename = get_tempfile()
    Image.new("RGB", (512, 512), (0, 0, 0)).save(filename)

    return filename


async def get_sticker_set() -> str:
    sticker_pack_name = get_custom_sticker()

    if not sticker_pack_name or not await check_pack(sticker_pack_name):
        sticker_pack_name = await generate_sticker_set()
        set_custom_sticker(sticker_pack_name)
    return sticker_pack_name


async def download_document(msg: Message):
    try:
        filename = get_tempfile()
        await bot.download_media(msg, filename)
        return filename
    except Exception as e:
        raise GeneralError("下载文件失败.") from e


async def file2sticker(filename, e: str):
    # Convert Image file
    converted_filename = convert_image(filename)
    # print(filename, converted_filename)
    msgs = await push_file(converted_filename)

    # Cleanup
    await add_to_stickers(msgs, e)
    await msgs.delete()
    os.remove(converted_filename)
    os.remove(filename)


@listener(
    command="sr",
    parameters="[贴纸包名/cancel]",
    description="保存贴纸/照片到自己的贴纸包 但是重构",
    need_admin=True
)
async def sticker_refactor(msg: Message):
    try:
        if msg.reply_to_message:
            _emoji = get_emoji()

            if msg.reply_to_message.sticker and msg.reply_to_message.sticker.emoji is not None:
                _emoji = msg.reply_to_message.sticker.emoji

            if len(msg.parameter) == 1 and is_emoji(msg.arguments):
                _emoji = msg.arguments

            # check target type
            if msg.reply_to_message.sticker:
                await file2sticker(await download_sticker(msg.reply_to_message), _emoji)
            elif msg.reply_to_message.photo:
                await file2sticker(await download_photo(msg.reply_to_message), _emoji)
            elif msg.reply_to_message.document:
                document = msg.reply_to_message.document
                if not document.file_name.endswith(SUPPORTED_IMAGE_FILE):
                    raise GeneralError("不支持的文件类型.")

                await file2sticker(await download_document(msg.reply_to_message), _emoji)
            else:
                raise GeneralError("找不到可以转换的贴纸/图片,请检查.")
            await msg.edit("✅ 成功添加到贴纸包 [{0}](https://t.me/addstickers/{0})"
                           .format(await get_sticker_set()))
        else:
            if len(msg.parameter) == 1:
                if is_emoji(msg.arguments):
                    set_emoji(msg.arguments)
                    await msg.edit("✅ 成功设置Emoji")
                elif len(msg.arguments) >= 5:
                    # Sticker Pack name
                    if msg.arguments == "cancel":
                        del_custom_sticker()
                        await msg.edit("✅ 成功清除贴纸包")
                    else:
                        set_custom_sticker(msg.arguments)
                        await msg.edit("✅ 成功设置贴纸包")
                else:
                    await msg.edit("❌ 贴纸包名称长度不能小于5！")
            else:
                await msg.edit(f"""👋 Hi! 感谢使用 Sticker (重构版) 插件!
请直接回复你想要添加的贴纸/图片 来保存到你的贴纸包!
可使用 <code>,{alias_command('sr')} 贴纸包名</code> 来自定义目标贴纸包 (若留cancel 则重置)
可使用 <code>,{alias_command('sr')} emoji</code> 来自定义默认emoji
目前使用的贴纸包为 {await get_sticker_set()}, 目前的默认 Emoji 为 {get_emoji()}
Made by BakaBotTeam@GitHub with ❤""")
    except PeerIdInvalid:
        await msg.edit("❌ 无法打开与 @Stickers 的对话 试试先与其私聊一次?")
    except GeneralError as e:
        await msg.edit(f"❌ 在处理时发生了错误: {e}")
