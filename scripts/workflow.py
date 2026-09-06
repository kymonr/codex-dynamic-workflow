"""Project entrypoint for the same installed Runtime implementation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/codex-dynamic-workflow/scripts"))
from cwf_runtime.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
