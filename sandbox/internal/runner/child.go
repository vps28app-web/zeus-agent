package runner

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strconv"
	"syscall"
)

// mountProcReadonly mounts a read-only procfs inside the PID namespace.
func mountProcReadonly(root string) error {
	procDir := filepath.Join(root, "proc")
	if err := syscall.Mount("proc", procDir, "proc", syscall.MS_NOSUID|syscall.MS_NODEV|syscall.MS_NOEXEC|syscall.MS_RDONLY, ""); err != nil {
		return fmt.Errorf("mount proc readonly: %w", err)
	}
	return nil
}

// disableCoreDumps disables core dumps for the current process.
func disableCoreDumps() error {
	if err := syscall.Setrlimit(syscall.RLIMIT_CORE, &syscall.Rlimit{Cur: 0, Max: 0}); err != nil {
		return fmt.Errorf("setrlimit RLIMIT_CORE: %w", err)
	}
	return nil
}

func bindMountReadOnly(mount func(string, string, string, uintptr, string) error, source, target string) error {
	if err := mount(source, target, "", syscall.MS_BIND, ""); err != nil {
		return fmt.Errorf("bind mount %s: %w", source, err)
	}
	flags := uintptr(syscall.MS_BIND | syscall.MS_REMOUNT | syscall.MS_RDONLY | syscall.MS_NOSUID | syscall.MS_NODEV)
	if err := mount(source, target, "", flags, ""); err != nil {
		return fmt.Errorf("remount %s read-only: %w", target, err)
	}
	return nil
}

func makeMountsPrivate(mount func(string, string, string, uintptr, string) error) error {
	if err := mount("none", "/", "", syscall.MS_REC|syscall.MS_PRIVATE, ""); err != nil {
		return fmt.Errorf("make sandbox mount namespace private: %w", err)
	}
	return nil
}

func rootfsPathForCwd(cwd string) (string, error) {
	if cwd == "" {
		return "", fmt.Errorf("sandbox working directory is unavailable")
	}
	return filepath.Join(cwd, "rootfs"), nil
}

// RunChild is invoked by the sandbox binary itself when started with
// --sandbox-child. It sets up the isolated filesystem and runs the command.
// Root is mandatory: running the payload on the host without a chroot is unsafe.
func RunChild(command string) error {
	if os.Geteuid() != 0 {
		return fmt.Errorf("sandbox execution requires root privileges")
	}

	// Mount propagation isolation is mandatory; never continue with mounts that
	// could propagate back to the host.
	if err := makeMountsPrivate(syscall.Mount); err != nil {
		return err
	}

	cwd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("get sandbox working directory: %w", err)
	}
	root, err := rootfsPathForCwd(cwd)
	if err != nil {
		return err
	}

	if err := os.MkdirAll(root, 0755); err != nil {
		return fmt.Errorf("mkdir rootfs: %w", err)
	}
	if err := syscall.Mount("tmpfs", root, "tmpfs", syscall.MS_NOSUID, "size=50M,mode=755"); err != nil {
		return fmt.Errorf("mount tmpfs: %w", err)
	}
	for _, d := range []string{"bin", "lib", "lib64", "usr", "dev", "proc", "etc", "tmp"} {
		if err := os.MkdirAll(filepath.Join(root, d), 0755); err != nil {
			return fmt.Errorf("create rootfs directory %s: %w", d, err)
		}
	}
	if err := os.Chmod(filepath.Join(root, "tmp"), 01777); err != nil {
		return fmt.Errorf("set sandbox tmp permissions: %w", err)
	}

	// Do not expose the host /etc (which may contain credentials or machine
	// configuration) inside the sandbox. System binaries and libraries are
	// read-only and cannot honor setuid bits.
	for _, src := range []string{"/bin", "/usr", "/lib", "/lib64"} {
		if _, err := os.Stat(src); os.IsNotExist(err) {
			continue
		}
		dst := filepath.Join(root, src)
		if err := os.MkdirAll(dst, 0755); err != nil {
			return fmt.Errorf("create mountpoint for %s: %w", src, err)
		}
		if err := bindMountReadOnly(syscall.Mount, src, dst); err != nil {
			return err
		}
	}
	for _, dev := range []string{"/dev/null", "/dev/zero", "/dev/random", "/dev/urandom"} {
		if err := exec.Command("cp", "-a", dev, filepath.Join(root, dev)).Run(); err != nil {
			return fmt.Errorf("copy device %s into sandbox: %w", dev, err)
		}
	}
	if err := mountProcReadonly(root); err != nil {
		return err
	}

	// Copy sandbox binary into chroot so it can re-exec itself.
	selfPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("cannot find own executable: %w", err)
	}
	chrootSelf := filepath.Join(root, "sandbox")
	data, err := os.ReadFile(selfPath)
	if err != nil {
		return fmt.Errorf("read sandbox executable: %w", err)
	}
	if err := os.WriteFile(chrootSelf, data, 0755); err != nil {
		return fmt.Errorf("copy sandbox into chroot: %w", err)
	}

	if err := syscall.Chroot(root); err != nil {
		return fmt.Errorf("chroot: %w", err)
	}
	if err := os.Chdir("/"); err != nil {
		return fmt.Errorf("change to sandbox root: %w", err)
	}

	cmd := exec.Command("/sandbox", "--sandbox-child-internal", command)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = []string{
		"PATH=/usr/bin:/bin",
		"HOME=/tmp",
		"TMPDIR=/tmp",
		payloadEnvJSONKey + "=" + os.Getenv(payloadEnvJSONKey),
	}

	return cmd.Run()
}

