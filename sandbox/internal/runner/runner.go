package runner

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
)

// Result holds the output of a sandboxed command execution.
type Result struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	Error    string `json:"error,omitempty"`
}

// Request configures a sandboxed execution.
type Request struct {
	Command    string            `json:"command"`
	TimeoutSec int               `json:"timeout_sec"`
	Env        map[string]string `json:"env,omitempty"`
	WorkDir    string            `json:"work_dir,omitempty"`
	CpuPct     int               `json:"cpu_pct,omitempty"`
	MemoryMB   int               `json:"memory_mb,omitempty"`
	MaxPids    int               `json:"max_pids,omitempty"`
}

// Run executes a command in a restricted child process using Linux namespaces.
func Run(ctx context.Context, req Request) Result {
	if req.TimeoutSec <= 0 {
		req.TimeoutSec = 30
	}
	if req.CpuPct <= 0 {
		req.CpuPct = 50
	}
	if req.MemoryMB <= 0 {
		req.MemoryMB = 128
	}
	if req.MaxPids <= 0 {
		req.MaxPids = 64
	}

	execCtx, cancel := context.WithTimeout(ctx, time.Duration(req.TimeoutSec)*time.Second)
	defer cancel()

	workDir := req.WorkDir
	if workDir == "" {
		var err error
		workDir, err = os.MkdirTemp("", "zeus-sandbox-*")
		if err != nil {
			return Result{Error: fmt.Sprintf("failed to create work dir: %v", err)}
		}
		defer os.RemoveAll(workDir)
	}

	selfPath, err := os.Executable()
	if err != nil {
		return Result{Error: fmt.Sprintf("failed to find executable: %v", err)}
	}

	cmd := exec.CommandContext(execCtx, selfPath, "--sandbox-child", req.Command)
	cmd.Dir = workDir
	cmd.Env = buildEnv(req.Env)
	cmd.Stdin = nil

	cmd.SysProcAttr = &syscall.SysProcAttr{
		Cloneflags: syscall.CLONE_NEWNS |
			syscall.CLONE_NEWPID |
			syscall.CLONE_NEWNET |
			syscall.CLONE_NEWIPC |
			syscall.CLONE_NEWUTS,
		Unshareflags: syscall.CLONE_NEWNS,
		Setpgid:      true,
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// cgroup setup before start
	cgroupCleanup, err := applyCgroups(req.MemoryMB, req.CpuPct, req.MaxPids)

	if err != nil {
		return Result{Error: fmt.Sprintf("failed to apply cgroups: %v", err)}
	}
	defer cgroupCleanup()

	err = cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return Result{Error: err.Error()}
		}
	}

	return Result{
		ExitCode: exitCode,
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
	}
}

// IsChildMode returns true if the current process should run the sandbox child setup.
func IsChildMode() bool {
	if len(os.Args) < 3 {
		return false
	}
	return os.Args[1] == "--sandbox-child"
}

// ExecChild runs the child sandbox setup. It is called from main when IsChildMode is true.
func ExecChild() {
	command := os.Args[2]
	if err := RunChild(command); err != nil {
		fmt.Fprintf(os.Stderr, "sandbox child error: %v\n", err)
		os.Exit(1)
	}
	os.Exit(0)
}

func buildEnv(extra map[string]string) []string {
	base := []string{
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"HOME=/tmp",
		"USER=nobody",
		"TMPDIR=/tmp",
	}
	for k, v := range extra {
		base = append(base, fmt.Sprintf("%s=%s", k, v))
	}
	return base
}

// PrepareWorkDir creates a clean working directory for the sandbox.
func PrepareWorkDir(base string) (string, error) {
	if base == "" {
		base = os.TempDir()
	}
	return os.MkdirTemp(base, "zeus-sandbox-*")
}

// CopyFiles copies listed files into the working directory.
func CopyFiles(workDir string, files []string) error {
	for _, src := range files {
		data, err := os.ReadFile(src)
		if err != nil {
			return err
		}
		dest := filepath.Join(workDir, filepath.Base(src))
		if err := os.WriteFile(dest, data, 0644); err != nil {
			return err
		}
	}
	return nil
}
