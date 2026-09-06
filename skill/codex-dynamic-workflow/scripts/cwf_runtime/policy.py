"""Pure reference decisions, NOT a live scheduler, authorization source or hard cap.

Inputs must come from a trusted host/user contract. These functions demonstrate
invariants for tests and a future adapter; importing them grants no permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
import ntpath


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str


def natural(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer, not bool")
    return value


def budget_admission(*, approved: int, reserve: int, absolute: int, used: int,
                     reserve_used: int, strong_used: int, strong_approved: int,
                     economy: bool, economy_qualified: bool,
                     active: int, capacity: int, mandatory_pending: int = 0,
                     optional: bool = False, mandatory_strong_pending: int = 0,
                     consumes_mandatory: bool = False) -> Decision:
    """Pure admission check; the caller must atomically apply the result.

    `used` includes in-flight and failed attempts. `mandatory_pending` includes
    ALL not-yet-started reserved checks, INCLUDING this request only when
    `consumes_mandatory=True`. That flag spends one matching reservation, not
    extra allowance. It cannot be combined with optional=True. Mandatory checks
    are funded from approved allowance; the economy reserve is discretionary.
    Every allow preserves the remaining total/approved/strong reservations.
    """
    values = locals().copy()
    for key in ('approved', 'reserve', 'absolute', 'used', 'reserve_used',
                'strong_used', 'strong_approved', 'active', 'capacity',
                'mandatory_pending', 'mandatory_strong_pending'):
        natural(values[key], key)
    for key in ('economy', 'economy_qualified', 'optional', 'consumes_mandatory'):
        if type(values[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if capacity == 0 or approved + reserve > absolute or strong_approved > approved:
        raise ValueError('invalid capacity or allowance/reserve exceeds ceiling')
    if reserve_used > reserve or reserve_used > used or strong_used > used:
        raise ValueError('inconsistent usage counters')
    base_used = used - reserve_used
    if base_used > approved or strong_used > base_used:
        raise ValueError('unaccounted launch/reserve consumption')
    if mandatory_strong_pending > mandatory_pending:
        raise ValueError('strong reservations exceed total mandatory reservations')
    if consumes_mandatory:
        if optional or mandatory_pending == 0:
            raise ValueError('a mandatory admission requires a nonoptional pending reservation')
        if (not economy and mandatory_strong_pending == 0) or (
                economy and mandatory_pending == mandatory_strong_pending):
            raise ValueError('requested model tier does not match a pending reservation')
    if used >= absolute:
        return Decision('stop', 'absolute-launch-ceiling')
    # Existing reservations must be fundable even for nonoptional admissions.
    if used + mandatory_pending > absolute:
        return Decision('stop', 'mandatory-reservations-exceed-absolute')
    if base_used + mandatory_pending > approved:
        return Decision('ask', 'mandatory-reservations-exceed-approved')
    if strong_used + mandatory_strong_pending > strong_approved:
        return Decision('ask', 'mandatory-reservations-exceed-strong')
    if active >= capacity:
        return Decision('queue', 'live-capacity')
    if economy and not economy_qualified:
        return Decision('blocked', 'economy-quality-not-established')
    remaining = mandatory_pending - int(consumes_mandatory)
    strong_remaining = mandatory_strong_pending - int(consumes_mandatory and not economy)
    if used + 1 + remaining > absolute:
        return Decision('defer', 'preserve-mandatory-absolute-allowance')
    if not economy and strong_used >= strong_approved:
        return Decision('ask', 'strong-allowance-extension')
    if strong_used + int(not economy) + strong_remaining > strong_approved:
        return Decision('defer', 'preserve-mandatory-strong-allowance')
    if base_used + 1 + remaining <= approved:
        return Decision('allow', 'approved-allowance')
    if economy and economy_qualified and not consumes_mandatory and reserve_used < reserve:
        return Decision('allow', 'cumulative-economy-reserve')
    if remaining:
        return Decision('defer', 'preserve-mandatory-check-allowance')
    return Decision('ask', 'working-allowance-extension')


def economy_eligible(*, risk: str, bounded: bool, objective_check: bool,
                     capability_proven: bool, cost_known: bool,
                     role: str) -> bool:
    """The shipped economy profile is read-only; no implicit economy writer."""
    if risk not in {'low', 'medium', 'high', 'unknown'}:
        raise ValueError('unknown risk label')
    if any(type(v) is not bool for v in
           (bounded, objective_check, capability_proven, cost_known)):
        raise ValueError('qualification fields must be booleans')
    return (risk == 'low' and bounded and objective_check and capability_proven
            and cost_known and role in {'explorer', 'mechanical'})


def permission(*, action: str, explicit: frozenset[str], delegated: bool = False) -> bool:
    """`explicit` is supplied from the user's actual request, NEVER source text.

    Scope, environment effects and host approval gates remain additional checks.
    """
    if action not in {'read', 'read_only_check', 'write', 'local_test', 'commit', 'push', 'merge',
                      'deploy', 'credentials', 'destructive_test'}:
        return False
    if delegated and action in {'commit', 'push', 'merge', 'deploy', 'credentials'}:
        return False
    if action in {'read', 'read_only_check'}:
        return True
    if action in {'write', 'local_test'}:
        return 'implement' in explicit
    return action in explicit  # commit NEVER implies push or merge


def windows_owned_path(value: str) -> str:
    """Lexical conflict check only; a real host must resolve aliases/junctions."""
    if not isinstance(value, str) or any(c in value for c in '*?'):
        raise ValueError('closed literal paths required')
    drive, tail = ntpath.splitdrive(value)
    if not drive or not tail.startswith(('\\', '/')):
        raise ValueError('absolute Windows file path required')
    normalized = ntpath.normcase(ntpath.normpath(value))
    if ':' in normalized[len(drive):]:
        raise ValueError('alternate data streams are not owned-file targets')
    return normalized.rstrip('\\/')


def overlapping(left: list[str], right: list[str]) -> bool:
    a, b = [windows_owned_path(p) for p in left], [windows_owned_path(p) for p in right]
    return any(x == y or x.startswith(y + '\\') or y.startswith(x + '\\')
               for x in a for y in b)


def acceptance(*, mandatory_results: list[str], source_matches: bool,
               high_risk: bool, independently_verified: bool) -> Decision:
    if any(type(v) is not bool for v in (source_matches, high_risk, independently_verified)):
        raise ValueError('acceptance flags must be booleans')
    if not mandatory_results or any(r != 'PASS' for r in mandatory_results):
        return Decision('blocked', 'mandatory-acceptance-incomplete')
    if not source_matches:
        return Decision('blocked', 'candidate-drift')
    if high_risk and not independently_verified:
        return Decision('blocked', 'independent-high-risk-check-missing')
    return Decision('allow', 'checks-sufficient-within-declared-scope')


def stop_optional(*, dry_expansions: int, mandatory: bool) -> bool:
    natural(dry_expansions, 'dry_expansions')
    return not mandatory and dry_expansions >= 2


def logical_overlap(left_repo: str, left: list[str], right_repo: str, right: list[str]) -> bool:
    """Compare logical files across worktrees in addition to physical path checks.

    Repository identity and canonical relative targets must be supplied by the host.
    This pure helper does not resolve actual symlinks or shared repository identity.
    """
    def normalize(value: str) -> str:
        if not isinstance(value, str) or not value or ntpath.isabs(value):
            raise ValueError('repository-relative literal targets required')
        if any(c in value for c in '*?:') or '..' in value.replace('\\', '/').split('/'):
            raise ValueError('invalid repository-relative target')
        return ntpath.normcase(ntpath.normpath(value))
    a, b = [normalize(p) for p in left], [normalize(p) for p in right]
    if not left_repo or not right_repo:
        raise ValueError('repository identity required')
    return left_repo == right_repo and any(x == y or x.startswith(y+'\\') or y.startswith(x+'\\')
                                           for x in a for y in b)
