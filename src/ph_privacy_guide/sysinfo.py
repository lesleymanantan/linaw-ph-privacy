"""Small measurement helpers."""
from __future__ import annotations

import resource
import sys


def peak_rss_bytes() -> int:
    """Peak resident memory of this process. macOS reports bytes, Linux reports kilobytes."""
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024
