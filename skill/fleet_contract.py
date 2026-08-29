"""Closed Agent Fleet v1 package contract.

The package describes a read-only 4-12 agent fleet. It is task data, never
model, sandbox, retry, write, credential, or publication authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

FLEET_PACKAGE_VERSION = 1
MIN_AGENTS = 4
MAX_AGENTS = 12
DEFAULT_AGENTS = 6
MAX_PACKAGE_BYTES = 1024 * 1024
MAX_NAME_CHARS = 64
MAX_TEXT_CHARS = 16_000
MAX_ITEM_CHARS = 4_000
MAX_LIST_ITEMS = 128
MAX_CHANGED_FILES = 256
MAX_COMMANDS = 16
MAX_ARGV_ITEMS = 32
MAX_ARGV_CHARS = 8_192
MAX_INLINE_CONTEXT_BYTES = 12 * 1024 * 1024

PRESETS = frozenset(
    {
        "adversarial-review",
        "competing-hypotheses",
        "architecture-council",
        "security-red-blue",
        "test-matrix",
        "repository-audit",
        "research-synthesis",
    }
)

RISK_TAGS = frozenset(
    {
        "public-api",
        "schema",
        "migration",
        "security",
        "credentials",
        "permissions",
        "concurrency",
        "state-machine",
        "recovery",
        "persistence",
        "release",
        "sandbox",
        "integrity",
        "platform",
        "performance",
    }
)

SAFE_VALIDATION_EXECUTABLES = frozenset({"python", "python3", "py", "pytest"})
FORBIDDEN_PYTHON_MODULES = frozenset(
    {"pip", "ensurepip", "venv", "build", "twine", "http.server", "pydoc"}
)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

TOP_KEYS = frozenset(
    {
        "version",
        "name",
        "preset",
        "agent_count",
        "objective",
        "acceptance_criteria",
        "scope",
        "exclusions",
        "candidate",
        "risk_tags",
        "verification",
        "limits",
    }
)
CANDIDATE_KEYS = frozenset(
    {"repository_full_name", "expected_head_sha", "changed_files"}
)
VERIFICATION_KEYS = frozenset({"required_ids", "commands"})
COMMAND_KEYS = frozenset({"id", "argv", "timeout_seconds"})
LIMIT_KEYS = frozenset(
    {
        "max_patch_bytes",
        "max_untracked_file_bytes",
        "max_candidate_bytes",
        "max_agent_output_bytes",
        "max_agent_log_bytes",
    }
)
LIMIT_RANGES: dict[str, tuple[int, int]] = {
    "max_patch_bytes": (1, 2 * 1024 * 1024),
    "max_untracked_file_bytes": (1, 512 * 1024),
    "max_candidate_bytes": (1, 4 * 1024 * 1024),
    "max_agent_output_bytes": (1, 2 * 1024 * 1024),
    "max_agent_log_bytes": (1, 8 * 1024 * 1024),
}

WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class FleetContractError(RuntimeError):
    """The Agent Fleet package is malformed or exceeds a trusted boundary."""


@dataclass(frozen=True)
class FleetPackage:
    value: dict[str, Any]
    digest: str

    @property
    def name(self) -> str:
        return self.value["name"]

    @property
    def preset(self) -> str:
        return self.value["preset"]

    @property
    def agent_count(self) -> int:
        return self.value["agent_count"]

    @property
    def objective(self) -> str:
        return self.value["objective"]

    @property
    def candidate(self) -> Mapping[str, Any]:
        return self.value["candidate"]

    @property
    def verification(self) -> Mapping[str, Any]:
        return self.value["verification"]

    @property
    def limits(self) -> Mapping[str, int]:
        return self.value["limits"]

    @property
    def risk_tags(self) -> tuple[str, ...]:
        return tuple(self.value["risk_tags"])


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FleetContractError(f"value is not canonical UTF-8 JSON: {exc}") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FleetContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FleetContractError(f"non-finite JSON number is forbidden: {value}")


def load_json_strict(path: str | Path, *, maximum_bytes: int = MAX_PACKAGE_BYTES) -> Any:
    source = Path(path).expanduser()
    try:
        if source.is_symlink():
            raise FleetContractError("package file cannot be a symlink")
        if not source.is_file():
            raise FleetContractError(f"package file does not exist: {source}")
        size = source.stat().st_size
        if size <= 0 or size > maximum_bytes:
            raise FleetContractError(
                f"package file size must be 1..{maximum_bytes} bytes: {size}"
            )
        raw = source.read_bytes()
    except FleetContractError:
        raise
    except OSError as exc:
        raise FleetContractError(f"cannot read package file {source}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise FleetContractError("package must be UTF-8 without BOM")
    if b"\x00" in raw:
        raise FleetContractError("package cannot contain NUL")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_constant,
        )
    except FleetContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FleetContractError(f"package is not strict UTF-8 JSON: {exc}") from exc


def _closed(value: Any, *, where: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetContractError(f"{where} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise FleetContractError(
            f"{where} keys mismatch: missing={missing} unknown={unknown}"
        )
    return value


def _text(value: Any, *, where: str, maximum: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        raise FleetContractError(f"{where} must be a string")
    result = value.strip()
    if not result or "\x00" in result or len(result) > maximum:
        raise FleetContractError(f"{where} must be a bounded non-empty string")
    try:
        result.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise FleetContractError(f"{where} must be UTF-8 encodable") from exc
    return result


def _integer(value: Any, *, where: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FleetContractError(f"{where} must be an integer")
    if not minimum <= value <= maximum:
        raise FleetContractError(f"{where} must be between {minimum} and {maximum}")
    return value


def _string_list(
    value: Any,
    *,
    where: str,
    minimum: int = 0,
    maximum: int = MAX_LIST_ITEMS,
    item_maximum: int = MAX_ITEM_CHARS,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise FleetContractError(
            f"{where} must contain {minimum}..{maximum} strings"
        )
    result = [
        _text(item, where=f"{where}[{index}]", maximum=item_maximum)
        for index, item in enumerate(value)
    ]
    if len({item.casefold() for item in result}) != len(result):
        raise FleetContractError(f"{where} must be case-insensitively unique")
    return result


def normalize_repo_path(value: Any, *, where: str) -> str:
    raw = _text(value, where=where, maximum=512)
    if raw != value:
        raise FleetContractError(f"{where} cannot have surrounding whitespace")
    if "\\" in raw or raw.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", raw):
        raise FleetContractError(f"{where} must be repository-relative POSIX form")
    if raw.endswith("/"):
        raise FleetContractError(f"{where} must name a file")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise FleetContractError(f"{where} contains an unsafe path segment")
    if any(part.casefold() == ".git" for part in parts):
        raise FleetContractError(f"{where} cannot enter .git")
    for part in parts:
        if part.endswith((" ", ".")):
            raise FleetContractError(f"{where} has a Windows-ambiguous segment")
        if part.split(".", 1)[0].casefold() in WINDOWS_RESERVED:
            raise FleetContractError(f"{where} uses a Windows reserved name")
    normalized = PurePosixPath(*parts).as_posix()
    if normalized != raw:
        raise FleetContractError(f"{where} is not canonical POSIX form")
    return normalized


def _validation_argv(value: Any, *, where: str) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ARGV_ITEMS:
        raise FleetContractError(f"{where} must contain 1..{MAX_ARGV_ITEMS} tokens")
    argv: list[str] = []
    for index, item in enumerate(value):
        token = _text(item, where=f"{where}[{index}]", maximum=1024)
        if token != item or "\n" in token or "\r" in token:
            raise FleetContractError(f"{where}[{index}] is not a canonical token")
        argv.append(token)
    if sum(len(item) for item in argv) > MAX_ARGV_CHARS:
        raise FleetContractError(f"{where} exceeds {MAX_ARGV_CHARS} characters")
    executable = argv[0].casefold()
    if "/" in argv[0] or "\\" in argv[0] or executable not in SAFE_VALIDATION_EXECUTABLES:
        raise FleetContractError(
            f"{where}[0] must be one of {sorted(SAFE_VALIDATION_EXECUTABLES)}"
        )
    lowered = [item.casefold() for item in argv]
    if "-c" in lowered or "--command" in lowered or "-" in argv[1:]:
        raise FleetContractError(f"{where} cannot execute inline or stdin code")
    if "-m" in lowered:
        module_index = lowered.index("-m") + 1
        if module_index >= len(argv):
            raise FleetContractError(f"{where} has -m without a module")
        if lowered[module_index] in FORBIDDEN_PYTHON_MODULES:
            raise FleetContractError(
                f"{where} cannot execute module {argv[module_index]!r}"
            )
    for token in argv[1:]:
        if token.startswith(("http://", "https://")):
            raise FleetContractError(f"{where} cannot contain a network URL")
        if token.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", token):
            raise FleetContractError(f"{where} cannot contain an absolute path")
        if token in {".", ".."} or token.startswith("../") or "/../" in token:
            raise FleetContractError(f"{where} cannot traverse outside the repository")
    return argv


def validate_package(raw: Any) -> FleetPackage:
    top = _closed(raw, where="package", keys=TOP_KEYS)
    if top["version"] != FLEET_PACKAGE_VERSION or isinstance(top["version"], bool):
        raise FleetContractError(
            f"package.version must be integer {FLEET_PACKAGE_VERSION}"
        )
    name = _text(top["name"], where="package.name", maximum=MAX_NAME_CHARS)
    if NAME_RE.fullmatch(name) is None:
        raise FleetContractError("package.name must be a lowercase identifier")
    preset = _text(top["preset"], where="package.preset", maximum=80)
    if preset not in PRESETS:
        raise FleetContractError(f"package.preset must be one of {sorted(PRESETS)}")
    agent_count = _integer(
        top["agent_count"],
        where="package.agent_count",
        minimum=MIN_AGENTS,
        maximum=MAX_AGENTS,
    )
    objective = _text(top["objective"], where="package.objective")
    acceptance = _string_list(
        top["acceptance_criteria"],
        where="package.acceptance_criteria",
        minimum=1,
        maximum=64,
    )
    scope = _string_list(top["scope"], where="package.scope", minimum=1, maximum=64)
    exclusions = _string_list(
        top["exclusions"], where="package.exclusions", maximum=64
    )

    candidate_raw = _closed(
        top["candidate"], where="package.candidate", keys=CANDIDATE_KEYS
    )
    repository = _text(
        candidate_raw["repository_full_name"],
        where="package.candidate.repository_full_name",
        maximum=201,
    )
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise FleetContractError(
            "package.candidate.repository_full_name must be owner/repository"
        )
    head = candidate_raw["expected_head_sha"]
    if not isinstance(head, str) or HEX40_RE.fullmatch(head) is None:
        raise FleetContractError(
            "package.candidate.expected_head_sha must be 40 lowercase hex"
        )
    changed_raw = candidate_raw["changed_files"]
    if not isinstance(changed_raw, list) or len(changed_raw) > MAX_CHANGED_FILES:
        raise FleetContractError(
            f"package.candidate.changed_files must contain 0..{MAX_CHANGED_FILES} paths"
        )
    changed = [
        normalize_repo_path(item, where=f"package.candidate.changed_files[{index}]")
        for index, item in enumerate(changed_raw)
    ]
    if len({item.casefold() for item in changed}) != len(changed):
        raise FleetContractError(
            "package.candidate.changed_files must be case-insensitively unique"
        )

    risk_raw = top["risk_tags"]
    if not isinstance(risk_raw, list) or len(risk_raw) > len(RISK_TAGS):
        raise FleetContractError("package.risk_tags must be a bounded array")
    if any(not isinstance(item, str) or item not in RISK_TAGS for item in risk_raw):
        raise FleetContractError(f"package.risk_tags must be drawn from {sorted(RISK_TAGS)}")
    risk_tags = sorted(set(risk_raw))
    if len(risk_tags) != len(risk_raw):
        raise FleetContractError("package.risk_tags must be unique")

    verification_raw = _closed(
        top["verification"], where="package.verification", keys=VERIFICATION_KEYS
    )
    required = _string_list(
        verification_raw["required_ids"],
        where="package.verification.required_ids",
        maximum=MAX_COMMANDS,
        item_maximum=80,
    )
    for item in required:
        if IDENTIFIER_RE.fullmatch(item) is None:
            raise FleetContractError(f"invalid verification identifier: {item!r}")
    commands_raw = verification_raw["commands"]
    if not isinstance(commands_raw, list) or len(commands_raw) > MAX_COMMANDS:
        raise FleetContractError(
            f"package.verification.commands must contain 0..{MAX_COMMANDS} commands"
        )
    commands: list[dict[str, Any]] = []
    command_ids: list[str] = []
    for index, value in enumerate(commands_raw):
        command = _closed(
            value,
            where=f"package.verification.commands[{index}]",
            keys=COMMAND_KEYS,
        )
        identifier = _text(
            command["id"],
            where=f"package.verification.commands[{index}].id",
            maximum=80,
        )
        if IDENTIFIER_RE.fullmatch(identifier) is None:
            raise FleetContractError(f"invalid verification identifier: {identifier!r}")
        command_ids.append(identifier)
        commands.append(
            {
                "id": identifier,
                "argv": _validation_argv(
                    command["argv"],
                    where=f"package.verification.commands[{index}].argv",
                ),
                "timeout_seconds": _integer(
                    command["timeout_seconds"],
                    where=f"package.verification.commands[{index}].timeout_seconds",
                    minimum=1,
                    maximum=3600,
                ),
            }
        )
    if len(set(command_ids)) != len(command_ids):
        raise FleetContractError("verification command identifiers must be unique")
    if not set(required) <= set(command_ids):
        raise FleetContractError(
            "required verification identifiers must reference declared commands"
        )

    limits_raw = _closed(top["limits"], where="package.limits", keys=LIMIT_KEYS)
    limits = {
        key: _integer(
            limits_raw[key],
            where=f"package.limits.{key}",
            minimum=minimum,
            maximum=maximum,
        )
        for key, (minimum, maximum) in LIMIT_RANGES.items()
    }
    if limits["max_untracked_file_bytes"] > limits["max_candidate_bytes"]:
        raise FleetContractError(
            "max_untracked_file_bytes cannot exceed max_candidate_bytes"
        )
    if limits["max_patch_bytes"] > limits["max_candidate_bytes"]:
        raise FleetContractError("max_patch_bytes cannot exceed max_candidate_bytes")
    worst_case_inline = (
        limits["max_candidate_bytes"]
        + agent_count * limits["max_agent_output_bytes"]
    )
    if worst_case_inline > MAX_INLINE_CONTEXT_BYTES:
        raise FleetContractError(
            "candidate plus worst-case fleet outputs exceed the bounded inline "
            f"context budget of {MAX_INLINE_CONTEXT_BYTES} bytes"
        )

    normalized = {
        "version": FLEET_PACKAGE_VERSION,
        "name": name,
        "preset": preset,
        "agent_count": agent_count,
        "objective": objective,
        "acceptance_criteria": acceptance,
        "scope": scope,
        "exclusions": exclusions,
        "candidate": {
            "repository_full_name": repository,
            "expected_head_sha": head,
            "changed_files": changed,
        },
        "risk_tags": risk_tags,
        "verification": {"required_ids": required, "commands": commands},
        "limits": limits,
    }
    return FleetPackage(normalized, canonical_digest(normalized))


def load_package(path: str | Path) -> FleetPackage:
    return validate_package(load_json_strict(path))


def fleet_contract() -> dict[str, Any]:
    return {
        "package_version": FLEET_PACKAGE_VERSION,
        "agent_count": {"minimum": MIN_AGENTS, "default": DEFAULT_AGENTS, "maximum": MAX_AGENTS},
        "presets": sorted(PRESETS),
        "risk_tags": sorted(RISK_TAGS),
        "validation_executables": sorted(SAFE_VALIDATION_EXECUTABLES),
        "max_inline_context_bytes": MAX_INLINE_CONTEXT_BYTES,
        "model_selectable_by_package": False,
        "write_authority": False,
        "automatic_retry": False,
        "majority_vote": False,
    }
