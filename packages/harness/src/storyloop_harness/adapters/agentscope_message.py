"""Small constructor for the AgentScope 2 message format used by the game."""

from agentscope.message import Msg as AgentScopeMsg, SystemMsg, UserMsg


def Msg(name: str, content: str, role: str) -> AgentScopeMsg:
    if role == "system":
        return SystemMsg(name=name, content=content)
    if role == "user":
        return UserMsg(name=name, content=content)
    raise ValueError(f"unsupported message role: {role}")
