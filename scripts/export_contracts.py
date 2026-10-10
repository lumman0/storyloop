"""Export the API-owned Pydantic roots to standard JSON Schema on stdout."""
import json
from pathlib import Path
import sys

# Regenerate from this checkout even when Python has an older wheel installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storyloop_platform.api.contracts import contract_schemas

sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(contract_schemas(), ensure_ascii=False, sort_keys=True, indent=2))
