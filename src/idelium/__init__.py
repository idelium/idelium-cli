"""Public package metadata for Idelium CLI."""

from typing import List, Optional

from idelium._internal.main import IDELIUM_VERSION


__version__ = IDELIUM_VERSION


def main(args: Optional[List[str]] = None) -> int:
    """Run the Idelium CLI entry point and return its process exit code."""
    from idelium._internal.main import main as _main

    return _main(args)
