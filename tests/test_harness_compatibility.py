"""Old platform imports retain type identity during package extraction."""


def test_shared_contract_and_adapter_identity():
    from story_harness.core.contracts import Snapshot as OldSnapshot
    from storyloop_harness.core.contracts import Snapshot
    from story_harness.core.billing import ModelUsage as OldUsage
    from storyloop_harness.models.usage import ModelUsage
    from story_harness.adapters.telemetry import Telemetry as OldTelemetry
    from storyloop_harness.adapters.telemetry import Telemetry
    from story_harness.adapters.model_config import CompatibleOpenAIChatModel as OldModel
    from storyloop_harness.models.agentscope import CompatibleOpenAIChatModel
    assert OldSnapshot is Snapshot
    assert OldUsage is ModelUsage
    assert OldModel is CompatibleOpenAIChatModel
    assert OldTelemetry is Telemetry
