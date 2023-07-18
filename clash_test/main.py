# This plugin is a plugin of Pagermaid-Pyro.
# This file is a part of repo BakaBotTeam/pagermaid-pyro-plugins
# Copyright 2023 Guimc(xiluo@guimc.ltd), the owner of BakaBotTeam, All rights reserved.
import threading
import time

from requests import Response

from pagermaid.listener import listener
from pagermaid.single_utils import Message, sqlite
from pagermaid.utils import pip_install, alias_command
from urllib.parse import quote

pip_install("requests")

import requests


def get_url() -> str | None:
    url: str | None = sqlite.get("ltd.guimc.clash_test.url", None)
    if url and not url.endswith("/"):
        return f"{url}/"
    else:
        return url


def set_url(e: str) -> None:
    sqlite["ltd.guimc.clash_test.url"] = e


def get_secret() -> str | None:
    return sqlite.get("ltd.guimc.clash_test.secret", None)


def set_secret(e: str) -> None:
    sqlite["ltd.guimc.clash_test.secret"] = e


def urlget(url: str) -> Response:
    if get_secret():
        header = {"Authorization": f"Bearer {get_secret()}"}
    else:
        header = {}

    return requests.get(get_url() + url, headers=header)


def get_proxies() -> list[str] | None:
    if get_url() is None:
        return None
    resp = urlget("providers/proxies").json()["providers"]["default"]["proxies"]
    proxies = []
    for i in resp:
        if i["type"] not in ["Direct", "Reject", "Selector", "Proxy", "URLTest", "Fallback", "LoadBalance"]:
            proxies.append(i["name"])
    return proxies


def test_proxy2(name: str) -> int:
    try:
        test_resp = requests.get(
            f"{get_url()}proxies/{quote(name)}/delay?timeout=10000&url=http%3A%2F%2Fwww.gstatic.com%2Fgenerate_204")
        if test_resp.status_code == 200:
            return int(test_resp.json()["delay"])
        else:
            return -1
    except:
        return -1


def test_proxy(name: str) -> int:
    pings = []
    for i in range(3):
        pings.append(test_proxy2(name))
        time.sleep(0.1)

    _avg = 0
    _succeed = 0
    for i in pings:
        if i != -1:
            _avg += i
            _succeed += 1

    if _avg == 0:
        return -1
    else:
        return int(_avg / _succeed)


def test_proxy_async(name: str, _results: dict):
    _results[name] = test_proxy(name)


def check_threads(threads: list[threading.Thread]):
    for i in threads:
        if i.is_alive():
            return False

    return True


def run_test() -> str:
    try:
        all_proxies = get_proxies()
        if all_proxies is None:
            return f"请先使用 <code>,{alias_command('ct')} url</code> 来设置Clash RESTFul API\n设置 secret 请直接: <code>,{alias_command('ct')} secret</code>"
        _results = {}
        success_result = {}
        failed_result = []
    except:
        return "失败, 请检查是否设置了正确的Clash RESTFul API."

    threads_pool = []
    for i in all_proxies:
        _subthread = threading.Thread(target=test_proxy_async, args=(i, _results))
        threads_pool.append(_subthread)
        _subthread.start()

    while not check_threads(threads_pool):
        continue

    for i in _results:
        if _results[i] != -1:
            success_result[i] = _results[i]
        else:
            failed_result.append(i)

    success_result_sorted = dict(sorted(success_result.items(), key=lambda x: x[1]))

    result = "在线节点:\n"
    for i in success_result_sorted:
        result += f"{i} - HTTP握手延迟:{success_result_sorted[i]} ms\n"

    if failed_result:
        result += "\n离线节点:\n" + "\n".join(failed_result)
    else:
        result += "\n全部节点都在线! 太酷啦!"

    return result


@listener(command="ct", description="使用Clash API进行HTTP Ping (Private)")
async def clash_test(msg: Message):
    if len(msg.parameter) == 1:
        if msg.arguments.startswith("https://") or msg.arguments.startswith("http://"):
            set_url(msg.arguments)
            await msg.edit("设置URL成功")
            return
        else:
            set_secret(msg.arguments)
            await msg.edit("设置Secret成功")
            return
    await msg.edit("Please Wait...")
    result = run_test()
    await msg.edit(result)
