# This plugin is a plugin of Pagermaid-Pyro.
# This file is a part of repo BakaBotTeam/pagermaid-pyro-plugins
# Copyright 2023 Guimc(xiluo@guimc.ltd), the owner of BakaBotTeam, All rights reserved.
import contextlib
import traceback
import requests
import io, base64, os, time, json

import os.path
import tempfile
import typing

from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.functions.stickers import CreateStickerSet
from pyrogram.raw.types import InputStickerSetShortName, InputStickerSetItem, InputDocument

from pagermaid.services import bot, sqlite
from pagermaid.utils import alias_command, pip_install
from pyromod.utils.conversation import Conversation

from PIL import Image, features
from pyrogram.enums import MessageEntityType
from pyrogram.errors import Flood, PeerIdInvalid, RPCError
from pyrogram.file_id import FileId
from pyrogram.errors.exceptions.bad_request_400 import ChatForwardsRestricted

from pagermaid.listener import listener
from pagermaid.enums import Client, Message

pip_install("emoji")
pip_install("opencv-python", alias="cv2")

import emoji
import cv2


BASE_API_URL = "https://quotly.sbcnm.tech/generate"
IMAGE_IMPROVE = Image.LANCZOS

SUPPORTED_IMAGE_FILE = (".png", ".jpg", ".jpeg", ".bmp", ".cur", ".dcx", ".fli",
                        ".flc", ".fpx", ".gbr", ".gd", ".ico", ".im", ".imt", ".psd", ".webp")


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
        await conv.send_message(i)  # what will happen if i just send message?
        # await conv.mark_as_read()
    # just avoid some exception
    time.sleep(.5)
    await conv.mark_as_read()


async def add_to_stickers(sticker: Message, e: str):
    await get_sticker_set()  # To avoid some exception
    async with bot.conversation(429000) as conv:
        await easy_ask(["/start", "/cancel", "/addsticker"], conv)

        # Check Sticker pack
        resp: Message = await conv.ask(await get_sticker_set())
        if resp.text == "Invalid set selected.":
            raise GeneralError("无法指定贴纸包,请检查.")
        # await conv.mark_as_read()
        await sticker.forward(429000)
        resp: Message = await conv.get_response()
        # await conv.mark_as_read()
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

        if max(img.width, img.height) != 512:
            scaling = height / width

            if scaling <= 1:
                img = img.resize((512, int(512 * scaling)), IMAGE_IMPROVE)
            else:
                img = img.resize((int(512 / scaling), 512), IMAGE_IMPROVE)
        img.save(imgfile + "_patched.png")

        return imgfile + "_patched.png"
    except KeyError as e:
        if not features.check_module('webp'):
            raise GeneralError(f"转换图片失败: {e}\n我们发现您的PIL库缺少WebP支持 您可以参考[此处](https://stackoverflow.com/questions/19860639/convert-images-to-webp-using-pillow)来解决你的问题") from e
        else:
            raise GeneralError(f"转换图片失败: {e}") from e
    except OSError as e:
        if not features.check_module('webp'):
            raise GeneralError(f"转换图片失败: {e}\n我们发现您的PIL库缺少WebP支持 您可以参考[此处](https://stackoverflow.com/questions/19860639/convert-images-to-webp-using-pillow)来解决你的问题") from e
        else:
            raise GeneralError(f"转换图片失败: {e}") from e
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


