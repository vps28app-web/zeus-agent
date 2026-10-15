package runner

import (
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strconv"
	"syscall"
)

// mountProcReadonly mounts /proc with restrictive flags to reduce kernel attack surface.
func mountProcReadonly(root string) error {
	procDir := filepath.Join(root, "proc")
	if err := syscall.Mount("proc", procDir, "proc", syscall.MS_NOSUID|syscall.MS_NODEV|syscall.MS_NOEXEC|syscall.MS_RDONLY, ""); err != nil {
		return fmt.Errorf("mount proc readonly: %w", err)
	}
	// Hide sensitive proc entries inside the chroot.
	for _, entry := range []string{"kcore", "kallsyms", "sched_debug", "sysrq-trigger", "sys"} {
		target := filepath.Join(procDir, entry)
		_ = os.RemoveAll(target)
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

// RunChild is invoked by the sandbox binary itself when started with
// --sandbox-child. It sets up the isolated filesystem and runs the command.
// Root is mandatory: running the payload on the host without a chroot is unsafe.
func RunChild(command string) error {
	if os.Geteuid() != 0 {
		return fmt.Errorf("sandbox execution requires root privileges")
	}

	// Make / private recursively so mounts don't leak outside the namespace.
	if err := syscall.Mount("none", "/", "", syscall.MS_REC|syscall.MS_PRIVATE, ""); err != nil {
		fmt.Fprintf(os.Stderr, "warning: mount private failed: %v\n", err)
	}

	root := "/"
	cwd, err := os.Getwd()
	if err == nil {
		root = filepath.Join(cwd, "rootfs")
	}

	// If we are root, create a chroot-like tmpfs root.
	if os.Geteuid() == 0 {
		if err := os.MkdirAll(root, 0755); err != nil {
			return fmt.Errorf("mkdir rootfs: %w", err)
		}
		if err := syscall.Mount("tmpfs", root, "tmpfs", 0, "size=50M,mode=755"); err != nil {
			return fmt.Errorf("mount tmpfs: %w", err)
		}
		for _, d := range []string{"bin", "lib", "lib64", "usr", "dev", "proc", "etc"} {
			_ = os.MkdirAll(filepath.Join(root, d), 0755)
		}
		_ = os.MkdirAll(filepath.Join(root, "tmp"), 0777)
		_ = os.Chmod(filepath.Join(root, "tmp"), 0777)
		for _, src := range []string{"/bin", "/usr", "/lib", "/lib64", "/etc"} {
			if _, err := os.Stat(src); os.IsNotExist(err) {
				continue
			}
			dst := filepath.Join(root, src)
			_ = os.MkdirAll(dst, 0755)
			if err := syscall.Mount(src, dst, "", syscall.MS_BIND|syscall.MS_RDONLY, ""); err != nil {
				fmt.Fprintf(os.Stderr, "warning: bind mount %s failed: %v\n", src, err)
			}
		}
		for _, dev := range []string{"/dev/null", "/dev/zero", "/dev/random", "/dev/urandom"} {
			_ = os.MkdirAll(filepath.Join(root, filepath.Dir(dev)), 0755)
			_ = exec.Command("cp", "-a", dev, filepath.Join(root, dev)).Run()
		}
		if err := mountProcReadonly(root); err != nil {
			fmt.Fprintf(os.Stderr, "warning: proc mount failed: %v\n", err)
		}

		// Copy sandbox binary into chroot so it can re-exec itself.
		selfPath, err := os.Executable()
		if err != nil {
			return fmt.Errorf("cannot find own executable: %w", err)
		}
		chrootSelf := filepath.Join(root, "/sandbox")
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
		_ = os.Chdir("/")
	}

	cmd := exec.Command("/sandbox", "--sandbox-child-internal", command)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = []string{
		"PATH=/usr/bin:/bin",
		"HOME=/tmp",
		"TMPDIR=/tmp",
	}

	return cmd.Run()
}

// IsInternalChildMode returns true when running inside the chroot.
func IsInternalChildMode() bool {
	return len(os.Args) >= 3 && os.Args[1] == "--sandbox-child-internal"
}

// ExecInternalChild runs the final command after chroot.
func ExecInternalChild() {
	command := os.Args[2]

	// Drop privileges to nobody if running as root.
	if os.Geteuid() == 0 {
		if err := dropPrivileges(); err != nil {
			fmt.Fprintf(os.Stderr, "drop privileges: %v\n", err)
			os.Exit(1)
		}
	}

	_ = disableCoreDumps()

	// Install seccomp-bpf filter. If it fails, log and continue with other isolations.
	if err := InstallSeccomp(); err != nil {
		fmt.Fprintf(os.Stderr, "seccomp: %v (continuing without seccomp)\n", err)
	}

	cmd := exec.Command("/bin/sh", "-c", command)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = []string{
		"PATH=/usr/bin:/bin",
		"HOME=/tmp",
		"TMPDIR=/tmp",
	}
	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		fmt.Fprintf(os.Stderr, "internal child error: %v\n", err)
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

	if err := syscall.Setgid(nobodyGID); err != nil {
		return fmt.Errorf("setgid: %w", err)
	}
	if err := syscall.Setuid(nobodyUID); err != nil {
		return fmt.Errorf("setuid: %w", err)
	}
	return nil
}
