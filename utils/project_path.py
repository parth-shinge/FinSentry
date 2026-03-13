"""
FinSentry - Project Path Configuration
============================================

Ensures the project root directory is on ``sys.path`` so that all
internal package imports (``ingestion``, ``fraud_detection``,
``graph_engine``, ``case_builder``, ``utils``) resolve correctly
regardless of the working directory.

Usage — add this to the top of any script that is run directly::

    from utils.project_path import PROJECT_ROOT
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Absolute path to the FinSentry project root directory.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
