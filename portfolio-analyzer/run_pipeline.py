#!/usr/bin/env python3
"""
Run the full portfolio analyzer pipeline (Phase 0→6 + comprehensive report).
Usage from repo root:  python portfolio-analyzer/run_pipeline.py
Usage from portfolio-analyzer:  python run_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure portfolio-analyzer is on path when run from repo root
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from pipeline_tools import run_full_pipeline

if __name__ == "__main__":
    result = run_full_pipeline(comprehensive_sentiment=True)
    print(result)
