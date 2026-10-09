"""Turn failure metadata must not guess whether an action was committed."""


class TurnInputError(ValueError):
    """Input rejected before any turn work or world mutation begins."""


class TurnRecoveryRequired(ValueError):
    """World work exists without sufficient evidence to settle it safely."""


def turn_failure(error: Exception, request_id: str | None, *,
                 message: str | None = None, code: str = "TURN_FAILED") -> dict:
    unstarted = isinstance(error, TurnInputError)
    recovery_required = isinstance(error, TurnRecoveryRequired)
    return {"code": ("INVALID_TURN_INPUT" if unstarted else
                     "TURN_RECOVERY_REQUIRED" if recovery_required else code),
            "message": message if message is not None else str(error),
            "retryable": not (unstarted or recovery_required),
            "commit_state": "not_started" if unstarted else "unknown",
            "request_id": request_id}
