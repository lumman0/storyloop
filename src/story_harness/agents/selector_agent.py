"""Compatibility alias; implementation lives in storyloop-platform."""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module('storyloop_platform.legacy.selector_agent')
