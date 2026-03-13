"""
FinSentry AI - SAR Generator Package
=======================================

Generates Suspicious Activity Reports from investigation cases with
graph-derived context and regulatory-compliant templates.

Modules:
    models     -- SARReport Pydantic model.
    templates  -- SAR section rendering functions.
    generator  -- SARGenerator (orchestrates the full pipeline).
"""

from sar_generator.models import SARReport
from sar_generator.generator import SARGenerator

__all__ = ["SARReport", "SARGenerator"]
