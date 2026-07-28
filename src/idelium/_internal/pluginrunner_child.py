"""Child process entrypoint for approved Idelium CLI plugins."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from idelium._internal.commons.resultenum import Result


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    plugin_path = Path(request["pluginPath"])
    spec = importlib.util.spec_from_file_location("idelium_approved_plugin", plugin_path)
    if spec is None or spec.loader is None:
        print("Plugin module could not be loaded.", file=sys.stderr)
        return 2

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entrypoint = getattr(module, request["entrypoint"])
    result = entrypoint(None, request.get("jsonConfig", {}), request.get("params"))

    if isinstance(result, Result):
        value = result.name
    elif result == 0:
        value = "OK"
    elif result == 1:
        value = "KO"
    elif result == 2:
        value = "NA"
    else:
        print("Plugin returned an unsupported result value.", file=sys.stderr)
        return 3

    print(json.dumps({"result": value}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