// IsInternalChildMode returns true when running inside the chroot.
func IsInternalChildMode() bool {
	return len(os.Args) >= 3 && os.Args[1] == "--sandbox-child-internal"
}

// runAfterSeccomp enforces that the payload is never invoked if the required
// syscall filter cannot be installed.
func runAfterSeccomp(installFilter, runPayload func() error) error {
	if err := installFilter(); err != nil {
		return fmt.Errorf("required seccomp filter unavailable: %w", err)
	}
	return runPayload()
}

// ExecInternalChild runs the final command after chroot. A missing seccomp
// filter is fatal: this process must not execute an unfiltered payload.
func ExecInternalChild() {
	command := os.Args[2]

	// Drop privileges to nobody if running as root.
	if os.Geteuid() == 0 {
		if err := dropPrivileges(); err != nil {
			fmt.Fprintf(os.Stderr, "drop privileges: %v\n", err)
			os.Exit(1)
		}
	}

	if err := disableCoreDumps(); err != nil {
		fmt.Fprintf(os.Stderr, "disable core dumps: %v\n", err)
		os.Exit(1)
	}

	payloadEnv, err := buildPayloadEnv(os.Getenv(payloadEnvJSONKey))
	if err != nil {
		fmt.Fprintf(os.Stderr, "sandbox payload environment: %v\n", err)
		os.Exit(1)
	}

	err = runAfterSeccomp(InstallSeccomp, func() error {
		cmd := exec.Command("/bin/sh", "-c", command)
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.Env = payloadEnv
		return cmd.Run()
	})
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			os.Exit(exitErr.ExitCode())
		}
		fmt.Fprintf(os.Stderr, "sandbox child error: %v\n", err)
		os.Exit(1)
	}
	os.Exit(0)
}

// dropPrivileges changes uid/gid to nobody if the user exists.
func dropPrivileges() error {
	nobodyUID := 65534
	nobodyGID := 65534

	// Try to look up nobody from /etc/passwd inside chroot.
	if u, err := user.Lookup("nobody"); err == nil {
		if uid, err := strconv.Atoi(u.Uid); err == nil {
			nobodyUID = uid
		}
		if gid, err := strconv.Atoi(u.Gid); err == nil {
			nobodyGID = gid
		}
	}

	if err := syscall.Setgroups([]int{}); err != nil {
		return fmt.Errorf("clear supplementary groups: %w", err)
	}
	if err := syscall.Setgid(nobodyGID); err != nil {
		return fmt.Errorf("setgid: %w", err)
	}
	if err := syscall.Setuid(nobodyUID); err != nil {
		return fmt.Errorf("setuid: %w", err)
	}
	return nil
}
