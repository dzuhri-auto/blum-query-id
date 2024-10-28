import argparse
import asyncio
import json
import random
import re
import sys
import time
from contextlib import suppress
from datetime import datetime
from http import HTTPStatus
from itertools import cycle

# from time import time
from urllib.parse import unquote

import aiohttp
import certifi
import pytz
import requests
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.theme import Theme

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
    JSONDecodeErrorException,
    MissingApiKeyException,
    UnexpectedResponseFormatException,
)
from bot.utils import logger
from constants import ACTION_MENUS
from helpers import (
    convert_datetime_str_to_utc,
    format_duration,
    get_query_ids,
    get_tele_user_obj_from_query_id,
    mapping_role_color,
)

curr_version = "2.2.3"

banner = f"""
[bold cyan]BLUM BOT[/bold cyan]
[bold magenta]Version {curr_version}[/bold magenta]
Created by: Irham Dzuhri
(https://t.me/irhamdz)
"""

custom_theme = Theme({"info": "dim cyan", "warning": "yellow", "danger": "bold red"})
console = Console(theme=custom_theme)


def check_version():
    version = requests.get(
        "https://raw.githubusercontent.com/dzuhri-auto/blum-query-id/refs/heads/main/version",
        verify=certifi.where(),
    )
    version_ = version.text.strip()
    if curr_version != version_:
        console.print(
            f"\nNew version detected: [cyan]{version_}[/cyan], Please update the bot by running the following command: [green]git pull[/green]",
            style="warning",
        )
        sys.exit()
    return version_


def initial_check_api_key():
    result = None
    response = requests.post(
        "http://ec2-54-166-158-149.compute-1.amazonaws.com/verify-key/",
        json={"api_key": settings.LICENSE_KEY},
    )
    json_response = response.json()
    if response.status_code != HTTPStatus.OK:
        result = None
    else:
        result = json_response
    return result


def initial_check_membership_time_left(api_key_obj):
    expired = False
    expire_ts_dt = convert_datetime_str_to_utc(api_key_obj.get("expire_ts"))
    role = api_key_obj.get("role_name")
    membership_expiry_left_ts = None
    if role != "admin":
        current_time_utc = datetime.now(pytz.utc)
        if expire_ts_dt < current_time_utc:
            expired = True  # expired
        membership_expiry_left_ts = expire_ts_dt - current_time_utc
    return expired, role, membership_expiry_left_ts


def check_license_key():
    status = True  # valid
    expired = False  # not expired
    role = None
    membership_expiry_left_ts = None
    if not settings.LICENSE_KEY:
        status = False
        return status, expired, role, membership_expiry_left_ts

    api_key_obj = initial_check_api_key()
    if not api_key_obj:
        status = False
        return status, expired, role, membership_expiry_left_ts

    expired, role, membership_expiry_left_ts = initial_check_membership_time_left(api_key_obj)
    return status, expired, role, membership_expiry_left_ts


def get_proxies() -> list[Proxy]:
    if settings.USE_PROXY_FROM_FILE.lower() == "true":
        with open(file="bot/config/proxies.txt", encoding="utf-8-sig") as file:
            proxies = [Proxy.from_str(proxy=row.strip()).as_url for row in file]
    else:
        proxies = []
    return proxies


def display_menu(choices, session_count, proxy_count, license_key_info):
    console = Console()

    menu_text = "\n".join([f"[red][{i}][/red] {choice}" for i, choice in enumerate(choices, 1)])

    proxy_info = (
        f":rocket: Detected [cyan]{session_count}[/cyan] accounts and [cyan]{proxy_count}[/cyan] proxies"
        if settings.USE_PROXY_FROM_FILE.lower() == "true"
        else f":rocket: Detected [cyan]{session_count}[/cyan] accounts (running without proxies)"
    )

    panel_content = f"{license_key_info}\n{proxy_info}\n\n" f"{menu_text}"

    panel = Panel(panel_content, border_style="dim cyan", style="bold white", padding=(1, 4))

    console.print(panel)
    print("")