async def get_quotly_image_file(bot: Client, message: Message):
    if not message.reply_to_message:
        return await message.edit("你需要回复一条消息。")
    await message.edit("让我看看！")
    messages = []
    fetched = 0
    limit = 1
    # if message.parameter:
        # try:
            # limit = int(message.parameter[0])
        # except:
            # pass
    async for msg in bot.get_chat_history(
        chat_id=message.reply_to_message.chat.id
    ):
        if msg.empty:
            continue
        if not msg.from_user and not msg.sender_chat:
            if msg.id == message.reply_to_message.id:
                await message.edit("你回复的消息好奇怪... 我没法处理它喵")
                raise Exception()
            continue
        if msg.id != message.reply_to_message.id and fetched == 0:
            continue
        
        from_user_data = {}
        if msg.from_user:
            from_user = msg.from_user
            from_user_data["id"] = from_user.id
            if from_user.first_name:
                from_user_data["first_name"] = from_user.first_name
            if from_user.last_name:
                from_user_data["last_name"] = from_user.last_name
            if from_user.username:
                from_user_data["username"] = from_user.username
            if from_user.photo:
                img_bytesio = await bot.download_media(from_user.photo.big_file_id, in_memory=True)
                img = Image.open(img_bytesio)
                rfile_name = str(time.time()) + ".png"
                img.save(rfile_name)
                fed_message = await bot.send_document("baka_quotly_helper_bot", rfile_name)
                os.remove(rfile_name)
                from_user_data["photo"] = {
                    "big_file_id": fed_message.document.file_id,
                }
            if from_user.emoji_status and from_user.emoji_status.custom_emoji_id:
                from_user_data["emoji_status"] = str(from_user.emoji_status.custom_emoji_id)
        elif msg.sender_chat:
            from_user = msg.sender_chat
            from_user_data["id"] = from_user.id
            if from_user.title:
                from_user_data["first_name"] = from_user.title
            else:
                if from_user.first_name:
                    from_user_data["first_name"] = from_user.first_name
                if from_user.last_name:
                    from_user_data["last_name"] = from_user.last_name
            if from_user.username:
                from_user_data["username"] = from_user.username
            if from_user.photo:
                img_bytesio = await bot.download_media(from_user.photo.big_file_id, in_memory=True)
                img = Image.open(img_bytesio)
                rfile_name = str(time.time()) + ".png"
                img.save(rfile_name)
                fed_message = await bot.send_document("baka_quotly_helper_bot", rfile_name)
                os.remove(rfile_name)
                from_user_data["photo"] = {
                    "big_file_id": fed_message.document.file_id,
                }
        else:
            continue
        
        message_data = {
            "from": from_user_data,
        }
        if msg.text:
            message_data["text"] = msg.text
        elif msg.caption:
            message_data["text"] = msg.caption
        if msg.entities:
            entities_data = []
            for entity in msg.entities:
                entity_data = {
                    "offset": entity.offset,
                    "length": entity.length,
                }
                if entity.type == MessageEntityType.BOLD:
                    entity_data["type"] = "bold"
                elif entity.type == MessageEntityType.ITALIC:
                    entity_data["type"] = "italic"
                elif entity.type == MessageEntityType.CODE:
                    entity_data["type"] = "code"
                elif entity.type == MessageEntityType.URL:
                    entity_data["type"] = "text_link"
                    entity_data["url"] = entity.url
                elif entity.type == MessageEntityType.CUSTOM_EMOJI:
                    entity_data["type"] = "custom_emoji"
                    entity_data["custom_emoji_id"] = str(entity.custom_emoji_id)
                elif entity.type == MessageEntityType.UNDERLINE:
                    entity_data["type"] = "underline"
                elif entity.type == MessageEntityType.STRIKETHROUGH:
                    entity.data["type"] = "strikethrough"
                elif entity.type == MessageEntityType.CODE:
                    entity.data["type"] = "code"
                else:
                    continue
                    
                entities_data.append(entity_data)
            message_data["entities"] = entities_data
        if msg.sticker:
            rfile_name = await bot.download_media(msg.sticker)
            if rfile_name.endswith(".tgs"):
                await message.edit("咱不支持 tgs 格式的贴纸…")
                raise Exception()
            if rfile_name.endswith(".webm"):
                orig_file = rfile_name
                cap = cv2.VideoCapture(orig_file)
                
                if not cap.isOpened():
                    await message.edit("好奇怪的 webm 贴纸… 咱打不开.")
                    raise Exception()
                
                ret, frame = cap.read()
                
                if ret:
                    rfile_name = str(time.time()) + ".png"
                    cv2.imwrite(rfile_name, frame)
                else:
                    await message.edit("好奇怪的 webm 贴纸… 咱没法从里面提取帧")
                    raise Exception()
                
                cap.release()
                os.remove(orig_file)
            fed_message = await bot.send_document("baka_quotly_helper_bot", rfile_name)
            os.remove(rfile_name)
            message_data["media"] = [{
                "file_id": fed_message.document.file_id,
                "width": msg.sticker.width,
                "height": msg.sticker.height
            }]
            message_data["mediaType"] = "sticker"
        if msg.photo:
            rfile_name = await bot.download_media(msg.photo)
            fed_message = await bot.send_document("baka_quotly_helper_bot", rfile_name)
            os.remove(rfile_name)
            message_data["media"] = [{
                "file_id": fed_message.document.file_id,
                "width": msg.photo.width,
                "height": msg.photo.height
            }]
            message_data["mediaType"] = "photo"
        if msg.voice:
            message_data["voice"] = { "waveform": list(msg.voice.waveform) }
        message_data["avatar"] = True
        messages.append(message_data)
        fetched += 1
        if fetched >= limit:
            break
    if not messages:
        await message.edit("咱没有找到可用的消息喵")
        raise Exception()
    messages.reverse()
    last_userid = -1
    for i in range(len(messages)):
        if messages[i]["from"]["id"] == last_userid:
            messages[i]["avatar"] = False
            messages[i]["from"]["first_name"] = ""
            messages[i]["from"]["last_name"] = ""
            try:
                messages[i]["from"]["emoji_status"]
            except:
                pass
        last_userid = messages[i]["from"]["id"]
    no_edit_flag = False
    try:
        bodys = json.dumps({
            "messages": messages,
            "type": "quote"
        })
        response = requests.post(
            BASE_API_URL,
            data=bodys,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
                "Content-Type": "application/json"
            }
        )
        try:
            data = response.json()
            if data.get("error"):
                await message.edit(f"生成失败了... 错误信息: {data['error']}")
                no_edit_flag = True
                raise Exception()
            if not data["result"].get("image"):
                await message.edit("生成失败了... 服务器没有返回图片, 可能是因为消息太长了?")
                no_edit_flag = True
                raise Exception()
            if response.status_code != 200:
                await message.edit("呜呜, 生成失败了... 等下再试试吧? 服务器返回的状态看起来不是很正常...")
                no_edit_flag = True
                raise Exception()
            image_data = data["result"]["image"]
            image_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size

            if max(img.width, img.height) != 512:
                scaling = height / width
    
                if scaling <= 1:
                    img = img.resize((512, int(512 * scaling)), IMAGE_IMPROVE)
                else:
                    img = img.resize((int(512 / scaling), 512), IMAGE_IMPROVE)
            rfile_name = str(time.time()) + ".webp"
            img.save(rfile_name)
            return rfile_name
        except:
            print(response.text)
            raise
    except:
        if not no_edit_flag:
            await message.edit("出了一些小问题... 看看控制台的报错吧 (=・ω・=)")
        raise


@listener(command="q", description="将回复的消息转换成语录")
async def quote(bot: Client, message: Message):
    try:
        rfile_name = await get_quotly_image_file(bot, message)
        with contextlib.suppress(Flood, ChatForwardsRestricted):
            await bot.send_sticker(
                chat_id=message.chat.id,
                sticker=rfile_name,
                reply_to_message_id=message.reply_to_message.id
            )
        os.remove(rfile_name)
    except:
        traceback.print_exc()


@listener(command="qs", description="将回复的消息转换成语录, 并自动添加到贴纸包 (来自 sticker_refactor)")
async def quotes(bot: Client, message: Message):
    try:
        rfile_name = await get_quotly_image_file(bot, message)
        _emoji = get_emoji()
        await file2sticker(rfile_name, _emoji)
        await message.edit("✅ 成功添加到贴纸包 [{0}](https://t.me/addstickers/{0})"
                           .format(await get_sticker_set()))
    except:
        traceback.print_exc()