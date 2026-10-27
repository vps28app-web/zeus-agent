package runner

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
)

// Result holds the output of a sandboxed command execution.
type Result struct {
	ExitCode  int    `json:"exit_code"`
	Stdout    string `json:"stdout"`
	Stderr    string `json:"stderr"`
	Error     string `json:"error,omitempty"`
	Truncated bool   `json:"truncated,omitempty"`
}

const maxOutputBytesPerStream = 512 * 1024

type boundedBuffer struct {
	bytes.Buffer
	limit     int
	truncated bool
}

func (b *boundedBuffer) Write(value []byte) (int, error) {
	remaining := b.limit - b.Len()
	if remaining <= 0 {
		if len(value) > 0 {
			b.truncated = true
		}
		return len(value), nil
	}
	if len(value) > remaining {
		_, _ = b.Buffer.Write(value[:remaining])
		b.truncated = true
		return len(value), nil
	}
	return b.Buffer.Write(value)
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

const MaxTimeoutSec = 300

// ValidateRequest rejects execution requests that exceed the sandbox's hard
// resource ceilings. Zero values select the documented defaults.
func ValidateRequest(req Request) error {
	if strings.TrimSpace(req.Command) == "" {
		return fmt.Errorf("command must not be empty")
	}
	if req.TimeoutSec < 0 || req.TimeoutSec > MaxTimeoutSec {
		return fmt.Errorf("timeout_sec must be between 0 and %d", MaxTimeoutSec)
	}
	if req.MemoryMB < 0 || req.MemoryMB > maxSandboxMemoryMB {
		return fmt.Errorf("memory_mb must be between 0 and %d", maxSandboxMemoryMB)
	}
	if req.CpuPct < 0 || req.CpuPct > 100 {
		return fmt.Errorf("cpu_pct must be between 0 and 100")
	}
	if req.MaxPids < 0 || req.MaxPids > maxSandboxPids {
		return fmt.Errorf("max_pids must be between 0 and %d", maxSandboxPids)
	}
	if req.WorkDir != "" {
		return fmt.Errorf("work_dir is not supported; sandbox workspaces are always created in a private temporary directory")
	}
	if _, err := encodePayloadEnv(req.Env); err != nil {
		return fmt.Errorf("invalid env: %w", err)
	}
	return nil
}

const (
	payloadEnvJSONKey      = "ZEUS_PAYLOAD_ENV_JSON"
	maxPayloadEnvJSONBytes = 64 * 1024
)

func encodePayloadEnv(extra map[string]string) (string, error) {
	for key, value := range extra {
		if key == "" || strings.ContainsAny(key, "=\x00") {
			return "", fmt.Errorf("invalid environment variable name %q", key)
		}
		if strings.ContainsRune(value, '\x00') {
			return "", fmt.Errorf("environment variable %q contains a NUL byte", key)
		}
	}
	encoded, err := json.Marshal(extra)
	if err != nil {
		return "", fmt.Errorf("encode payload environment: %w", err)
	}
	if len(encoded) > maxPayloadEnvJSONBytes {
		return "", fmt.Errorf("payload environment exceeds %d bytes", maxPayloadEnvJSONBytes)
	}
	return string(encoded), nil
}

// buildSandboxHelperEnv contains no request-controlled environment keys. The
// request environment is transported as JSON under a neutral variable name so
// dynamic loaders cannot interpret values such as LD_PRELOAD before isolation.
func buildSandboxHelperEnv(payloadEnv map[string]string) ([]string, error) {
	encoded, err := encodePayloadEnv(payloadEnv)
	if err != nil {
		return nil, err
	}
	return []string{
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"HOME=/tmp",
		"USER=nobody",
		"TMPDIR=/tmp",
		payloadEnvJSONKey + "=" + encoded,
	}, nil
}

// buildPayloadEnv is called only after the sandbox child has dropped privileges.
func buildPayloadEnv(encoded string) ([]string, error) {
	var extra map[string]string
	if encoded != "" {
		if err := json.Unmarshal([]byte(encoded), &extra); err != nil {
			return nil, fmt.Errorf("decode payload environment: %w", err)
		}
	}
	if _, err := encodePayloadEnv(extra); err != nil {
		return nil, err
	}

	env := map[string]string{
		"PATH":   "/usr/bin:/bin",
		"HOME":   "/tmp",
		"TMPDIR": "/tmp",
	}
	for key, value := range extra {
		env[key] = value
	}
	keys := make([]string, 0, len(env))
	for key := range env {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make([]string, 0, len(keys))
	for _, key := range keys {
		result = append(result, key+"="+env[key])
	}
	return result, nil
}

// Run executes a command in a restricted child process using Linux namespaces.
func Run(ctx context.Context, req Request) Result {
	return runWithExecutable(ctx, req, "")
}

// runWithExecutable allows integration tests to start the real sandbox binary;
// production callers leave executable empty and use this process's executable.
func runWithExecutable(ctx context.Context, req Request, selfPath string) Result {
	if err := ValidateRequest(req); err != nil {
		return Result{ExitCode: 1, Error: err.Error()}
	}
	if os.Geteuid() != 0 {
		return Result{
			ExitCode: 1,
			Error:    "sandbox execution requires root privileges; start the sandbox server with sudo",
		}
	}

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

	workDir, err := os.MkdirTemp("", "zeus-sandbox-*")
	if err != nil {
		return Result{Error: fmt.Sprintf("failed to create work dir: %v", err)}
	}
	defer os.RemoveAll(workDir)

	if selfPath == "" {
		selfPath, err = os.Executable()
		if err != nil {
			return Result{Error: fmt.Sprintf("failed to find executable: %v", err)}
		}
	}

	helperEnv, err := buildSandboxHelperEnv(req.Env)
	if err != nil {
		return Result{ExitCode: 1, Error: err.Error()}
	}
	cmd := exec.CommandContext(execCtx, selfPath, "--sandbox-child", req.Command)
	cmd.Dir = workDir
	cmd.Env = helperEnv
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

	stdout, stderr := boundedBuffer{limit: maxOutputBytesPerStream}, boundedBuffer{limit: maxOutputBytesPerStream}
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// Create a dedicated cgroup and attach the child atomically at process
	// creation. Never move the long-lived sandbox server into the workload group.
	cgroup, err := applyCgroups(req.MemoryMB, req.CpuPct, req.MaxPids)
	if err != nil {
		return Result{Error: fmt.Sprintf("failed to apply required cgroup limits: %v", err)}
	}
	cmd.SysProcAttr.UseCgroupFD = true
	cmd.SysProcAttr.CgroupFD = int(cgroup.dir.Fd())

	err = cmd.Run()
	cleanupErr := cgroup.cleanup()
	if cleanupErr != nil {
		return Result{Error: fmt.Sprintf("sandbox cgroup cleanup failed: %v", cleanupErr)}
	}
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return Result{Error: err.Error()}
		}
	}

	return Result{
		ExitCode:  exitCode,
		Stdout:    stdout.String(),
		Stderr:    stderr.String(),
		Truncated: stdout.truncated || stderr.truncated,
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
