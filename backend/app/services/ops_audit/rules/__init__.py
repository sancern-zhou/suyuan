"""Operations work order audit rules.

This package contains all deterministic rules for operations work order audits.
Rules are organized by category and can be imported individually or via the registry.
"""

from __future__ import annotations

from app.services.ops_audit.rules.attachment_rules import (
    attachment_review_candidate_rule_ids,
    build_attachment_inventory,
    check_attachment_requirements,
)
from app.services.ops_audit.rules.attachment_ocr_rules import check_attachment_ocr_quality
from app.services.ops_audit.rules.device_consistency_rules import (
    check_device_identity_consistency,
    merge_device_history,
)
from app.services.ops_audit.rules.lifecycle_rules import check_lifecycle_closure
from app.services.ops_audit.rules.o3_transfer_quality_rules import check_o3_transfer_quality_values
from app.services.ops_audit.rules.rf_abnormal_remark_rules import check_rf_abnormal_remarks
from app.services.ops_audit.rules.rf_calibration_date_rules import check_rf_calibration_dates
from app.services.ops_audit.rules.rf_enum_rules import check_rf_enum_values
from app.services.ops_audit.rules.rf_formula_rules import check_rf_formula_values
from app.services.ops_audit.rules.rf_humidity_rules import check_rf_environment_humidity_values
from app.services.ops_audit.rules.rf_multipoint_rules import check_rf_multipoint_values
from app.services.ops_audit.rules.rf_pm_pressure_rules import check_rf_pm_pressure_values
from app.services.ops_audit.rules.rf_position_rules import check_rf_field_positions
from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values
from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields
from app.services.ops_audit.rules.rf_time_rules import check_rf_time_ranges
from app.services.ops_audit.rules.rf_unit_rules import check_rf_unit_values
from app.services.ops_audit.rules.rf_visibility_rules import check_rf_visibility_values
from app.services.ops_audit.rules.workflow_rules import check_workflow_completeness

__all__ = [
    # Workflow rules
    "check_workflow_completeness",
    # RF form rules
    "check_rf_required_fields",
    "check_rf_time_ranges",
    "check_rf_unit_values",
    "check_rf_range_values",
    "check_rf_formula_values",
    "check_rf_environment_humidity_values",
    "check_rf_multipoint_values",
    "check_rf_pm_pressure_values",
    "check_rf_field_positions",
    "check_rf_abnormal_remarks",
    "check_rf_calibration_dates",
    "check_rf_enum_values",
    "check_rf_visibility_values",
    "check_o3_transfer_quality_values",
    # Lifecycle rules
    "check_lifecycle_closure",
    # Device consistency rules
    "check_device_identity_consistency",
    "merge_device_history",
    # Attachment rules
    "check_attachment_requirements",
    "check_attachment_ocr_quality",
    "build_attachment_inventory",
    "attachment_review_candidate_rule_ids",
]


def get_all_rule_checkers() -> dict[str, callable]:
    """Return a registry of all rule checker functions.

    The registry maps rule group names to their checker functions,
    making it easy to enable/disable rule groups during audit runs.
    """
    return {
        "workflow": check_workflow_completeness,
        "rf_required": check_rf_required_fields,
        "rf_time": check_rf_time_ranges,
        "rf_unit": check_rf_unit_values,
        "rf_range": check_rf_range_values,
        "rf_formula": check_rf_formula_values,
        "rf_environment_humidity": check_rf_environment_humidity_values,
        "rf_multipoint": check_rf_multipoint_values,
        "rf_pm_pressure": check_rf_pm_pressure_values,
        "rf_position": check_rf_field_positions,
        "rf_abnormal_remark": check_rf_abnormal_remarks,
        "rf_calibration_date": check_rf_calibration_dates,
        "rf_enum": check_rf_enum_values,
        "rf_visibility": check_rf_visibility_values,
        "o3_transfer_quality": check_o3_transfer_quality_values,
        "lifecycle": check_lifecycle_closure,
        "device_consistency": check_device_identity_consistency,
        "attachment": check_attachment_requirements,
        "attachment_ocr": check_attachment_ocr_quality,
    }
