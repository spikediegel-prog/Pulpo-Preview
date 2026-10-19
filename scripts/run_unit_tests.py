"""Run unit tests and fail on otherwise ignored finalizer exceptions."""
from __future__ import annotations

import argparse
import gc
from pathlib import Path
import sys
import unittest
import warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--start-directory", default="tests")
    parser.add_argument("-p", "--pattern", default="test*.py")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    unraisable_types: list[str] = []
    previous_hook = sys.unraisablehook

    def record_unraisable(error) -> None:
        # Keep only the type name, never the resource/exception/traceback: those
        # references could themselves prevent cleanup or retain sensitive data.
        unraisable_types.append(error.exc_type.__name__)
        previous_hook(error)

    try:
        sys.unraisablehook = record_unraisable
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            suite = unittest.defaultTestLoader.discover(
                args.start_directory, pattern=args.pattern)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            gc.collect()
        if unraisable_types:
            print(f"FAILED cleanup: {len(unraisable_types)} unraisable exception(s)",
                  file=sys.stderr)
        return int(not result.wasSuccessful() or bool(unraisable_types))
    finally:
        sys.unraisablehook = previous_hook


if __name__ == "__main__":
    raise SystemExit(main())