def create_menus():
    menus = ["Start bot", "Add query", "Delete query"]
    print("Please choose action: ")
    print("")
    for idx, menu in enumerate(menus):
        num = idx + 1
        print(f"{num}. {menu}")
    print(
        "========================================================================================"
    )


async def delete_account():
    delete = True
    while delete:
        query_ids = await get_query_ids()
        number_validation = []
        list_of_username = []
        delete_action = None

        if query_ids:
            print("")
            print("Please Choose session that want to be delete: ")
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
                    logger.warning("Please only input number")
                elif delete_action not in number_validation:
                    logger.warning("Please only input number that are available")
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

            logger.success(f"Successfully deleted session {list_of_username[delete_action - 1]}")

            list_of_username.pop(delete_action - 1)

            if not list_of_username:
                logger.success(f"All of your session has been deleted")
                return None

            print("\n")
            keep_deleting = input("Want to delete other session? (y/n) > ")
            if not keep_deleting or keep_deleting == "n":
                return None
            elif keep_deleting == "y":
                continue
            else:
                return None
        else:
            logger.warning(f"You dont have any session, please create session first!")
            return None


async def process() -> None:
    with Progress(transient=True) as progress:
        task = progress.add_task("[blue]Checking License Key...", total=None)
        status, expired, role, membership_expiry_left_ts = check_license_key()
        progress.update(task, total=100)
        progress.start_task(task)
        if not status:
            console.print(
                "\n\nLICENSE KEY is missing or invalid, please check your license key!",
                style="danger",
            )
            sys.exit()

        if expired:
            console.print(
                "\n\nYour LICENSE KEY has been expired, please re-subscribe to continue!",
                style="danger",
            )
            sys.exit()

    duration_left = (
        format_duration(membership_expiry_left_ts.total_seconds())
        if membership_expiry_left_ts
        else 0
    )
    license_key_info = f":key: Login as {mapping_role_color(role)} user, license key expire time left: [yellow]{duration_left}[/yellow]"

    query_ids = []
    with Progress(transient=True) as progress:
        task = progress.add_task("[blue]Checking Query IDs...", total=None)
        query_ids = await get_query_ids()
        progress.update(task, total=len(query_ids))
        progress.start_task(task)

    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="Action to perform")
    action = parser.parse_args().action
    if not action:
        ACTION_MENUS
        display_menu(
            ACTION_MENUS,
            session_count=len(query_ids),
            proxy_count=len(get_proxies()),
            license_key_info=license_key_info,
        )
        while True:
            choice = console.input(
                "[bold yellow]Select an action (press Enter to exit): [/bold yellow]"
            )
            console.print("")

            if not choice:
                break

            if not choice.isdigit() or int(choice) not in range(1, 6):
                console.print("Invalid input. Please select a number between 1 and 3.\n")
                continue

            action = int(choice)
            break

    if action == 2:
        await register_query_id()
    elif action == 1:
        await run_tasks(query_ids)
    elif action == 3:
        await delete_account()


