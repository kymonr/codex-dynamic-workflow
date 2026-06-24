# Runner Risk Recheck - 2026-06-23

Scope: recheck the historical findings captured in `docs/evidence/smoke-summary.json` against the current `src/runner.py`. This is evidence for Team Router follow-up planning; no runner behavior was changed in this pass.

## Findings

1. `--allowed-root` remains optional for read mode.
   - Evidence: `_main_read()` still defines `--allowed-root` with `default=None`, then passes it to `validate_spec(raw, allowed_roots=args.allowed_root)`.
   - Current status: still applicable as a read-mode boundary risk. The README recommends passing `--allowed-root <项目根>` for the `cli-runner` read-mode entry, but the code path still allows omission.

2. Local `output_schema` validation remains intentionally minimal.
   - Evidence: `_check_schema_minimal()` still checks only top-level `type == "object"` and required top-level keys.
   - Current status: still applicable. This protects against missing required top-level fields, but it is not a full JSON Schema validator for property types, arrays, enums, or `additionalProperties`.

3. `_harden_schema()` is improved for nested `properties` and `items`, but remains incomplete for some JSON Schema locations.
   - Evidence: `_harden_schema()` recurses through `properties`, `items`, `anyOf`, `allOf`, and `oneOf`; it does not recurse through `$defs`, `definitions`, or schema-valued `additionalProperties`.
   - Current status: partially mitigated, still applicable for schemas that use those unsupported locations.

## Recommendation

Keep these as runner backlog items, separate from Team Router:

- Require or strongly default `--allowed-root` when a parent workflow knows the user-scoped project root.
- Either document `_check_schema_minimal()` as a shallow check everywhere, or add a real JSON Schema validator dependency through an explicit dependency decision.
- Extend `_harden_schema()` recursion to `$defs`, `definitions`, tuple `items`, and schema-valued `additionalProperties`, then add focused unit tests.
