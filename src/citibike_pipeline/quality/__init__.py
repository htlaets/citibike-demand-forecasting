"""Data-quality, quarantine and schema-management components."""

# Backward-compatible exports for the original in-memory source checks.
from .checks import QualityIssue, QualityReport, check_source

# Warehouse-level quality framework.
from .quarantine import quarantine_invalid_records
from .schema_drift import check_all_schemas, check_dataset_schema
from .warehouse import DQResult, run_quality_checks, summarize

__all__ = [
    "QualityIssue",
    "QualityReport",
    "check_source",
    "DQResult",
    "run_quality_checks",
    "summarize",
    "quarantine_invalid_records",
    "check_all_schemas",
    "check_dataset_schema",
]
