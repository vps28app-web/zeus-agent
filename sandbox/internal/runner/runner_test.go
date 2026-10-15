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
