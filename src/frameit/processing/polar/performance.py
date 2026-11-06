# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

"""Optional graph/memory observations that never compute lazy physical fields."""

from __future__ import annotations

import sys


def dask_graph_tasks(datasets):
    keys = set()
    for dataset in datasets:
        for value in dataset.variables.values():
            if hasattr(value.data, "__dask_graph__"):
                keys.update(value.data.__dask_graph__().keys())
    return len(keys)


def process_peak_rss_bytes():
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)
