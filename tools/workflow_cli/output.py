import json
import os
import sys

# Exit codes
EXIT_OK = 0        # success
EXIT_CLI_ERR = 2   # CLI/input error (missing args, unknown command)
EXIT_GATE_FAIL = 3 # gate check failure (entry or quality gate)
EXIT_DRY_RUN = 4   # dry-run mode, no changes made
EXIT_REVIEW_REQ = 5  # forced subagent review required
EXIT_CONFLICT = 6  # state conflict (run already closed, etc.)
EXIT_NOT_FOUND = 7 # resource not found (run.md, artifact, etc.)


def is_json_mode() -> bool:
    """Check if JSON output mode is enabled via R2P_JSON environment variable."""
    return os.environ.get("R2P_JSON", "0") == "1"


def format_success(data: dict, message: str = "") -> str:
    """Format a success response."""
    if is_json_mode():
        return json.dumps({"status": "ok", "message": message, **data}, indent=2)

    lines = []
    if message:
        lines.append(f"✓ {message}")

    for key, value in data.items():
        if isinstance(value, (list, dict)):
            lines.append(f"  {key}:")
            if isinstance(value, list):
                for item in value:
                    lines.append(f"    - {item}")
            else:
                for k, v in value.items():
                    lines.append(f"    {k}: {v}")
        else:
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def format_error(message: str, details: list[str] | None = None, exit_code: int = EXIT_CLI_ERR) -> str:
    """Format an error response."""
    if is_json_mode():
        payload = {"status": "error", "message": message, "exit_code": exit_code}
        if details:
            payload["details"] = details
        return json.dumps(payload, indent=2)

    lines = [f"✗ {message}"]
    if details:
        for d in details:
            lines.append(f"  • {d}")

    return "\n".join(lines)


def format_stop(reason: str, next_step: str = "", data: dict | None = None) -> str:
    """Format a stop condition (workflow needs user input)."""
    if is_json_mode():
        payload = {"status": "stop", "reason": reason}
        if next_step:
            payload["next_step"] = next_step
        if data:
            payload.update(data)
        return json.dumps(payload, indent=2)

    lines = [f"⏸ {reason}"]
    if next_step:
        lines.append(f"  → {next_step}")

    return "\n".join(lines)


def format_gate_result(gate_result, gate_type: str = "gate") -> str:
    """Format a GateResult for output."""
    if gate_result.passed:
        return format_success({"gate": gate_type}, message=f"{gate_type} passed")
    return format_error(
        f"{gate_type} failed",
        details=gate_result.issues,
        exit_code=gate_result.exit_code,
    )


def print_and_exit(output: str, exit_code: int = EXIT_OK) -> None:
    """Print output and exit with given code."""
    print(output)
    sys.exit(exit_code)
