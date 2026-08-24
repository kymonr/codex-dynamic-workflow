"""Closed Worktree Writer v1 package contract.

The package is data, never authorization outside the exact host binding supplied
on the writer CLI. This module performs no filesystem writes and no model calls.
It deliberately accepts only the v1 create/modify text-file surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

PACKAGE_VERSION = 1
MAX_PACKAGE_BYTES = 1024 * 1024
MAX_NAME_CHARS = 50
MAX_OBJECTIVE_CHARS = 16_000
MAX_TARGET_CHARS = 512
MAX_OWNED_TARGETS = 32
MAX_VERIFICATION_COMMANDS = 16
MAX_ARGV_ITEMS = 32
MAX_ARGV_CHARS = 8_192

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

TOP_KEYS = frozenset(
    {"version", "name", "objective", "base", "authority", "limits", "verification"}
)
BASE_KEYS = frozenset(
    {"repository_full_name", "expected_head_sha", "expected_tree_sha"}
)
AUTHORITY_KEYS = frozenset({"owned_targets", "allowed_actions"})
LIMIT_KEYS = frozenset(
    {
        "max_changed_files",
        "max_patch_bytes",
        "max_created_file_bytes",
        "max_total_candidate_bytes",
    }
)
VERIFICATION_KEYS = frozenset({"required_verification_ids", "commands"})
COMMAND_KEYS = frozenset({"id", "argv", "timeout_seconds"})
GRANTABLE_ACTIONS = frozenset({"create", "modify"})

WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}

SAFE_VALIDATION_EXECUTABLES = frozenset({"python", "python3", "py", "pytest"})
FORBIDDEN_PYTHON_MODULES = frozenset(
    {"pip", "ensurepip", "venv", "build", "twine", "http.server", "pydoc"}
)

LIMIT_RANGES: dict[str, tuple[int, int]] = {
    "max_changed_files": (1, 32),
    "max_patch_bytes": (1, 16 * 1024 * 1024),
    "max_created_file_bytes": (1, 4 * 1024 * 1024),
    "max_total_candidate_bytes": (1, 32 * 1024 * 1024),
}


class WriterContractError(RuntimeError):
    """The Worktree Writer v1 package or binding cannot continue safely."""


@dataclass(frozen=True)
class WriterPackage:
    """Normalized closed package plus its canonical digest."""

    value: dict[str, Any]
    digest: str

    @property
    def name(self) -> str:
        return self.value["name"]

    @property
    def objective(self) -> str:
        return self.value["objective"]

    @property
    def repository_full_name(self) -> str:
        return self.value["base"]["repository_full_name"]

    @property
    def expected_head_sha(self) -> str:
        return self.value["base"]["expected_head_sha"]

    @property
    def expected_tree_sha(self) -> str:
        return self.value["base"]["expected_tree_sha"]

    @property
    def owned_targets(self) -> tuple[str, ...]:
        return tuple(self.value["authority"]["owned_targets"])

    @property
    def allowed_actions(self) -> frozenset[str]:
        return frozenset(self.value["authority"]["allowed_actions"])

    @property
    def limits(self) -> Mapping[str, int]:
        return self.value["limits"]

    @property
    def verification(self) -> Mapping[str, Any]:
        return self.value["verification"]


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WriterContractError(f"value is not canonical UTF-8 JSON: {exc}") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WriterContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise WriterContractError(f"non-finite JSON number is forbidden: {value}")


def load_json_strict(path: str | Path, *, maximum_bytes: int = MAX_PACKAGE_BYTES) -> Any:
    source = Path(path).expanduser()
    try:
        if source.is_symlink():
            raise WriterContractError("package file cannot be a symlink")
        if not source.is_file():
            raise WriterContractError(f"package file does not exist: {source}")
        size = source.stat().st_size
        if size <= 0 or size > maximum_bytes:
            raise WriterContractError(
                f"package file size must be 1..{maximum_bytes} bytes: {size}"
            )
        raw = source.read_bytes()
    except WriterContractError:
        raise
    except OSError as exc:
        raise WriterContractError(f"cannot read package file {source}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise WriterContractError("package must be UTF-8 without BOM")
    if b"\x00" in raw:
        raise WriterContractError("package cannot contain NUL")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_constant,
        )
    except WriterContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterContractError(f"package is not strict UTF-8 JSON: {exc}") from exc


def _closed_object(
    value: Any, *, where: str, keys: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WriterContractError(f"{where} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise WriterContractError(
            f"{where} keys mismatch: missing={missing} unknown={unknown}"
        )
    return value


def _text(value: Any, *, where: str, maximum: int, strip: bool = True) -> str:
    if not isinstance(value, str):
        raise WriterContractError(f"{where} must be a string")
    result = value.strip() if strip else value
    if not result:
        raise WriterContractError(f"{where} must be non-empty")
    if "\x00" in result:
        raise WriterContractError(f"{where} cannot contain NUL")
    if len(result) > maximum:
        raise WriterContractError(f"{where} exceeds {maximum} characters")
    try:
        result.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise WriterContractError(f"{where} must be UTF-8 encodable") from exc
    return result


def _integer(value: Any, *, where: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WriterContractError(f"{where} must be an integer")
    if not minimum <= value <= maximum:
        raise WriterContractError(f"{where} must be between {minimum} and {maximum}")
    return value


def normalize_repo_path(value: Any, *, where: str = "owned target") -> str:
    path = _text(value, where=where, maximum=MAX_TARGET_CHARS, strip=False)
    if path != path.strip():
        raise WriterContractError(f"{where} cannot have leading or trailing whitespace")
    if "\\" in path:
        raise WriterContractError(f"{where} must use POSIX separators")
    if path.startswith("/") or path.startswith("//") or re.match(r"^[A-Za-z]:", path):
        raise WriterContractError(f"{where} must be repository-relative")
    if path.endswith("/"):
        raise WriterContractError(f"{where} must name a file")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WriterContractError(f"{where} contains an unsafe path segment")
    if any(part.casefold() == ".git" for part in parts):
        raise WriterContractError(f"{where} cannot enter .git")
    for part in parts:
        if part.endswith((" ", ".")):
            raise WriterContractError(
                f"{where} has a Windows-ambiguous path segment: {part!r}"
            )
        stem = part.split(".", 1)[0].casefold()
        if stem in WINDOWS_RESERVED:
            raise WriterContractError(
                f"{where} uses a Windows reserved device name: {part!r}"
            )
    normalized = PurePosixPath(*parts).as_posix()
    if normalized != path:
        raise WriterContractError(f"{where} is not canonical POSIX form")
    return normalized


def _validate_validation_argv(argv: Any, *, where: str) -> list[str]:
    if not isinstance(argv, list) or not 1 <= len(argv) <= MAX_ARGV_ITEMS:
        raise WriterContractError(f"{where} must contain 1..{MAX_ARGV_ITEMS} tokens")
    normalized: list[str] = []
    for index, raw in enumerate(argv):
        token = _text(raw, where=f"{where}[{index}]", maximum=1_024, strip=False)
        if token != token.strip() or "\n" in token or "\r" in token:
            raise WriterContractError(f"{where}[{index}] is not a canonical token")
        normalized.append(token)
    if sum(len(token) for token in normalized) > MAX_ARGV_CHARS:
        raise WriterContractError(f"{where} exceeds {MAX_ARGV_CHARS} characters")

    executable = normalized[0]
    if (
        "/" in executable
        or "\\" in executable
        or executable.casefold() not in SAFE_VALIDATION_EXECUTABLES
    ):
        raise WriterContractError(
            f"{where}[0] must be one of {sorted(SAFE_VALIDATION_EXECUTABLES)}"
        )
    lowered = [token.casefold() for token in normalized]
    if "-c" in lowered or "--command" in lowered or "-" in normalized[1:]:
        raise WriterContractError(f"{where} cannot execute inline or stdin code")
    if "-m" in lowered:
        module_index = lowered.index("-m") + 1
        if module_index >= len(lowered):
            raise WriterContractError(f"{where} has -m without a module")
        if lowered[module_index] in FORBIDDEN_PYTHON_MODULES:
            raise WriterContractError(
                f"{where} cannot execute module {normalized[module_index]!r}"
            )
    for token in normalized[1:]:
        if token.startswith(("http://", "https://")):
            raise WriterContractError(f"{where} cannot contain a network URL")
        if token.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", token):
            raise WriterContractError(f"{where} cannot contain an absolute path token")
        if token in {"..", "."} or token.startswith("../") or "/../" in token:
            raise WriterContractError(f"{where} cannot traverse outside the worktree")
    return normalized


def validate_package(raw: Any) -> WriterPackage:
    top = _closed_object(raw, where="package", keys=TOP_KEYS)
    if isinstance(top["version"], bool) or top["version"] != PACKAGE_VERSION:
        raise WriterContractError(f"package.version must be integer {PACKAGE_VERSION}")
    name = _text(top["name"], where="package.name", maximum=MAX_NAME_CHARS)
    if NAME_RE.fullmatch(name) is None:
        raise WriterContractError("package.name must be a lowercase identifier")
    objective = _text(
        top["objective"], where="package.objective", maximum=MAX_OBJECTIVE_CHARS
    )

    base = _closed_object(top["base"], where="package.base", keys=BASE_KEYS)
    repository = _text(
        base["repository_full_name"],
        where="package.base.repository_full_name",
        maximum=201,
    )
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise WriterContractError(
            "package.base.repository_full_name must be owner/repository"
        )
    for key in ("expected_head_sha", "expected_tree_sha"):
        value = base[key]
        if not isinstance(value, str) or HEX40_RE.fullmatch(value) is None:
            raise WriterContractError(f"package.base.{key} must be 40 lowercase hex")

    authority = _closed_object(
        top["authority"], where="package.authority", keys=AUTHORITY_KEYS
    )
    targets_raw = authority["owned_targets"]
    if (
        not isinstance(targets_raw, list)
        or not 1 <= len(targets_raw) <= MAX_OWNED_TARGETS
    ):
        raise WriterContractError(
            f"package.authority.owned_targets must contain 1..{MAX_OWNED_TARGETS} paths"
        )
    targets = [
        normalize_repo_path(
            value, where=f"package.authority.owned_targets[{index}]"
        )
        for index, value in enumerate(targets_raw)
    ]
    folded = [target.casefold() for target in targets]
    if len(folded) != len(set(folded)):
        raise WriterContractError(
            "package.authority.owned_targets must be case-insensitively unique"
        )
    actions_raw = authority["allowed_actions"]
    if not isinstance(actions_raw, list) or not actions_raw:
        raise WriterContractError("package.authority.allowed_actions must be non-empty")
    if any(not isinstance(item, str) for item in actions_raw):
        raise WriterContractError("package.authority.allowed_actions must be strings")
    actions = sorted(set(actions_raw))
    if len(actions) != len(actions_raw) or not set(actions) <= GRANTABLE_ACTIONS:
        raise WriterContractError(
            "package.authority.allowed_actions may contain create/modify once each"
        )

    limits_raw = _closed_object(
        top["limits"], where="package.limits", keys=LIMIT_KEYS
    )
    limits = {
        key: _integer(
            limits_raw[key],
            where=f"package.limits.{key}",
            minimum=minimum,
            maximum=maximum,
        )
        for key, (minimum, maximum) in LIMIT_RANGES.items()
    }
    if limits["max_changed_files"] > len(targets):
        raise WriterContractError(
            "package.limits.max_changed_files cannot exceed owned target count"
        )
    if limits["max_created_file_bytes"] > limits["max_total_candidate_bytes"]:
        raise WriterContractError(
            "package.limits.max_created_file_bytes cannot exceed max_total_candidate_bytes"
        )

    verification = _closed_object(
        top["verification"], where="package.verification", keys=VERIFICATION_KEYS
    )
    required_raw = verification["required_verification_ids"]
    if not isinstance(required_raw, list) or not required_raw:
        raise WriterContractError(
            "package.verification.required_verification_ids must be non-empty"
        )
    required: list[str] = []
    for index, value in enumerate(required_raw):
        identifier = _text(
            value,
            where=f"package.verification.required_verification_ids[{index}]",
            maximum=80,
        )
        if IDENTIFIER_RE.fullmatch(identifier) is None:
            raise WriterContractError(f"invalid verification identifier: {identifier!r}")
        required.append(identifier)
    if len(required) != len(set(required)):
        raise WriterContractError("required verification identifiers must be unique")

    commands_raw = verification["commands"]
    if (
        not isinstance(commands_raw, list)
        or not 1 <= len(commands_raw) <= MAX_VERIFICATION_COMMANDS
    ):
        raise WriterContractError(
            f"package.verification.commands must contain 1..{MAX_VERIFICATION_COMMANDS} commands"
        )
    commands: list[dict[str, Any]] = []
    command_ids: list[str] = []
    for index, raw_command in enumerate(commands_raw):
        command = _closed_object(
            raw_command,
            where=f"package.verification.commands[{index}]",
            keys=COMMAND_KEYS,
        )
        identifier = _text(
            command["id"],
            where=f"package.verification.commands[{index}].id",
            maximum=80,
        )
        if IDENTIFIER_RE.fullmatch(identifier) is None:
            raise WriterContractError(f"invalid command identifier: {identifier!r}")
        command_ids.append(identifier)
        commands.append(
            {
                "id": identifier,
                "argv": _validate_validation_argv(
                    command["argv"],
                    where=f"package.verification.commands[{index}].argv",
                ),
                "timeout_seconds": _integer(
                    command["timeout_seconds"],
                    where=(
                        f"package.verification.commands[{index}].timeout_seconds"
                    ),
                    minimum=1,
                    maximum=3_600,
                ),
            }
        )
    if len(command_ids) != len(set(command_ids)):
        raise WriterContractError("verification command identifiers must be unique")
    if not set(required) <= set(command_ids):
        raise WriterContractError(
            "required verification identifiers must reference declared commands"
        )

    normalized = {
        "version": PACKAGE_VERSION,
        "name": name,
        "objective": objective,
        "base": {
            "repository_full_name": repository,
            "expected_head_sha": base["expected_head_sha"],
            "expected_tree_sha": base["expected_tree_sha"],
        },
        "authority": {
            "owned_targets": targets,
            "allowed_actions": actions,
        },
        "limits": limits,
        "verification": {
            "required_verification_ids": required,
            "commands": commands,
        },
    }
    return WriterPackage(normalized, canonical_digest(normalized))


def load_package(path: str | Path) -> WriterPackage:
    return validate_package(load_json_strict(path))


def package_contract() -> dict[str, Any]:
    """Return deterministic zero-model package boundary metadata."""

    return {
        "contract_version": PACKAGE_VERSION,
        "grantable_actions": sorted(GRANTABLE_ACTIONS),
        "forbidden_effects": [
            "delete",
            "rename",
            "mode_change",
            "symlink",
            "reparse",
            "submodule",
            "git_metadata",
            "external_write",
            "credentialed_action",
        ],
        "hard_limits": {
            key: {"minimum": minimum, "maximum": maximum}
            for key, (minimum, maximum) in LIMIT_RANGES.items()
        },
        "validation_executables": sorted(SAFE_VALIDATION_EXECUTABLES),
        "model_generated_authority": False,
        "automatic_apply": False,
        "automatic_git_write": False,
        "automatic_retry": False,
    }
