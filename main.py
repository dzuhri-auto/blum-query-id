import argparse
import asyncio
import json
import random
from contextlib import suppress
from datetime import datetime
from http import HTTPStatus
from itertools import cycle

# import time
from time import time
from urllib.parse import unquote

import aiohttp
import pytz
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy

from bot.config import settings
from bot.core.agents import generate_random_user_agent
from bot.core.registrator import register_query_id
from bot.exceptions import (
    ErrorStartGameException,
    ExpiredApiKeyException,
    ExpiredTokenException,
    GameSessionNotFoundException,
    InvalidApiKeyException,
    InvalidSessionException,
)
from bot.utils import logger
from helpers import (
    convert_datetime_str_to_utc,
    format_duration,
    get_query_ids,
    get_tele_user_obj_from_query_id,
    mapping_role_color,
    populate_not_claimed_tasks,
    populate_not_started_tasks,
)

start_text = """
========================================================================================
                                    BLUM BOT
========================================================================================
Created By : https://t.me/irhamdz (Irham Dzuhri)
Premium bot ini cuma bisa didapatkan dari dzuhri auto (channel) / Irham Dzuhri (owner), 
Selain dari itu bisa di pastikan fake. 
Pilih menu:
    1. Start bot
    2. Buat sesi
    3. Hapus sesi
=========================================================================================
"""


def get_proxies() -> list[Proxy]:
    if settings.USE_PROXY_FROM_FILE:
        with open(file="bot/config/proxies.txt", encoding="utf-8-sig") as file:
            proxies = [Proxy.from_str(proxy=row.strip()).as_url for row in file]
    else:
        proxies = []
    return proxies


async def delete_account():
    delete = True
    while delete:
        query_ids = await get_query_ids()
        number_validation = []
        list_of_username = []
        delete_action = None

        if query_ids:
            print("")
            print("Pilih akun yg ingin dihapus: ")
            print("")
            for idx, query_id in enumerate(query_ids):
                tele_user_obj = get_tele_user_obj_from_query_id(query_id)
                username = tele_user_obj.get("username")
                num = idx + 1
                print(f"{num}. {username}")
                list_of_username.append(username)
                number_validation.append(str(num))
            print("")

            while True:
                delete_action = input("> ")
                if not delete_action:
                    return None
                if not delete_action.isdigit():
                    logger.warning("Harap masukkan angka")
                elif delete_action not in number_validation:
                    logger.warning("Harap masukkan angka yang tersedia")
                else:
                    delete_action = int(delete_action)
                    break

            with open("query_ids.txt", "r+") as f:
                content = f.readlines()
                content_len = len(content)
                f.truncate(0)
                f.seek(0)
                index_to_strip = 0
                for content_idx, line in enumerate(content):
                    if not content_idx == (delete_action - 1):
                        if delete_action == content_len:
                            index_to_strip = delete_action - 2
                        if index_to_strip and content_idx == index_to_strip:
                            f.write(line.strip())
                        else:
                            f.write(line)

            logger.success(f"Akun {list_of_username[delete_action - 1]} berhasil di hapus")

            list_of_username.pop(delete_action - 1)

            if not list_of_username:
                logger.success(f"Akun mu sudah terhapus semua")
                return None

            print("\n")
            keep_deleting = input("Ingin hapus akun lainnya? (y/n) > ")
            if not keep_deleting or keep_deleting == "n":
                return None
            elif keep_deleting == "y":
                continue
            else:
                return None
        else:
            logger.warning(f"Kamu belum mendaftarkan akun, harap daftarkan akun terlebih dahulu")
            return None


async def process(role: str, expire_ts: datetime) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="Action to perform")
    action = parser.parse_args().action
    if not action:
        print(start_text)
        while True:
            action = input("> ")
            if not action.isdigit():
                logger.warning("Harap masukkan angka")
            elif action not in ["1", "2", "3"]:
                logger.warning("Harap masukkan angka 1 , 2, atau 3")
            else:
                action = int(action)
                break
    if action == 2:
        await register_query_id()
    elif action == 1:
        await run_tasks(role=role, expire_ts=expire_ts)
    elif action == 3:
        await delete_account()


