package runner

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	defaultCgroupBase  = "/sys/fs/cgroup"
	maxSandboxMemoryMB = 4096
	maxSandboxPids     = 256
	cgroupCPUPeriodUS  = 100000
)

type sandboxCgroup struct {
	path string
	dir  *os.File
}

// checkCgroupControllers fails closed unless cgroup v2 exposes and has enabled
// every controller required to bound a sandboxed process.
func checkCgroupControllers(base string) error {
	available, err := os.ReadFile(filepath.Join(base, "cgroup.controllers"))
	if err != nil {
		return fmt.Errorf("read available cgroup controllers: %w", err)
	}
	enabled, err := os.ReadFile(filepath.Join(base, "cgroup.subtree_control"))
	if err != nil {
		return fmt.Errorf("read enabled cgroup controllers: %w", err)
	}
	availableSet := fieldsSet(string(available))
	enabledSet := fieldsSet(string(enabled))
	for _, name := range []string{"cpu", "memory", "pids"} {
		if _, ok := availableSet[name]; !ok {
			return fmt.Errorf("required cgroup v2 controller %q is unavailable", name)
		}
		if _, ok := enabledSet[name]; !ok {
			return fmt.Errorf("required cgroup v2 controller %q is not enabled for child groups", name)
		}
	}
	return nil
}

func fieldsSet(value string) map[string]struct{} {
	set := make(map[string]struct{})
	for _, field := range strings.Fields(value) {
		set[strings.TrimPrefix(field, "+")] = struct{}{}
	}
	return set
}

// writeCgroupLimits applies strict memory, CPU quota, and process-count caps.
func writeCgroupLimits(path string, memoryMB, cpuPct, maxPids int) error {
	if memoryMB < 1 || memoryMB > maxSandboxMemoryMB {
		return fmt.Errorf("memory limit must be between 1 and %d MiB", maxSandboxMemoryMB)
	}
	if cpuPct < 1 || cpuPct > 100 {
		return fmt.Errorf("CPU limit must be between 1 and 100 percent")
	}
	if maxPids < 1 || maxPids > maxSandboxPids {
		return fmt.Errorf("PID limit must be between 1 and %d", maxSandboxPids)
	}

	limits := map[string]string{
		"memory.max": fmt.Sprintf("%d", memoryMB*1024*1024),
		"cpu.max":    fmt.Sprintf("%d %d", cpuPct*1000, cgroupCPUPeriodUS),
		"pids.max":   fmt.Sprintf("%d", maxPids),
	}
	for name, value := range limits {
		if err := os.WriteFile(filepath.Join(path, name), []byte(value), 0644); err != nil {
			return fmt.Errorf("apply %s cgroup limit: %w", name, err)
		}
	}
	return nil
}

func createSandboxCgroup(base string, memoryMB, cpuPct, maxPids int) (*sandboxCgroup, error) {
	if err := checkCgroupControllers(base); err != nil {
		return nil, fmt.Errorf("sandbox resource isolation unavailable: %w", err)
	}
	path, err := os.MkdirTemp(base, "zeus-sandbox-")
	if err != nil {
		return nil, fmt.Errorf("create sandbox cgroup: %w", err)
	}
	cleanupPath := func() { _ = os.Remove(path) }
	if err := writeCgroupLimits(path, memoryMB, cpuPct, maxPids); err != nil {
		cleanupPath()
		return nil, err
	}
	for _, name := range []string{"cgroup.kill", "cgroup.events"} {
		if _, err := os.Stat(filepath.Join(path, name)); err != nil {
			cleanupPath()
			return nil, fmt.Errorf("required cgroup v2 file %s unavailable: %w", name, err)
		}
	}
	dir, err := os.Open(path)
	if err != nil {
		cleanupPath()
		return nil, fmt.Errorf("open sandbox cgroup: %w", err)
	}
	return &sandboxCgroup{path: path, dir: dir}, nil
}

func applyCgroups(memoryMB, cpuPct, maxPids int) (*sandboxCgroup, error) {
	return createSandboxCgroup(defaultCgroupBase, memoryMB, cpuPct, maxPids)
}

// cleanup kills any descendants left by the command before removing its cgroup.
func (cg *sandboxCgroup) cleanup() error {
	if cg == nil {
		return nil
	}
	if cg.dir != nil {
		if err := cg.dir.Close(); err != nil {
			return fmt.Errorf("close sandbox cgroup handle: %w", err)
		}
		cg.dir = nil
	}
	killPath := filepath.Join(cg.path, "cgroup.kill")
	if err := os.WriteFile(killPath, []byte("1"), 0200); err != nil {
		return fmt.Errorf("kill remaining sandbox processes: %w", err)
	}

	deadline := time.Now().Add(5 * time.Second)
	for {
		events, err := os.ReadFile(filepath.Join(cg.path, "cgroup.events"))
		if err != nil {
			return fmt.Errorf("read sandbox cgroup events: %w", err)
		}
		if strings.Contains(string(events), "populated 0") {
			break
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("sandbox processes remained after cgroup.kill")
		}
		time.Sleep(10 * time.Millisecond)
	}
	if err := os.Remove(cg.path); err != nil {
		return fmt.Errorf("remove sandbox cgroup: %w", err)
	}
	return nil
}
