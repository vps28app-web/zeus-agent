package runner

import (
	"testing"

	"golang.org/x/sys/unix"
)

func TestAuditArchForSupportsAMD64(t *testing.T) {
	arch, err := auditArchFor("amd64")
	if err != nil {
		t.Fatalf("auditArchFor(amd64) error = %v", err)
	}
	if arch != auditArchX8664 {
		t.Fatalf("auditArchFor(amd64) = %#x, want %#x", arch, auditArchX8664)
	}
}

func TestAuditArchForRejectsUnsupportedArchitecture(t *testing.T) {
	if _, err := auditArchFor("arm64"); err == nil {
		t.Fatal("auditArchFor(arm64) succeeded; unsupported architectures must fail closed")
	}
}

func TestSeccompFilterKillsOnArchitectureMismatch(t *testing.T) {
	filter, err := buildSeccompFilterForArch(auditArchX8664)
	if err != nil {
		t.Fatalf("buildSeccompFilterForArch() error = %v", err)
	}
	if len(filter) < 3 {
		t.Fatalf("filter has %d instructions, want at least 3", len(filter))
	}
	if filter[1].Jt != 1 || filter[1].Jf != 0 {
		t.Fatalf("architecture branch = jt:%d jf:%d, want matching arch to skip mismatch action", filter[1].Jt, filter[1].Jf)
	}
	if filter[2].K != uint32(seccompRetKillProcess) {
		t.Fatalf("mismatched architecture action = %#x, want kill-process %#x", filter[2].K, uint32(seccompRetKillProcess))
	}
}

func TestSeccompAllowsUIDInspectionSyscall(t *testing.T) {
	for _, syscallNumber := range allowedSyscalls {
		if syscallNumber == unix.SYS_GETUID {
			return
		}
	}
	t.Fatal("seccomp filter must allow getuid so sandboxed tools can report their unprivileged identity")
}
