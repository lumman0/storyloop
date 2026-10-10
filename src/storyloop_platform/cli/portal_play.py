"""Login, choose a game, and play through a terminal menu."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from uuid import uuid4

from storyloop_platform.cli.guidance_view import format_turn_output
from storyloop_platform.cli.startup import (
    launch_portal,
    persist_credentials,
    prepare_credentials,
)
from storyloop_platform.portal.local_config import LocalPreferences
from storyloop_platform.portal.service import PlayerPortal
from storyloop_platform.bootstrap import build_portal
from storyloop_platform.runtime.guidance import GuidanceResult


def _show(view: dict) -> None:
    if view["opening"]:
        print(view["opening"])
    status = f"[第 {view['day']} 天 | tick {view['tick']}]" if view["day"] is not None else f"[tick {view['tick']}]"
    print(format_turn_output(view["body"], status,
                             GuidanceResult(tuple(view["suggestions"]), "portal")))


async def play(portal: PlayerPortal, preferences: LocalPreferences | None = None) -> None:
    print("玩家入口 | /quit 退出")
    cached = preferences.session(portal.db_path) if preferences else None
    token = None
    if cached and isinstance(cached.get("token"), str):
        try:
            portal.accounts.resolve_token(cached["token"])
            token = cached["token"]
            print(f"已恢复登录：{cached.get('username', '玩家')}")
        except PermissionError:
            preferences.clear_session(portal.db_path)
    while token is None:
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
            token = session["token"]
            if preferences:
                preferences.save_session(portal.db_path, username, token)
            break
        except EOFError:
            return
        except (ValueError, PermissionError) as error:
            print(f"[登录未生效] {error}")
    if not cached or token != cached.get("token"):
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
                choice = input("选择编号，或 /logout、/quit: ").strip()
            except EOFError:
                break
            if choice == "/quit":
                break
            if choice == "/logout":
                portal.logout(token)
                if preferences:
                    preferences.clear_session(portal.db_path)
                break
            try:
                if choice.startswith("s") and choice[1:].isdigit():
                    index = int(choice[1:]) - 1
                    if index < 0 or index >= len(saves):
                        raise ValueError("存档编号无效")
                    save = saves[index]
                    catalog_id = save["catalog_id"]
                    resume = save["game_id"]
                else:
                    index = int(choice) - 1
                    if index < 0 or index >= len(games):
                        raise ValueError("游戏编号无效")
                    catalog_id = games[index]["id"]
                    resume = None
                names = prepare_credentials(portal.settings, preferences, prompt=True, require=True)
                if preferences:
                    persist_credentials(preferences, names)
                view = await (portal.resume_save(token, resume) if resume is not None
                              else portal.create_save(token, catalog_id))
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
    parser.add_argument("--catalog", help="scenario catalog; remembered after first launch")
    parser.add_argument("--profile", choices=("local", "online"), default="local")
    parser.add_argument("--config", help="deployment settings; remembered after successful local launch")
    parser.add_argument("--db", help="SQLite database shared by accounts and games")
    args = parser.parse_args()
    preferences = LocalPreferences() if args.profile == "local" else None
    try:
        portal = launch_portal(profile=args.profile, config=args.config, catalog=args.catalog,
                               db=args.db, preferences=preferences, prompt=sys.stdin.isatty(),
                               portal_factory=build_portal)
    except FileNotFoundError:
        parser.error("selected settings or catalog file does not exist")
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(play(portal, preferences))


if __name__ == "__main__":
    main()
