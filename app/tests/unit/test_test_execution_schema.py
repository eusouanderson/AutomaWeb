from datetime import datetime

from app.schemas.test_execution import TestExecutionRequest, TestExecutionResult


def test_test_execution_request_defaults() -> None:
    req = TestExecutionRequest(project_id=1)
    assert req.project_id == 1
    assert req.test_ids is None


def test_test_execution_result_schema() -> None:
    now = datetime.utcnow()
    result = TestExecutionResult(
        id=1,
        project_id=1,
        total_tests=10,
        passed=8,
        failed=2,
        skipped=0,
        log_file="/tmp/log.html",
        report_file="/tmp/report.html",
        output_file="/tmp/output.xml",
        status="completed",
        created_at=now,
        completed_at=now,
    )
    assert result.total_tests == 10
    assert result.status == "completed"
