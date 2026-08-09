import pytest
from pydantic import ValidationError

from app.api import EmployeeInput
from app.models import ParseStatus
from app.schemas import DocumentCreate


def test_document_create_applies_security_defaults():
    value = DocumentCreate(
        candidate_id="C001",
        tenant_id="acme",
        title="林晓岚简历",
        document_type="resume",
    )

    assert value.permission_scope == "hr_private"
    assert value.confidentiality_level == "internal"


def test_parse_status_uses_clear_terminal_states():
    assert ParseStatus.SUCCEEDED.value == "succeeded"
    assert ParseStatus.FAILED.value == "failed"
    assert "review_required" not in {item.value for item in ParseStatus}


def test_employee_job_level_uses_l_prefix():
    value = EmployeeInput(employee_no="C006", name="测试员工", job_level="L3")
    assert value.job_level == "L3"

    with pytest.raises(ValidationError):
        EmployeeInput(employee_no="C007", name="错误职级", job_level="T9")