async def run_tasks(role: str, expire_ts: datetime):
    query_ids = await get_query_ids()
    if not query_ids:
        logger.warning("Buat sesi dulu gan.. ")
        return
    proxies = get_proxies()
    logger.info(f"============================================================")
    logger.info(f"Mendeteksi {len(query_ids)} akun | {len(proxies)} proxies")
    logger.info(f"============================================================")
    proxies_cycle = cycle(proxies) if proxies else None
    tasks = [
        asyncio.create_task(
            run_tapper(
                query_id=query_id,
                proxy=next(proxies_cycle) if proxies_cycle else None,
                role=role,
                expire_ts=expire_ts,
            )
        )
        for query_id in query_ids
    ]
    await asyncio.gather(*tasks)


class Tapper:
    def __init__(self, query_id: str, role: str, expire_ts: datetime):
        self.query_id = query_id
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None
        # self.user_url = "https://user-domain.blum.codes/api/v1"
        # self.login_base_url = "https://gateway.blum.codes/v1/auth/provider"
        # self.game_url = "https://game-domain.blum.codes/api/v1"
        self.gateway_url = "https://gateway.blum.codes/api/v1"
        self.game_url = "https://game-domain.blum.codes/api/v1"
        self.wallet_url = "https://wallet-domain.blum.codes/api/v1"
        self.subscription_url = "https://subscription.blum.codes/api/v1"
        self.tribe_url = "https://tribe-domain.blum.codes/api/v1"
        self.user_url = "https://user-domain.blum.codes/api/v1"
        self.earn_domain = "https://earn-domain.blum.codes/api/v1"
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://telegram.blum.codes",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Sec-Ch-Ua": '"Google Chrome";v="127", "Chromium";v="127", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?1",
            "Sec-Ch-Ua-Platform": "Android",
            "X-Requested-With": "org.telegram.messenger",
        }
        self.role = role
        self.expire_ts = expire_ts
        self.session_ug_dict = self.load_user_agents() or []
        self.access_token_created_time = 0

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type="android", browser_type="chrome")

    def info(self, message):
        from bot.utils import info

        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug

        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning

        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error

        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical

        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success

        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"
        if not any(
            session["session_name"] == self.session_name for session in self.session_ug_dict
        ):
            user_agent_str = generate_random_user_agent()
            self.session_ug_dict.append(
                {"session_name": self.session_name, "user_agent": user_agent_str}
            )
            with open(user_agents_file_name, "w") as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)
            logger.success(
                f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully"
            )
            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"
        try:
            with open(user_agents_file_name, "r") as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data
        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")
        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")
        return []

    def check_user_agent(self):
        load = next(
            (
                session["user_agent"]
                for session in self.session_ug_dict
                if session["session_name"] == self.session_name
            ),
            None,
        )
        if load is None:
            return self.save_user_agent()
        return load

    async def login(self, http_client: aiohttp.ClientSession, initdata):
        try:
            json_data = {"query": initdata}
            resp = await http_client.post(
                f"{self.user_url}/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                json=json_data,
                ssl=False,
            )
            # self.debug(f'login text {await resp.text()}')
            resp_json = await resp.json()

            return resp_json.get("token").get("access"), resp_json.get("token").get("refresh")
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | login error {error}")

    async def claim_task(self, http_client: aiohttp.ClientSession, task_id):
        try:
            resp = await http_client.post(
                f"{self.earn_domain}/tasks/{task_id}/claim", ssl=False
            )
            resp_json = await resp.json()

            # logger.debug(f"{self.session_name} | claim_task response: {resp_json}")

            return resp_json.get("status") == "FINISHED"
        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Claim task error {error}"
            )

    async def start_complete_task(self, http_client: aiohttp.ClientSession, task_id):
        try:
            resp = await http_client.post(
                f"{self.game_url}/tasks/{task_id}/start", ssl=False
            )
            resp_json = await resp.json()

            # logger.debug(f"{self.session_name} | start_complete_task response: {resp_json}")
            return resp_json.get("status") == "STARTED"
        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Start complete task error {error}"
            )

    async def get_tasks(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get(f"{self.earn_domain}/tasks", ssl=False)
            resp_json = await resp.json()

            # logger.debug(f"{self.session_name} | get_tasks response: {resp_json}")

            if isinstance(resp_json, list):
                return resp_json
            else:
                logger.error(
                    f"{self.session_name} | Unexpected response format in get_tasks: {resp.status} {resp_json}"
                )
                return []
        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Get tasks error {error}"
            )

    async def play_game(self, http_client: aiohttp.ClientSession, play_passes):
        try:
            while play_passes:
                game_id = await self.start_game(http_client=http_client)

                if not game_id or game_id == "cannot start game":
                    raise ErrorStartGameException(
                        f"Gagal start game!, sisa tiket: <lc>{play_passes}</lc>"
                    )
                    # break
                else:
                    self.success("Memulai play game")

                await asyncio.sleep(random.uniform(30, 40))

                msg, points = await self.claim_game(game_id=game_id, http_client=http_client)
                if isinstance(msg, bool) and msg:
                    play_passes -= 1
                    self.info(
                        f"Selesai play game! , reward: <lg>(+{points})</lg>, sisa tiket: <lc>{play_passes}</lc>"
                    )
                else:
                    self.info(f"Gagal play game, msg: {msg}, sisa tiket: <lc>{play_passes}</lc>")
                    break

                await asyncio.sleep(random.uniform(30, 40))
        except Exception as e:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Error occurred during play game: {e}"
            )
            await asyncio.sleep(random.randint(0, 5))

    async def start_game(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(f"{self.game_url}/game/play", ssl=False)
            response_data = await resp.json()
            if "gameId" in response_data:
                return response_data.get("gameId")
            elif "message" in response_data:
                return response_data.get("message")
        except Exception as e:
            self.error(f"Error occurred during start game: {e}")

    async def claim_game(self, game_id: str, http_client: aiohttp.ClientSession):
        try:
            points = random.randint(settings.POINTS[0], settings.POINTS[1])
            json_data = {"gameId": game_id, "points": points}

            resp = await http_client.post(
                f"{self.game_url}/game/claim", json=json_data, ssl=False
            )

            if resp.status == HTTPStatus.UNAUTHORIZED:
                raise ExpiredTokenException("token expired during claim game")

            txt = await resp.text()

            if "game session not found" in txt:
                raise GameSessionNotFoundException(
                    "got error game session not found during claim game"
                )

            return True if txt == "OK" else txt, points
        except Exception as e:
            self.error(f"Error occurred during claim game: {e}")

    async def claim(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(f"{self.game_url}/farming/claim", ssl=False)
            if resp.status != 200:
                resp = await http_client.post(
                    f"{self.game_url}/farming/claim", ssl=False
                )

            resp_json = await resp.json()

            return int(resp_json.get("timestamp") / 1000), resp_json.get("availableBalance")
        except Exception as e:
            self.error(f"Error occurred during claim: {e}")

    async def start(self, http_client: aiohttp.ClientSession):
        url = f"{self.game_url}/farming/start"
        try:
            resp = await http_client.post(url, ssl=False)

            # if resp.status != 200:
            #     resp = await http_client.post(url, ssl=False)

            resp_json = await resp.json()
            return int(resp_json.get("startTime") / 1000), int(resp_json.get("endTime") / 1000)
        except Exception as e:
            self.error(f"Error occurred during start: {e}")

    async def friend_balance(self, http_client: aiohttp.ClientSession):
        url = f"{self.user_url}/friends/balance"
        try:
            resp = await http_client.get(url=url, ssl=False)
            resp_json = await resp.json()

            claim_amount = resp_json.get("amountForClaim")
            is_available = resp_json.get("canClaim")

            if resp.status != 200:
                resp = await http_client.get(url=url, ssl=False)
                resp_json = await resp.json()
                claim_amount = resp_json.get("amountForClaim")
                is_available = resp_json.get("canClaim")

            return (claim_amount, is_available)
        except Exception as e:
            self.error(f"Error occurred during friend balance: {e}")

    async def friend_claim(self, http_client: aiohttp.ClientSession):
        url = f"{self.user_url}/friends/claim"
        try:
            resp = await http_client.post(url, ssl=False)
            resp_json = await resp.json()
            amount = resp_json.get("claimBalance")
            if resp.status != 200:
                resp = await http_client.post(url, ssl=False)
                resp_json = await resp.json()
                amount = resp_json.get("claimBalance")

            return amount
        except Exception as e:
            self.error(f"Error occurred during friends claim: {e}")

    async def balance(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get(f"{self.game_url}/user/balance", ssl=False)
            resp_json = await resp.json()

            timestamp = resp_json.get("timestamp")
            play_passes = resp_json.get("playPasses")
            balance = resp_json.get("availableBalance")

            start_time = None
            end_time = None
            if resp_json.get("farming"):
                start_time = resp_json["farming"].get("startTime")
                end_time = resp_json["farming"].get("endTime")

            return (
                int(timestamp / 1000) if timestamp is not None else None,
                int(start_time / 1000) if start_time is not None else None,
                int(end_time / 1000) if end_time is not None else None,
                play_passes,
                balance,
            )
        except Exception as e:
            self.error(f"Error occurred during balance: {e}")

    async def claim_daily_reward(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(
                f"{self.game_url}/daily-reward?offset=-180", ssl=False
            )
            txt = await resp.text()
            return True if txt == "OK" else txt
        except Exception as e:
            self.error(f"Error occurred during claim daily reward: {e}")

    async def refresh_token(self, http_client: aiohttp.ClientSession, token):
        json_data = {"refresh": token}
        resp = await http_client.post(
            "https://gateway.blum.codes/v1/auth/refresh", json=json_data, ssl=False
        )
        resp_json = await resp.json()
        return resp_json.get("access"), resp_json.get("refresh")

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(
                url="https://httpbin.org/ip", timeout=aiohttp.ClientTimeout(5)
            )
            ip = (await response.json()).get("origin")
            logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Proxy IP: {ip}")
        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Proxy: {proxy} | Error: {error}"
            )

    async def run(self, proxy: str | None) -> None:
        if "tgWebAppData" in self.query_id:
            init_data = unquote(
                string=self.query_id.split("tgWebAppData=", maxsplit=1)[1].split(
                    "&tgWebAppVersion", maxsplit=1
                )[0]
            )
        else:
            init_data = self.query_id
        tele_user_obj = get_tele_user_obj_from_query_id(init_data)
        self.session_name = tele_user_obj.get("username")
        access_token = None
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        http_client = CloudflareScraper(headers=self.headers, connector=proxy_conn)
        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)
        http_client.headers["User-Agent"] = self.check_user_agent()
        while True:
            try:
                if time() - self.access_token_created_time >= 3000:
                    if "Authorization" in http_client.headers:
                        del http_client.headers["Authorization"]

                    # init_data = await self.get_tg_web_data(proxy=proxy)

                    access_token, refresh_token = await self.login(
                        http_client=http_client, initdata=init_data
                    )

                    http_client.headers["Authorization"] = f"Bearer {access_token}"

                    self.access_token_created_time = time()

                    if self.first_run is not True:
                        # self.success("Logged in successfully")
                        self.first_run = True

                timestamp, start_time, end_time, play_passes, balance = await self.balance(
                    http_client=http_client
                )
                self.info(f"Balance : <lg>{int(float(balance)):,}</lg>")

                await asyncio.sleep(1.5)

                msg = await self.claim_daily_reward(http_client=http_client)
                if isinstance(msg, bool) and msg:
                    self.success("Berhasil klaim daily reward!")

                if isinstance(play_passes, int):
                    self.info(f"Kamu punya <lg>{play_passes}</lg> play ticket pass")

                claim_amount, is_available = await self.friend_balance(http_client=http_client)

                if claim_amount != 0 and is_available:
                    amount = await self.friend_claim(http_client=http_client)
                    self.success(
                        f"Berhasil klaim friend ref reward: <lg>(+{int(float(amount)):,})</lg>"
                    )

                if play_passes and play_passes > 0 and settings.PLAY_GAMES is True:
                    await self.play_game(http_client=http_client, play_passes=play_passes)

                await asyncio.sleep(1.5)

                # start task
                tasks = await self.get_tasks(http_client=http_client)
                if tasks:
                    not_started_tasks = populate_not_started_tasks(tasks)
                    total_not_started_tasks = len(not_started_tasks)
                    if total_not_started_tasks > 0:
                        # self.info(
                        #     f"Kamu punya <lg>{total_not_started_tasks}</lg> task yg belum selesai"
                        # )

                        for task in not_started_tasks:
                            task_title = task.get("task_title")
                            task_id = task.get("task_id")
                            task_started = await self.start_complete_task(
                                http_client=http_client, task_id=task_id
                            )
                            if task_started:
                                # self.success(f"Sukses start task: <lc>{task_title}</lc>")
                                await asyncio.sleep(1.5)

                await asyncio.sleep(1)

                # claim task
                tasks = await self.get_tasks(http_client=http_client)
                if tasks:
                    not_claimed_tasks = populate_not_claimed_tasks(tasks)
                    total_not_claimed_tasks = len(not_claimed_tasks)
                    if total_not_claimed_tasks > 0:
                        for task in not_claimed_tasks:
                            task_title = task.get("task_title")
                            task_id = task.get("task_id")
                            task_claimed = await self.claim_task(
                                http_client=http_client, task_id=task_id
                            )
                            if task_claimed:
                                self.success(
                                    f"<lg>Sukses claim task:</lg> <lc>{task_title}</lc> <lg>(+{task.get('task_reward')})</lg>"
                                )
                                await asyncio.sleep(1.5)

                await asyncio.sleep(1)

                timestamp, start_time, end_time, play_passes, balance = await self.balance(
                    http_client=http_client
                )

                if (
                    start_time is not None
                    and end_time is not None
                    and timestamp is not None
                    and timestamp >= end_time
                ):
                    timestamp, balance = await self.claim(http_client=http_client)
                    self.success(
                        f"Berhasil klaim farming reward!, Balance: <lg>{int(float(balance)):,}</lg>"
                    )
                    await asyncio.sleep(1)

                    start_time, end_time = await self.start(http_client=http_client)
                    self.info(f"Start farming!")
                    await asyncio.sleep(1)

                elif start_time is None and end_time is None:
                    start_time, end_time = await self.start(http_client=http_client)
                    self.info(f"Start farming!")
                    await asyncio.sleep(1)

                random_offset_sec = random.randint(30, 300)
                sleep_duration = (end_time - timestamp) + random_offset_sec
                self.info(f"Delay {format_duration(sleep_duration)}")
                # need_login = True

                # update membership info
                api_key_result = await check_api_key()
                role, expire_ts_dt = await check_membership_time_left(api_key_result)
                self.role = role
                self.expire_ts = expire_ts_dt
                await asyncio.sleep(sleep_duration)

            except InvalidSessionException as error:
                raise error

            except ExpiredTokenException as error:
                self.warning(f"<ly>{error}</ly>")
                await asyncio.sleep(delay=10)
                continue

            except GameSessionNotFoundException as error:
                self.warning(f"<ly>{error}</ly>")
                await asyncio.sleep(delay=10)
                continue

            except ErrorStartGameException as error:
                self.warning(f"<ly>{error}</ly>")
                await asyncio.sleep(delay=10)
                continue

            except ExpiredApiKeyException as error:
                self.error(str(error))
                break

            except Exception as error:
                self.error(f"Unknown error: {error}")
                await asyncio.sleep(delay=10)


async def run_tapper(query_id: str, proxy: str | None, role: str, expire_ts: datetime):
    await Tapper(query_id=query_id, role=role, expire_ts=expire_ts).run(proxy=proxy)


async def check_api_key():
    result = None
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://ec2-54-166-158-149.compute-1.amazonaws.com/verify-key/",
            json={"api_key": settings.API_KEY},
        ) as resp:
            response = await resp.text()
            json_response = json.loads(response)
            if resp.status != HTTPStatus.OK:
                raise InvalidApiKeyException(json_response.get("error"))
            else:
                result = json_response
        await session.close()
        return result


async def check_membership_time_left(api_key_obj, show_log=False):
    expire_ts_dt = convert_datetime_str_to_utc(api_key_obj.get("expire_ts"))
    role = api_key_obj.get("role_name")
    if show_log:
        logger.info(f"Login sebagai {mapping_role_color(role)} user")
    if role != "admin":
        current_time_utc = datetime.now(pytz.utc)
        if expire_ts_dt < current_time_utc:
            raise ExpiredApiKeyException(
                "Masa member kamu sudah habis, silahkan perpanjang terlebih dahulu"
            )
        if show_log:
            membership_expiry_left_ts = expire_ts_dt - current_time_utc
            logger.info(
                f"Sisa waktu membership: {format_duration(membership_expiry_left_ts.total_seconds())}"
            )
    return role, expire_ts_dt


async def main():
    try:
        result = await check_api_key()
        role, expire_ts_dt = await check_membership_time_left(result, True)
        await process(role=role, expire_ts=expire_ts_dt)
    except InvalidApiKeyException as err:
        logger.error("API Key salah")
    except ExpiredApiKeyException as err:
        logger.error(str(err))


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
