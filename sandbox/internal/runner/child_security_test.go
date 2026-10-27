package runner

import (
	"errors"
	"syscall"
	"testing"
)

func TestMakeMountsPrivateReturnsFailure(t *testing.T) {
	called := false
	err := makeMountsPrivate(func(string, string, string, uintptr, string) error {
		called = true
		return errors.New("mount propagation denied")
	})
	if !called {
		t.Fatal("mount operation was not attempted")
	}
	if err == nil {
		t.Fatal("makeMountsPrivate() ignored a failed private-mount operation")
	}
}

func TestBindMountReadOnlyRemountsBindMountWithSecurityFlags(t *testing.T) {
	var flags []uintptr
	err := bindMountReadOnly(func(source, target, filesystem string, mountFlags uintptr, data string) error {
		if source != "/usr" || target != "/sandbox/usr" || filesystem != "" || data != "" {
			t.Fatalf("mount args = (%q, %q, %q, %q), want source/target bind mount", source, target, filesystem, data)
		}
		flags = append(flags, mountFlags)
		return nil
	}, "/usr", "/sandbox/usr")
	if err != nil {
		t.Fatalf("bindMountReadOnly() error = %v", err)
	}
	want := []uintptr{
		syscall.MS_BIND,
		syscall.MS_BIND | syscall.MS_REMOUNT | syscall.MS_RDONLY | syscall.MS_NOSUID | syscall.MS_NODEV,
	}
	if len(flags) != len(want) {
		t.Fatalf("mount called %d times, want %d", len(flags), len(want))
	}
	for i := range want {
		if flags[i] != want[i] {
			t.Errorf("mount call %d flags = %#x, want %#x", i+1, flags[i], want[i])
		}
	}
}

func TestBindMountReadOnlyStopsWhenBindMountFails(t *testing.T) {
	calls := 0
	err := bindMountReadOnly(func(string, string, string, uintptr, string) error {
		calls++
		return errors.New("bind failed")
	}, "/usr", "/sandbox/usr")
	if err == nil || calls != 1 {
		t.Fatalf("bindMountReadOnly() = (%v, %d calls), want bind error after one call", err, calls)
	}
}

func TestBindMountReadOnlyReturnsRemountFailure(t *testing.T) {
	wantErr := errors.New("read-only remount denied")
	calls := 0
	err := bindMountReadOnly(func(string, string, string, uintptr, string) error {
		calls++
		if calls == 2 {
			return wantErr
		}
		return nil
	}, "/usr", "/sandbox/usr")
	if !errors.Is(err, wantErr) || calls != 2 {
		t.Fatalf("bindMountReadOnly() = (%v, %d calls), want remount error after two calls", err, calls)
	}
}

func TestRootfsPathRejectsMissingWorkingDirectory(t *testing.T) {
	if _, err := rootfsPathForCwd(""); err == nil {
		t.Fatal("rootfsPathForCwd() accepted an empty cwd")
	}
}
