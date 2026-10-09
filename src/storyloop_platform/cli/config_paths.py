"""Resolve command configuration, including remembered bundled paths from upgrades."""
from pathlib import Path


def select_config(explicit: str | None, remembered: str | None, default: Path) -> str:
    """Migrate only a missing implicit default; persist through normal startup later."""
    if explicit is not None:
        return explicit
    if remembered:
        previous = Path(remembered)
        if not (previous.is_absolute() and not previous.exists()
                and previous.parts[-3:] == ("story_harness", "defaults", default.name)):
            return remembered
    return str(default)
