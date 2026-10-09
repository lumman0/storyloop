"""The wheel builder must consume an immutable, explicit harness source."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("build_harness", Path(__file__).resolve().parents[1] / "scripts/build_harness.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@pytest.mark.parametrize("source", [{}, {"git": "https://example.com/harness.git", "rev": "main"}, {"path": "../harness"}, {"git": "https://example.com/harness.git", "rev": "a" * 39}])
def test_rejects_missing_mutable_or_neighbor_source(source):
    with pytest.raises(ValueError, match="immutable"):
        module.harness_requirement({"tool": {"uv": {"sources": {"storyloop-harness": source}}}})

def test_uses_exact_metadata_commit():
    source = {"git": "https://example.com/harness.git", "rev": "a" * 40}
    assert module.harness_requirement({"tool": {"uv": {"sources": {"storyloop-harness": source}}}}) == "git+https://example.com/harness.git@" + "a" * 40
