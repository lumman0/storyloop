"""Check Flash and Max with a one-line live request; never persist the API key."""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import sys

from storyloop_platform.config import ModelFactory, default_settings


async def check_models(router: ModelFactory) -> dict[str, object]:
    results: dict[str, object] = {}
    for task in ("followup_actions", "single_turn"):
        model = router.create_model(task)
        try:
            response = await model(
                [{"role": "user", "content": "请只回复 OK"}],
                max_tokens=64,
            )
            content = response.content
            results[model.model_name] = {
                "ok": bool(content),
                "content_types": [item.get("type") for item in content],
            }
        except Exception as error:
            results[model.model_name] = {
                "ok": False,
                "error_type": type(error).__name__,
                "status_code": getattr(error, "status_code", None),
            }
    return results


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = os.getenv("STORY_MODEL_API_KEY") or getpass.getpass("百炼 API Key（输入不回显）: ")
    router = ModelFactory(default_settings(), env={"STORY_MODEL_API_KEY": key})
    print(json.dumps(asyncio.run(check_models(router)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
