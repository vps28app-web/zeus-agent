"""Tests for the security audit logger."""

from pathlib import Path

from zeus.security.audit import AuditLogger


def test_audit_logger_writes_jsonl(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    logger.log_execution(
        tool="run_terminal",
        command="echo hello",
        result={"exit_code": 0, "stdout": "hello", "stderr": ""},
    )
    files = list(tmp_path.glob("audit-*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "run_terminal" in content
    assert "echo hello" in content


def test_audit_logger_file_mutation(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    logger.log_file_mutation(action="write", path=Path("/tmp/x.txt"), allowed=True)
    files = list(tmp_path.glob("audit-*.jsonl"))
    content = files[0].read_text()
    assert "file:write" in content
    assert "/tmp/x.txt" in content
    assert '"allowed": true' in content
