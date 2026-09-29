"""Login, choose a game, and play through a terminal menu."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from uuid import uuid4

from story_harness.cli.guidance_view import format_turn_output
from story_harness.cli.react_play import DEFAULT_CONFIG
from story_harness.portal.service import PlayerPortal
from story_harness.runtime.guidance import GuidanceResult


def _show(view: dict) -> None:
    if view["opening"]:
        print(view["opening"])
    status = f"[第 {view['day']} 天 | tick {view['tick']}]" if view["day"] is not None else f"[tick {view['tick']}]"
    print(format_turn_output(view["body"], status,
                             GuidanceResult(tuple(view["suggestions"]), "portal")))


async def play(portal: PlayerPortal) -> None:
    print("玩家入口 | /quit 退出")
    while True:
        try:
            action = input("登录或注册？[login/register] ").strip().lower()
            if action == "/quit":
                return
            if action not in {"login", "register"}:
                continue
            username = input("用户名: ").strip()
            password = getpass.getpass("密码: ")
            session = (portal.register(username, password) if action == "register"
                       else portal.login(username, password))
            break
        except EOFError:
            return
        except (ValueError, PermissionError) as error:
            print(f"[登录未生效] {error}")
    token = session["token"]
    print("登录成功。")
    try:
        while True:
            games = portal.games(token)
            saves = portal.saves(token)
            print("\n新游戏:")
            for index, game in enumerate(games, 1):
                print(f"  {index}. {game['title']} ({game['mode']})")
            print("已有存档:")
            for index, save in enumerate(saves, 1):
                print(f"  s{index}. {save['title']} [tick {save['tick']}]"
                      + (" [已结束]" if save["complete"] else "")
                      + (" [剧本已变化]" if not save["available"] else ""))
            try:
                choice = input("选择编号，或 /quit: ").strip()
            except EOFError:
                break
            if choice == "/quit":
                break
            try:
                if choice.startswith("s") and choice[1:].isdigit():
                    index = int(choice[1:]) - 1
                    if index < 0 or index >= len(saves):
                        raise ValueError("存档编号无效")
                    save = saves[index]
                    catalog_id = save["catalog_id"]
                    operation = portal.resume_save(token, save["game_id"])
                else:
                    index = int(choice) - 1
                    if index < 0 or index >= len(games):
                        raise ValueError("游戏编号无效")
                    catalog_id = games[index]["id"]
                    operation = portal.create_save(token, catalog_id)
                if not os.environ.get(portal.config.api_key_env):
                    os.environ[portal.config.api_key_env] = getpass.getpass("模型 API Key（输入不回显）: ")
                view = await operation
            except (ValueError, IndexError, KeyError) as error:
                print(f"[选择未生效] {error}")
                continue
            print(f"\n{next(game['title'] for game in games if game['id'] == catalog_id)}"
                  f" | game={view['game_id']} | /back 返回目录")
            _show(view)
            while not view["complete"]:
                try:
                    text = input("你> ").strip()
                except EOFError:
                    return
                if text == "/back":
                    break
                if text == "/quit":
                    return
                if not text:
                    continue
                try:
                    view = await portal.turn(token, view["game_id"], text, uuid4().hex)
                except ValueError as error:
                    print(f"[输入未生效] {error}")
                    continue
                _show(view)
    finally:
        portal.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", help="SQLite database shared by accounts and games")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(play(PlayerPortal(args.catalog, args.config, args.db)))


if __name__ == "__main__":
    main()
