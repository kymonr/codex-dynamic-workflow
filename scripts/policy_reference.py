"""Compatibility import for the shared authoritative policy implementation.

The Runtime and original v2 policy tests use the same decisions. Importing these
functions does not grant permissions; the Runtime adds transactional accounting.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skill/codex-dynamic-workflow/scripts'))
from cwf_runtime.policy import (Decision, natural, budget_admission, economy_eligible,
                                permission, windows_owned_path, overlapping,
                                acceptance, stop_optional, logical_overlap)

__all__ = ['Decision', 'natural', 'budget_admission', 'economy_eligible', 'permission',
           'windows_owned_path', 'overlapping', 'acceptance', 'stop_optional', 'logical_overlap']