async def run_tasks(query_ids):
    # query_ids = await get_query_ids()
    if not query_ids:
        logger.warning(
            "No query ID found. Please select <lc>Add query</lc> or add it directly to the <lc>query_ids.txt</lc> file"
        )
        return
    proxies = get_proxies()
    result = await check_api_key()
    role, expire_ts_dt = await check_membership_time_left(result)
    proxies_cycle = cycle(proxies) if proxies else None
    tasks = [
        asyncio.create_task(
            run_tapper(
                query_id=query_id,
                proxy=next(proxies_cycle) if proxies_cycle else None,
                role=role,
                expire_ts=expire_ts_dt,
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
        self.gateway_url = "https://gateway.blum.codes/api/v1"
        self.game_url = "https://game-domain.blum.codes/api/v1"
        self.wallet_url = "https://wallet-domain.blum.codes/api/v1"
        self.subscription_url = "https://subscription.blum.codes/api/v1"
        self.tribe_url = "https://tribe-domain.blum.codes/api/v1"
        self.user_url = "https://user-domain.blum.codes/api/v1"
        self.earn_domain = "https://earn-domain.blum.codes/api/v1"
        self.game_url_v2 = "https://game-domain.blum.codes/api/v2"
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

        info(f"<ly>{self.session_name}</ly> | {message}")

    def debug(self, message):
        from bot.utils import debug

        debug(f"<ly>{self.session_name}</ly> | ⚙ {message}")

    def warning(self, message):
        from bot.utils import warning

        warning(f"<ly>{self.session_name}</ly> | ⚠️ {message}")

    def error(self, message):
        from bot.utils import error

        error(f"<ly>{self.session_name}</ly> | ❌ {message}")

    def critical(self, message):
        from bot.utils import critical

        critical(f"<ly>{self.session_name}</ly> | ‼ {message}")

    def success(self, message):
        from bot.utils import success

        success(f"<ly>{self.session_name}</ly> | ✅ {message}")

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
            self.success("User agent saved successfully")
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

    def load_task_codes(self):
        task_codes_file_name = "task_codes.json"
        try:
            with open(task_codes_file_name, "r") as task_codes:
                task_code_datas = json.load(task_codes)
                if isinstance(task_code_datas, dict):
                    return task_code_datas
        except FileNotFoundError:
            self.warning("Task codes file not found.")
        except json.JSONDecodeError:
            self.warning("Task codes file is empty or corrupted.")
        return {}

    async def login(self, http_client: aiohttp.ClientSession, initdata):
        try:
            json_data = {"query": initdata}
            resp = await http_client.post(
                f"{self.user_url}/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                json=json_data,
                ssl=False,
            )
            # self.debug(f'login text {await resp.text()}')
            if resp.headers.get("content-type") == "application/json":
                resp_json = await resp.json()
                if resp_json.get("message") and "Invalid username" in resp_json.get("message"):
                    # fresh account and doesnt have username
                    tele_user_obj = get_tele_user_obj_from_query_id(self.query_id)
                    first_name = tele_user_obj.get("first_name")
                    last_name = tele_user_obj.get("last_name")
                    username = None
                    while True:
                        random_num = random.randint(0, 1000)
                        username = f"{first_name}_{last_name}{random_num}"
                        username_check_body = {"username": username}
                        resp = await http_client.post(
                            f"{self.user_url}/user/username/check",
                            json=username_check_body,
                            ssl=False,
                        )
                        if resp.status in {HTTPStatus.OK, HTTPStatus.CREATED}:
                            break
                    # set the username while getting the token
                    json_data["username"] = username
                    resp = await http_client.post(
                        f"{self.user_url}/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                        json=json_data,
                        ssl=False,
                    )
                    if resp.status in {HTTPStatus.OK, HTTPStatus.CREATED}:
                        self.info(f"Successfully set username: <lc>{username}</lc>")
                        resp_json = await resp.json()
                        return resp_json.get("token", {}).get("access", {}), resp_json.get(
                            "token", {}
                        ).get("refresh", {})
                    else:
                        return None, None
                else:
                    return resp_json.get("token", {}).get("access", {}), resp_json.get(
                        "token", {}
                    ).get("refresh", {})
            else:
                # print("Unexpected response format:", await response.text())
                response = await resp.text()
                raise UnexpectedResponseFormatException(f"Unexpected response format: {response}")
        except UnexpectedResponseFormatException as err:
            return None, None
        except Exception as error:
            self.error(f"Login error {error}")

    async def claim_task(self, http_client: aiohttp.ClientSession, task_id):
        try:
            resp = await http_client.post(f"{self.earn_domain}/tasks/{task_id}/claim", ssl=False)
            # Check if the response is JSON
            if resp.headers.get("content-type") == "application/json":
                try:
                    resp_json = await resp.json()
                    return resp_json.get("status") == "FINISHED"
                except json.JSONDecodeError:
                    raise JSONDecodeErrorException("Error decoding JSON response")
            else:
                # Handle non-JSON response
                response = await resp.text()
                raise UnexpectedResponseFormatException(f"Unexpected response format: {response}")
        except UnexpectedResponseFormatException as err:
            return False
        except JSONDecodeErrorException as err:
            return False
        except Exception as error:
            self.error(f"Claim task error {error}")

    async def validate_task(self, http_client: aiohttp.ClientSession, task_id, title):
        try:
            keywords = self.load_task_codes()

            payload = {"keyword": keywords.get(title)}
            resp = await http_client.post(
                f"{self.earn_domain}/tasks/{task_id}/validate", json=payload, ssl=False
            )
            resp_json = await resp.json()
            if resp_json.get("status") == "READY_FOR_CLAIM":
                status = await self.claim_task(http_client, task_id)
                if status:
                    return status
            else:
                return False
        except Exception as error:
            self.error(f"Validate task error {error}")

    async def start_complete_task(self, http_client: aiohttp.ClientSession, task_id):
        try:
            resp = await http_client.post(f"{self.earn_domain}/tasks/{task_id}/start", ssl=False)
            # logger.debug(f"{self.session_name} | start_complete_task response: {resp_json}")
            if resp.headers.get("content-type") == "application/json":
                try:
                    resp_json = await resp.json()
                    return resp_json.get("status") == "STARTED"
                except json.JSONDecodeError:
                    raise JSONDecodeErrorException("Error decoding JSON response")
            else:
                # Handle non-JSON response
                response = await resp.text()
                raise UnexpectedResponseFormatException(f"Unexpected response format: {response}")
        except UnexpectedResponseFormatException as err:
            return False
        except JSONDecodeErrorException as err:
            return False
        except Exception as error:
            self.error(f"Start complete task error {error}")

    async def get_tasks(self, http_client: aiohttp.ClientSession):
        try:
            while True:
                resp = await http_client.get(f"{self.earn_domain}/tasks", ssl=False)
                if resp.status not in [HTTPStatus.OK, HTTPStatus.CREATED]:
                    continue
                else:
                    break

            resp_json = await resp.json()

            def collect_tasks(resp_json):
                collected_tasks = []
                for task in resp_json:
                    if task.get("sectionType") == "HIGHLIGHTS":
                        tasks_list = task.get("tasks", [])
                        for t in tasks_list:
                            sub_tasks = t.get("subTasks")
                            if sub_tasks:
                                for sub_task in sub_tasks:
                                    collected_tasks.append(sub_task)
                            if t.get("type") != "PARTNER_INTEGRATION":
                                collected_tasks.append(t)

                    if task.get("sectionType") == "WEEKLY_ROUTINE":
                        tasks_list = task.get("tasks", [])
                        for t in tasks_list:
                            sub_tasks = t.get("subTasks", [])
                            for sub_task in sub_tasks:
                                collected_tasks.append(sub_task)

                    if task.get("sectionType") == "DEFAULT":
                        sub_tasks = task.get("subSections", [])
                        for sub_task in sub_tasks:
                            tasks = sub_task.get("tasks", [])
                            for task_basic in tasks:
                                collected_tasks.append(task_basic)

                return collected_tasks

            all_tasks = collect_tasks(resp_json)

            return all_tasks
        except Exception as error:
            self.error(f"Get tasks error {error}")
            return []

    async def play_game(self, http_client: aiohttp.ClientSession, play_passes, refresh_token):
        try:
            total_games = 0
            tries = 3
            while play_passes:
                game_id = await self.start_game(http_client=http_client)

                if not game_id or game_id == "cannot start game":
                    self.warning(
                        f"Couldn't start play in game! , play_passes: {play_passes}, trying again"
                    )
                    tries -= 1
                    if tries == 0:
                        self.warning("No more trying, gonna skip games")
                        break
                    continue
                else:
                    if total_games != 20:
                        total_games += 1
                        self.success(f"Started playing game with game id: {game_id}")
                    else:
                        self.info("Getting new token to play games")
                        while True:
                            (access_token, refresh_token) = await self.refresh_token(
                                http_client=http_client, token=refresh_token
                            )
                            if access_token:
                                http_client.headers["Authorization"] = f"Bearer {access_token}"
                                self.success("Got new token")
                                total_games = 0
                                break
                            else:
                                self.error("Can`t get new token, trying again")
                                continue

                random_delay = random.uniform(30, 40)
                self.info(f"Delay {format_duration(random_delay)} before claim the game")
                await asyncio.sleep(random_delay)

                data_elig = await self.check_elig_dogs(http_client=http_client)
                dogs = 0
                if data_elig:
                    dogs = random.randint(25, 30) * 5
                    msg, points, dogs = await self.claim_game(
                        game_id=game_id, http_client=http_client, dogs=dogs
                    )
                else:
                    msg, points, dogs = await self.claim_game(
                        game_id=game_id, http_client=http_client, dogs=dogs
                    )

                if isinstance(msg, bool) and msg:
                    self.success(
                        f"Successfully playing game!, reward: <lg>{points}</lg> BP | <lc>{dogs}</lc> Dogs"
                    )
                else:
                    self.warning(f"Couldn't play game, msg: {msg}, retrying..")
                    tries -= 1
                    if tries == 0:
                        self.warning("No more trying, gonna skip games")
                        break

                await asyncio.sleep(random.uniform(3, 5))

                play_passes -= 1
        except Exception as e:
            self.error(f"Error occurred during play game: {e}")

    async def start_game(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(f"{self.game_url_v2}/game/play", ssl=False)
            response_data = await resp.json()
            if "gameId" in response_data:
                return response_data.get("gameId")
            elif "message" in response_data:
                return response_data.get("message")
        except Exception as e:
            self.error(f"Error occurred during start game: {e}")

    async def get_data_payload(self):
        url = "https://raw.githubusercontent.com/zuydd/database/main/blum.json"
        data = requests.get(url=url)
        return data.json()

    async def create_payload(self, http_client: aiohttp.ClientSession, game_id, points, dogs):
        # data = await self.get_data_payload()
        # payload_server = data.get("payloadServer", [])
        # filtered_data = [item for item in payload_server if item["status"] == 1]
        # random_id = random.choice([item["id"] for item in filtered_data])
        # resp = await http_client.post(
        #     f"https://{random_id}.vercel.app/api/blum",
        #     json={"game_id": game_id, "points": points, "dogs": dogs},
        # )
        payload_server = "https://server2.ggtog.live/api/game"
        payload_data = {"gameId": game_id, "points": str(points)}
        if dogs:
            payload_data["dogs"] = dogs
        resp = await http_client.post(payload_server, json=payload_data)
        if resp is not None:
            data = await resp.json()
            if "payload" in data:
                return data["payload"]
        return None

    async def claim_game(self, game_id: str, dogs, http_client: aiohttp.ClientSession):
        try:
            points = random.randint(settings.POINTS[0], settings.POINTS[1])

            data = await self.create_payload(
                http_client=http_client, game_id=game_id, points=points, dogs=dogs
            )

            resp = await http_client.post(
                f"{self.game_url_v2}/game/claim", json={"payload": data}, ssl=False
            )
            if resp.status != HTTPStatus.OK:
                resp = await http_client.post(
                    f"{self.game_url_v2}/game/claim", json={"payload": data}, ssl=False
                )

            txt = await resp.text()

            return True if txt == "OK" else txt, points, dogs
        except Exception as e:
            self.error(f"Error occurred during claim game: {e}")

    async def claim(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(f"{self.game_url}/farming/claim", ssl=False)
            if resp.status != 200:
                resp = await http_client.post(f"{self.game_url}/farming/claim", ssl=False)

            resp_json = await resp.json()

            return int(resp_json.get("timestamp") / 1000), resp_json.get("availableBalance")
        except Exception as e:
            self.error(f"Error occurred during claim: {e}")

    async def start_farming(self, http_client: aiohttp.ClientSession):
        url = f"{self.game_url}/farming/start"
        try:
            resp = await http_client.post(url, ssl=False)

            # if resp.status != 200:
            #     resp = await http_client.post(url, ssl=False)

            resp_json = await resp.json()
            start_time = resp_json.get("startTime")
            end_time = resp_json.get("endTime")
            if not start_time and not end_time:
                return None, None

            if not isinstance(start_time, int):
                start_time = int(start_time)

            if not isinstance(end_time, int):
                end_time = int(end_time)

            return start_time / 1000, end_time / 1000
        except Exception as e:
            self.error(f"Error occurred during start farming: {e}")

    async def friend_balance(self, http_client: aiohttp.ClientSession):
        url = f"{self.user_url}/friends/balance"
        try:
            resp = await http_client.get(url=url, ssl=False)
            if resp.headers.get("content-type") == "application/json":
                try:
                    resp_json = await resp.json()
                    claim_amount = resp_json.get("amountForClaim")
                    is_available = resp_json.get("canClaim")

                    if resp.status != 200:
                        resp = await http_client.get(url=url, ssl=False)
                        resp_json = await resp.json()
                        claim_amount = resp_json.get("amountForClaim")
                        is_available = resp_json.get("canClaim")

                    return (claim_amount, is_available)
                except json.JSONDecodeError:
                    raise JSONDecodeErrorException("Error decoding JSON response")
            else:
                # Handle non-JSON response
                response = await resp.text()
                raise UnexpectedResponseFormatException(f"Unexpected response format: {response}")
        except UnexpectedResponseFormatException as err:
            return 0, False
        except JSONDecodeErrorException as err:
            return 0, False
        except Exception as e:
            self.error(f"Error occurred during friend balance: {e}")

    async def friend_claim(self, http_client: aiohttp.ClientSession):
        url = f"{self.user_url}/friends/claim"
        try:
            resp = await http_client.post(url, ssl=False)
            if resp.headers.get("content-type") == "application/json":
                try:
                    resp_json = await resp.json()
                    amount = resp_json.get("claimBalance")
                    if resp.status != 200:
                        resp = await http_client.post(url, ssl=False)
                        resp_json = await resp.json()
                        amount = resp_json.get("claimBalance")
                    return amount
                except json.JSONDecodeError:
                    raise JSONDecodeErrorException("Error decoding JSON response")
            else:
                # Handle non-JSON response
                response = await resp.text()
                raise UnexpectedResponseFormatException(f"Unexpected response format: {response}")
        except UnexpectedResponseFormatException as err:
            return False
        except JSONDecodeErrorException as err:
            return False
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
            resp = await http_client.post(f"{self.game_url}/daily-reward?offset=-180", ssl=False)
            txt = await resp.text()
            return True if txt == "OK" else txt
        except Exception as e:
            self.error(f"Error occurred during claim daily reward: {e}")

    async def check_elig_dogs(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get(
                f"{self.game_url_v2}/game/eligibility/dogs_drop", ssl=False
            )
            resp_json = await resp.json()
            return resp_json.get("eligible", False)
        except json.JSONDecodeError as err:
            raise JSONDecodeErrorException("check_elig_dogs not expected response")
        except Exception as error:
            self.error(f"check_elig_dogs task error {error}")
            return False

    async def refresh_token(self, http_client: aiohttp.ClientSession, token):
        if "Authorization" in http_client.headers:
            del http_client.headers["Authorization"]
        json_data = {"refresh": token}
        resp = await http_client.post(f"{self.user_url}/auth/refresh", json=json_data, ssl=False)
        resp_json = await resp.json()

        return resp_json.get("access"), resp_json.get("refresh")

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(
                url="https://httpbin.org/ip", timeout=aiohttp.ClientTimeout(5)
            )
            ip = (await response.json()).get("origin")
            self.info(f"Bind with proxy IP: <lc>{ip}</lc>")
        except asyncio.TimeoutError as err:
            self.warning(f"Got timeout while checking proxy: {proxy}, skipping...")
        except aiohttp.ClientConnectorError as err:
            self.warning(f"Connection error while checking proxy: {proxy}, skipping...")
        except Exception as error:
            self.error(f"Proxy: {proxy} | Error: {error}")

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
        first_name = tele_user_obj.get("first_name")
        self.session_name = (
            tele_user_obj.get("username") if tele_user_obj.get("username") else first_name
        )

        if settings.USE_RANDOM_DELAY_IN_RUN.lower() == "true":
            random_delay = random.randint(
                settings.RANDOM_DELAY_IN_RUN[0], settings.RANDOM_DELAY_IN_RUN[1]
            )
            self.info(f"🤖 Bot will start in <ly>{format_duration(random_delay)}</ly>")
            await asyncio.sleep(random_delay)

        access_token = None
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        http_client = CloudflareScraper(headers=self.headers, connector=proxy_conn)
        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)
        http_client.headers["User-Agent"] = self.check_user_agent()
        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
                    http_client = CloudflareScraper(headers=self.headers, connector=proxy_conn)
                    http_client.headers["User-Agent"] = self.check_user_agent()
                if time.time() - self.access_token_created_time >= 3000:
                    if "Authorization" in http_client.headers:
                        del http_client.headers["Authorization"]

                    access_token, refresh_token = await self.login(
                        http_client=http_client, initdata=init_data
                    )

                    if access_token:
                        self.success("Successfully Login")
                    else:
                        self.error(f"Login failed, retrying in <ly>{format_duration(60)}</ly>")
                        self.access_token_created_time = 0
                        await asyncio.sleep(60)
                        continue

                    http_client.headers["Authorization"] = f"Bearer {access_token}"

                    self.access_token_created_time = time.time()

                timestamp, start_time, end_time, play_passes, balance = await self.balance(
                    http_client=http_client
                )
                if not balance:
                    self.error(
                        f"Error while checking balance, retrying in <ly>{format_duration(60)}</ly>"
                    )
                    self.access_token_created_time = 0
                    await asyncio.sleep(60)
                    continue
                self.info(f"Balance : <lg>{int(float(balance)):,}</lg>")

                await asyncio.sleep(1.5)

                msg = await self.claim_daily_reward(http_client=http_client)
                if isinstance(msg, bool) and msg:
                    self.success("Successfully claim daily reward!")

                claim_amount, is_available = await self.friend_balance(http_client=http_client)

                if claim_amount != 0 and is_available:
                    amount = await self.friend_claim(http_client=http_client)
                    if amount:
                        self.success(
                            f"Successfully claim friend ref reward: <lg>(+{int(float(amount)):,})</lg>"
                        )

                await asyncio.sleep(1.5)

                elig_dogs_drop = await self.check_elig_dogs(http_client=http_client)
                if elig_dogs_drop:
                    self.info("<lg>Your account is eligible for Dogs drop in play game</lg>")
                else:
                    self.warning("Your account is not eligible for Dogs drop in play game")

                if isinstance(play_passes, int):
                    self.info(f"You have <lg>{play_passes}</lg> play ticket ")

                if play_passes and play_passes > 0 and settings.PLAY_GAMES.lower() == "true":
                    await self.play_game(
                        http_client=http_client,
                        play_passes=play_passes,
                        refresh_token=refresh_token,
                    )

                await asyncio.sleep(1.5)

                tasks = await self.get_tasks(http_client=http_client)

                for task in tasks:
                    if (
                        task.get("status") == "NOT_STARTED"
                        and task.get("type") != "PROGRESS_TARGET"
                    ):
                        self.info(f"Started doing task: <lc>{task['title']}</lc>")
                        await self.start_complete_task(http_client=http_client, task_id=task["id"])
                        await asyncio.sleep(1)

                await asyncio.sleep(5)

                tasks = await self.get_tasks(http_client=http_client)
                for task in tasks:
                    if task.get("status"):
                        if task["status"] == "READY_FOR_CLAIM" and task["type"] != "PROGRESS_TASK":
                            status = await self.claim_task(
                                http_client=http_client, task_id=task["id"]
                            )
                            if status:
                                self.success(f"Claimed task: <lc>{task['title']}</lc>")
                            await asyncio.sleep(1)
                        elif (
                            task["status"] == "READY_FOR_VERIFY"
                            and task["validationType"] == "KEYWORD"
                        ):
                            status = await self.validate_task(
                                http_client=http_client, task_id=task["id"], title=task["title"]
                            )

                            if status:
                                self.success(f"Validated task: <lc>{task['title']}</lc>")

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
                        f"Successfully claim farming reward!, Balance: <lg>{int(float(balance)):,}</lg>"
                    )
                    await asyncio.sleep(1)

                    start_time, end_time = await self.start_farming(http_client=http_client)
                    self.info(f"Start farming!")
                    await asyncio.sleep(1)

                elif start_time is None and end_time is None:
                    start_time, end_time = await self.start_farming(http_client=http_client)
                    self.info(f"Start farming!")
                    await asyncio.sleep(1)

                random_offset_sec = random.randint(30, 300)
                default_sleep_duration = 3600
                sleep_duration = default_sleep_duration + random_offset_sec
                if end_time and timestamp:
                    sleep_duration = (end_time - timestamp) + random_offset_sec
                self.info(f"Delay <ly>{format_duration(sleep_duration)}</ly>")

                # update membership info
                api_key_result = await check_api_key()
                role, expire_ts_dt = await check_membership_time_left(api_key_result)
                self.role = role
                self.expire_ts = expire_ts_dt

                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                await asyncio.sleep(sleep_duration)

            except InvalidSessionException as error:
                raise error

            except ExpiredTokenException as error:
                self.warning(f"<ly>{error}</ly>")
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                self.access_token_created_time = 0
                await asyncio.sleep(delay=60)
                continue

            except GameSessionNotFoundException as error:
                self.warning(f"<ly>{error}</ly>")
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                self.access_token_created_time = 0
                await asyncio.sleep(delay=60)
                continue

            except ErrorStartGameException as error:
                self.warning(f"<ly>{error}</ly>")
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                self.access_token_created_time = 0
                await asyncio.sleep(delay=60)
                continue

            except ExpiredApiKeyException as error:
                self.error(str(error))
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                break

            except Exception as error:
                error_delay = 300
                self.error(
                    f"Unknown error: {str(error)}, retrying in <ly>{format_duration(error_delay)}</ly>"
                )
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                self.access_token_created_time = 0
                await asyncio.sleep(delay=error_delay)


async def run_tapper(query_id: str, proxy: str | None, role: str, expire_ts: datetime):
    await Tapper(query_id=query_id, role=role, expire_ts=expire_ts).run(proxy=proxy)


async def check_api_key():
    result = None
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://ec2-54-166-158-149.compute-1.amazonaws.com/verify-key/",
            json={"api_key": settings.LICENSE_KEY},
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
        logger.info(f"============================================================")
        logger.info(f"Login as {mapping_role_color(role)} user")
    if role != "admin":
        current_time_utc = datetime.now(pytz.utc)
        if expire_ts_dt < current_time_utc:
            raise ExpiredApiKeyException(
                "Your LICENSE KEY has been expired, please re-subscribe it to continue"
            )
        if show_log:
            membership_expiry_left_ts = expire_ts_dt - current_time_utc
            logger.info(
                f"LICENSE KEY expire time left: <ly>{format_duration(membership_expiry_left_ts.total_seconds())}</ly>"
            )
    return role, expire_ts_dt


async def main():
    try:
        await process()
    except InvalidApiKeyException as err:
        logger.error("Invalid LICENSE KEY !")
    except ExpiredApiKeyException as err:
        logger.error(str(err))
    except MissingApiKeyException as err:
        logger.error(str(err))
    except InvalidSessionException as err:
        logger.error(str(err))
    except FileNotFoundError as err:
        logger.error(str(err))


if __name__ == "__main__":
    panel = Panel(banner, expand=False, border_style="dim cyan")
    console.print(panel, justify="center")
    time.sleep(1)
    with Progress(transient=True) as progress:
        task = progress.add_task("[blue]Checking Bot Version...", total=None)
        version = check_version()
        progress.update(task, total=len(version))
        progress.start_task(task)
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
