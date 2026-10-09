"""Pure helpers for safe Minecraft command execution and locate result parsing."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_RESOURCE_LOCATION = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
# These are the shipped presets. The AstrBot config key
# ``llm_command_allowlist`` can extend or replace them at runtime.
DEFAULT_LLM_COMMAND_ALLOWLIST = [
    "list", "seed", "time", "weather", "difficulty",
    "spark healthreport",
]
_SAFE_ROOT_COMMANDS = set(DEFAULT_LLM_COMMAND_ALLOWLIST[:-1])
_SAFE_EXACT_COMMANDS = {DEFAULT_LLM_COMMAND_ALLOWLIST[-1]}
_LOCATE_TYPES = {"structure", "biome", "poi"}
_BLOCKED_ROOT_COMMANDS = {
    "stop", "op", "deop", "ban", "pardon", "whitelist", "kick", "kill",
    "function", "schedule", "reload", "data", "forceload",
}
_PLAYER_NAME = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def validate_resource_location(value: str, *, max_length: int = 128) -> Tuple[bool, str]:
    value = (value or "").strip().lower()
    if not value or len(value) > max_length or not _RESOURCE_LOCATION.fullmatch(value):
        return False, "target 必须是合法的 Minecraft resource location，例如 minecraft:village"
    return True, value


def build_locate_command(target: str, locate_type: str = "structure", player: str = "") -> Tuple[bool, str, str]:
    locate_type = (locate_type or "").strip().lower()
    if locate_type not in _LOCATE_TYPES:
        return False, "", "locate_type 必须是 structure、biome 或 poi"
    player = (player or "").strip()
    if not _PLAYER_NAME.fullmatch(player):
        return False, "", "player 必须是 1-16 位 Minecraft 玩家名（字母、数字或下划线）"
    valid, normalized = validate_resource_location(target)
    if not valid:
        return False, "", normalized
    return True, f"execute at {player} run locate {locate_type} {normalized}", ""


def command_allowed(command: str, *, allow_arbitrary: bool = False, max_length: int = 256,
                    allowlist: Optional[list[str]] = None) -> Tuple[bool, str]:
    command = (command or "").strip()
    if not command or len(command) > max_length or any(ord(ch) < 32 and ch not in "\t" for ch in command):
        return False, "命令为空、过长或包含控制字符"
    normalized_command = command.lstrip("/").lower()
    root = normalized_command.split(None, 1)[0]
    if root in _BLOCKED_ROOT_COMMANDS:
        return False, f"命令 {root} 默认禁止通过 LLM 工具执行"
    if allow_arbitrary:
        return True, ""
    configured = allowlist if allowlist is not None else DEFAULT_LLM_COMMAND_ALLOWLIST
    normalized_allowlist = {str(item).strip().lstrip("/").lower() for item in configured if str(item).strip()}
    safe_roots = {item for item in normalized_allowlist if " " not in item}
    safe_exact = {item for item in normalized_allowlist if " " in item}
    if root not in safe_roots and root != "execute" and normalized_command not in safe_exact:
        return False, f"命令 {root} 不在 LLM 安全命令白名单中"
    if root == "execute" and not re.match(r"^execute\s+at\s+[A-Za-z0-9_]{1,16}\s+run\s+locate\s+(?:structure|biome|poi)\s+[a-z0-9_.-]+:[a-z0-9_./-]+$", command, re.I):
        return False, "locate 命令必须使用 execute at <玩家名> run locate <structure|biome|poi> <namespace:id> 格式"
    if root == "locate":
        return False, "locate 必须以玩家为中心，通过 execute at <玩家名> run locate 执行"
    return True, ""


def log_delta(before: str, after: str) -> str:
    before, after = before or "", after or ""
    if after.startswith(before):
        return after[len(before):]
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    if len(after_lines) >= len(before_lines) and after_lines[:len(before_lines)] == before_lines:
        return "\n".join(after_lines[len(before_lines):])
    return after


def parse_locate_output(output: str, target: str) -> Dict[str, Any]:
    text = (output or "").strip()
    coordinate_patterns = (
        re.compile(r"\[\s*(-?\d+)\s*,\s*(?:~|[-+]?\d+)\s*,\s*(-?\d+)\s*\]"),
        re.compile(r"(?:\bat\b|坐标为?)\s*[(:【\[]?\s*(-?\d+)\s*[,，、]\s*(-?\d+)\s*[)】\]]?", re.I),
    )
    for pattern in coordinate_patterns:
        match = pattern.search(text)
        if match:
            return {"found": True, "target": target, "coordinates": {"x": int(match.group(1)), "z": int(match.group(2))}, "raw_output": text[-800:]}
    if re.search(r"could not find|not found|无法找到|找不到|没有找到", text, re.I):
        return {"found": False, "target": target, "coordinates": None, "raw_output": text[-800:]}
    return {"found": None, "target": target, "coordinates": None, "raw_output": text[-800:]}


def result_json(status: str, *, instance: str, command: str, accepted: bool, evidence: bool = False,
                output: str = "", reason: str = "", parsed: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"status": status, "instance": instance, "command": command, "accepted": accepted,
            "evidence": evidence, "output": (output or "")[-800:], "reason": reason, "parsed": parsed}
