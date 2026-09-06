"""Installed, self-contained Runtime entrypoint."""
from cwf_runtime.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
