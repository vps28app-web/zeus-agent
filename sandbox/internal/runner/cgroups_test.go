package runner

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCheckCgroupControllersRequiresAllLimitsEnabled(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "cgroup.controllers"), []byte("cpu memory pids"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "cgroup.subtree_control"), []byte("cpu memory"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := checkCgroupControllers(root); err == nil {
		t.Fatal("checkCgroupControllers() succeeded without the pids controller enabled")
	}
}

func TestCheckCgroupControllersAcceptsRequiredControllers(t *testing.T) {
	root := t.TempDir()
	for name, value := range map[string]string{
		"cgroup.controllers":     "cpu memory pids",
		"cgroup.subtree_control": "cpu memory pids",
	} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(value), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := checkCgroupControllers(root); err != nil {
		t.Fatalf("checkCgroupControllers() error = %v", err)
	}
}

func TestWriteCgroupLimitsWritesHardLimits(t *testing.T) {
	group := t.TempDir()
	for _, name := range []string{"memory.max", "cpu.max", "pids.max"} {
		if err := os.WriteFile(filepath.Join(group, name), nil, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := writeCgroupLimits(group, 128, 50, 64); err != nil {
		t.Fatalf("writeCgroupLimits() error = %v", err)
	}
	for name, want := range map[string]string{
		"memory.max": "134217728",
		"cpu.max":    "50000 100000",
		"pids.max":   "64",
	} {
		got, err := os.ReadFile(filepath.Join(group, name))
		if err != nil {
			t.Fatal(err)
		}
		if strings.TrimSpace(string(got)) != want {
			t.Errorf("%s = %q, want %q", name, strings.TrimSpace(string(got)), want)
		}
	}
}

func TestWriteCgroupLimitsRejectsUnsafeValues(t *testing.T) {
	if err := writeCgroupLimits(t.TempDir(), 128, 101, 64); err == nil {
		t.Fatal("writeCgroupLimits() accepted CPU above 100 percent")
	}
}
