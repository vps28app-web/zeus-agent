package runner

import (
	"context"
	"os"
	"strings"
	"testing"
)

func TestRunRejectsUnprivilegedExecution(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root execution is covered by the privileged integration environment")
	}

	result := Run(context.Background(), Request{Command: "echo should-not-run"})
	if !strings.Contains(strings.ToLower(result.Error), "requires root") {
		t.Fatalf("Run error = %q, want a clear root requirement", result.Error)
	}
}

func TestSandboxExecutionIsIsolated(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("requires root, cgroup v2 and Linux namespaces; CI runs this test with sudo")
	}
	result := Run(context.Background(), Request{
		Command:    `printf '%s\n' "$(id -u)"; test ! -e /etc/passwd && echo isolated`,
		TimeoutSec: 10,
		MemoryMB:   128,
		CpuPct:     50,
		MaxPids:    64,
	})
	if result.Error != "" {
		t.Fatalf("sandbox execution error = %q", result.Error)
	}
	if got, want := result.Stdout, "65534\nisolated\n"; got != want {
		t.Fatalf("sandbox stdout = %q, want %q", got, want)
	}
	if result.Truncated {
		t.Fatal("small integration output was unexpectedly truncated")
	}
}
