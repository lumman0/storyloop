"""Register the game's read-only tools with AgentScope 2 permissions."""

from collections.abc import Callable

from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, Toolkit


class ReadOnlyToolkit(Toolkit):
    def register_tool_function(self, function: Callable) -> None:
        tool = FunctionTool(
            function,
            is_read_only=True,
            permission=PermissionDecision(PermissionBehavior.ALLOW, "Game read-only tool"),
        )
        self.tool_groups[0].tools.append(tool)
