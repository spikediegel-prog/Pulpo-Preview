"""Fail closed when a dependency scan failed, was skipped, or was cancelled."""
import json
import os


def admitted(needs: dict) -> bool:
    required = {"python-dependencies", "container-dependencies"}
    return isinstance(needs, dict) and all(
        isinstance(needs.get(name), dict) and needs[name].get("result") == "success"
        for name in required
    )


if __name__ == "__main__":
    raise SystemExit(0 if admitted(json.loads(os.environ["DEPENDENCY_NEEDS_JSON"])) else 1)
