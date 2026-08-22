"""Additional unit tests for zeus/mcp/server.py."""

import json
from unittest.mock import patch

from zeus.mcp.server import MCPServer


def test_run_stdio_reads_and_responds():
    server = MCPServer()

    requests = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    ]

    written = []

    with patch("sys.stdin", iter(requests)):
        with patch("sys.stdout.write", written.append):
            with patch("sys.stdout.flush"):
                server.run_stdio()

    assert len(written) == 1
    resp = json.loads(written[0])
    assert resp["id"] == 1


def test_run_stdio_handles_parse_error():
    server = MCPServer()
    written = []

    with patch("sys.stdin", iter(["not json"])):
        with patch("sys.stdout.write", written.append):
            with patch("sys.stdout.flush"):
                server.run_stdio()

    assert len(written) == 1
    resp = json.loads(written[0])
    assert "error" in resp
