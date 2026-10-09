"""Check configured model tasks with one bounded request per task."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Iterable

from storyloop_platform.cli.startup import load_profile_settings, prepare_credentials
from storyloop_platform.config import ModelFactory
from storyloop_platform.portal.local_config import LocalPreferences


def _failure(error: Exception) -> dict:
    status = getattr(error, "status_code", None)
    return {"ok": False, "error_type": type(error).__name__,
            "status_code": status if isinstance(status, int) else None}


async def check_models(factory: ModelFactory, tasks: Iterable[str]) -> list[dict]:
    selected = tuple(dict.fromkeys(tasks))
    for task in selected:
        factory.settings.model_for(task)
    results = []
    # SDK retry logs can contain provider exception bodies. This standalone check
    # reports only structured outcomes and restores logging when it finishes.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for task in selected:
            result = {"task": task, "model": factory.settings.model_for(task).model}
            model = None
            try:
                model = factory.create_model(task)
                response = await model([{"role": "user", "content": "Reply only OK."}],
                                       max_completion_tokens=64)
                result["ok"] = bool(response.content)
            except Exception as error:
                result.update(_failure(error))
            finally:
                if model is not None:
                    await model.client.close()
            results.append(result)
    finally:
        logging.disable(previous)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="deployment settings file")
    parser.add_argument("--profile", choices=("local", "online"), default="local")
    parser.add_argument("--task", action="append", help="configured task; repeat to select several (default: all routes)")
    args = parser.parse_args()
    try:
        settings = load_profile_settings(args.config, args.profile)
        tasks = tuple(args.task or settings.routes)
        # Validate every selection before any credential prompt or model request.
        for task in tasks:
            settings.model_for(task)
        preferences = LocalPreferences() if args.profile == "local" else None
        prepare_credentials(settings, preferences, tasks=tasks, include_memory=False,
                            prompt=sys.stdin.isatty(), require=True)
        results = asyncio.run(check_models(ModelFactory(settings), tasks))
    except Exception as error:
        results = [_failure(error)]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
