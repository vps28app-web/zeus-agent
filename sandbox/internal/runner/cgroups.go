package runner

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

// applyCgroups creates a temporary cgroup v2 subtree for the current process
// and returns a cleanup function. It limits memory and CPU weight.
func applyCgroups(memoryMB, cpuPct int) (func(), error) {
	cgroupBase := "/sys/fs/cgroup"
	if _, err := os.Stat(cgroupBase); os.IsNotExist(err) {
		return func() {}, nil // cgroups v2 not available
	}

	sliceName := fmt.Sprintf("zeus-sandbox-%d", os.Getpid())
	slicePath := filepath.Join(cgroupBase, sliceName)
	if err := os.MkdirAll(slicePath, 0755); err != nil {
		return func() {}, fmt.Errorf("failed to create cgroup slice: %w", err)
	}

	// Move current process into the slice so child processes inherit it.
	if err := os.WriteFile(filepath.Join(slicePath, "cgroup.procs"), []byte(strconv.Itoa(os.Getpid())), 0700); err != nil {
		os.Remove(slicePath)
		return func() {}, fmt.Errorf("failed to move process to cgroup: %w", err)
	}

	memoryMax := memoryMB * 1024 * 1024
	if err := os.WriteFile(filepath.Join(slicePath, "memory.max"), []byte(strconv.Itoa(memoryMax)), 0700); err != nil {
		// memory controller might not be available; ignore
	}

	// cpu.weight range is 1..10000. cpuPct is 1..100.
	weight := cpuPct * 100
	if weight > 10000 {
		weight = 10000
	}
	if weight < 1 {
		weight = 1
	}
	if err := os.WriteFile(filepath.Join(slicePath, "cpu.weight"), []byte(strconv.Itoa(weight)), 0700); err != nil {
		// cpu controller might not be available; ignore
	}

	cleanup := func() {
		_ = os.Remove(slicePath)
	}
	return cleanup, nil
}
