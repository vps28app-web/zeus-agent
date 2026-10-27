package runner

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
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
	binaryPath := filepath.Join(t.TempDir(), "zeus-sandbox")
	build := exec.Command("go", "build", "-o", binaryPath, "../../cmd/sandbox")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build sandbox integration binary: %v\n%s", err, output)
	}
	result := runWithExecutable(context.Background(), Request{
		Command:    `printf '%s\n' "$(id -u)"; test ! -e /etc/passwd && echo isolated`,
		TimeoutSec: 10,
		MemoryMB:   128,
		CpuPct:     50,
		MaxPids:    64,
	}, binaryPath)
	if result.Error != "" {
		t.Fatalf("sandbox execution error = %q", result.Error)
	}
	if got, want := result.Stdout, "65534\nisolated\n"; got != want || result.ExitCode != 0 {
		t.Fatalf("sandbox result mismatch: exit_code=%d stdout=%q stderr=%q; want exit_code=0 stdout=%q", result.ExitCode, result.Stdout, result.Stderr, want)
	}
	if result.Truncated {
		t.Fatal("small integration output was unexpectedly truncated")
	}
}
