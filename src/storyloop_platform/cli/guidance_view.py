"""Terminal presentation for optional, non-canonical player guidance."""

from storyloop_platform.runtime.guidance import GuidanceResult


def format_guidance(result: GuidanceResult) -> str:
    if not result.items:
        return ""
    return "── 下一步建议 ──\n" + "\n".join(f"• {item}" for item in result.items)


def format_turn_output(body: str, status: str, guidance: GuidanceResult) -> str:
    """Keep optional guidance visually outside the story and turn status."""
    main = "\n".join(part for part in (body, status) if part)
    panel = format_guidance(guidance)
    return f"{main}\n\n{panel}" if panel else main
