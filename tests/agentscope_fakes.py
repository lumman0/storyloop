"""Small AgentScope 2 model doubles for game runtime tests."""

import json
from functools import wraps

from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock, ToolCallBlock
from agentscope.model import ChatModelBase as SDKChatModelBase
from agentscope.model import ChatResponse as SDKChatResponse
from agentscope.model import StructuredResponse


class ChatModelBase(SDKChatModelBase):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        original = cls.__dict__.get("__call__")
        if original is not None:
            @wraps(original)
            async def call(self, *args, **kwargs):
                if not args and "messages" in kwargs:
                    args = (kwargs.pop("messages"),)
                if args and isinstance(args[0], list) and args[0] and isinstance(args[0][0], Msg):
                    args = ([item.model_dump(mode="json") for item in args[0]], *args[1:])
                response = await original(self, *args, **kwargs)
                has_structured_tool = any(
                    item.get("function", {}).get("name") == "GenerateStructuredOutput"
                    for item in kwargs.get("tools") or []
                )
                if has_structured_tool:
                    for block in response.content:
                        if isinstance(block, ToolCallBlock) and block.name == "generate_response":
                            block.name = "GenerateStructuredOutput"
                    if response.metadata and not any(
                        isinstance(block, ToolCallBlock) for block in response.content
                    ):
                        response.content = [ToolCallBlock(
                            id="structured-test", name="GenerateStructuredOutput",
                            input=json.dumps(response.metadata, ensure_ascii=False),
                        )]
                return response
            cls.__call__ = call

    def __init__(self, model_name: str, stream: bool = False) -> None:
        super().__init__(credential=OpenAICredential(api_key="test-key"),
                         model=model_name, parameters=self.Parameters(), stream=stream)
        self.model_name = model_name
        self.formatter = OpenAIChatFormatter()

    async def generate_structured_output(self, messages, structured_model, **kwargs):
        response = await self(messages, structured_model=structured_model, **kwargs)
        content = response.metadata
        if not content:
            for block in response.content:
                if isinstance(block, ToolCallBlock) and block.name == "generate_response":
                    content = json.loads(block.input)
                    break
        return StructuredResponse(content=content, usage=response.usage)


def ChatResponse(content, *, metadata=None, usage=None):
    blocks = []
    for block in content:
        if not isinstance(block, dict):
            blocks.append(block)
        elif block.get("type") == "tool_use":
            blocks.append(ToolCallBlock(
                id=block["id"], name=block["name"],
                input=block.get("raw_input") or json.dumps(block.get("input", {})),
            ))
        elif block.get("type") == "text":
            blocks.append(TextBlock(text=block["text"]))
        else:
            raise ValueError(f"unsupported test block: {block.get('type')}")
    return SDKChatResponse(content=blocks, is_last=True,
                           metadata=metadata or {}, usage=usage)
