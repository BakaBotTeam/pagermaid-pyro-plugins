'''speedtest 测速Version3.0'''
import os
import json
import tarfile
import requests
import subprocess

from pagermaid.listener import listener
from pagermaid.enums import Client, Message, AsyncClient
from pagermaid.utils import lang

plugins_dir = os.path.abspath(os.path.dirname(__file__))
speedtest = os.path.join(plugins_dir, "speedtest")
def convert_size(b, suffix="B", factor=1024):
    for unit in ["", "K", "M", "G", "T", "P"]:
        if b < factor:
            return f'{b:.2f}{unit}{suffix}'
        b /= factor

def is_json(content):
    try:
        json.loads(content)
    except:
         return False
    return True

@listener(command="spt",
          need_admin=True,
          description=lang('speedtest_des'),
          parameters="(list/server id)")
async def spt(client: Client, message: Message) -> None:
    """
使用示例:
1、测速:`spt`
2、获取服务器:`spt list`
3、指定服务器测速:`spt <服务器 id>`
"""
    edit_message = await message.edit('正在运行中...')
    chat_id = message.chat.id    
    args = message.text.strip().split()
    arg = args[1] if len(args) > 1 else None

    async def sptest():
        await edit_message.edit(f'Speedtest测速中...')
        command = [speedtest, "--format=json-pretty", "--progress=no", "--accept-license", "--accept-gdpr"]
        command.append(f"--server-id={arg}")
        try:
            output = subprocess.check_output(command)
        except Exception as e:
            output = e
        return output

    if not os.path.exists(speedtest):
        await edit_message.edit("下载 speedtest 中...")
        arch = os.uname().machine
        url = f'https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-{arch}.tgz'
        try:
            with requests.Session() as s:
                r = s.get(url)
            if r.ok:
                with open(f'{speedtest}.tgz', "wb") as f:
                    f.write(r.content)
                tar = tarfile.open(f'{speedtest}.tgz', "r:*")
                tar.extract("speedtest", path=plugins_dir)
        except:
            await edit_message.edit("下载 speedtest 失败~")

    if os.path.exists(speedtest):
        if arg == 'list':
            await edit_message.edit(f'获取服务器中...')
            command = [speedtest, "-L", "--format=json-pretty", "--accept-license", "--accept-gdpr"]
            try:
                output = subprocess.check_output(command)
            except Exception as e:
                await edit_message.edit(f'获取服务器失败...')
            else:
                content = "**SPEEDTEST 服务器列表**\n\n"
                servers = json.loads(output)["servers"]
                for s in servers:
                    content += f"▪️ `{s['id']}`: `{s['name']} - {s['location']} {s['country']}`\n"
                await edit_message.edit(content)
        else:
            output = await sptest()
            if not is_json(output):
                return await edit_message.edit(f'测速失败...\n{output}')
            data = json.loads(output)
            await message.delete()
            content = (
                f"**🎸Speedtest测速结果**\n"
                f"下载速度:{convert_size(data['download']['bandwidth'], suffix='B/s')} ~ {convert_size(data['download']['bytes'], suffix='B', factor=1000)}\n"
                f"上传速度:{convert_size(data['upload']['bandwidth'], suffix='B/s')} ~ {convert_size(data['upload']['bytes'], suffix='B', factor=1000)}\n"
                f"延迟:{data['ping']['latency']}ms  抖动:{data['ping']['jitter']}\n"
                f"测速点:{data['isp']}\n"
                f"服务商:{data['server']['name']} ㉿ {data['server']['location']} {data['server']['country']}\n"
            )
            await client.send_photo(
                chat_id,
                photo=f"{data['result']['url']}.png",
                caption=content
            )