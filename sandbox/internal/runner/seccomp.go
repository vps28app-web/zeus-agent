package runner

import (
	"fmt"
	"runtime"
	"unsafe"

	"golang.org/x/sys/unix"
)

// Seccomp action constants (not defined in older golang.org/x/sys versions).
const (
	seccompRetAllow      = 0x7fff0000
	seccompRetErrno      = 0x00050000
	seccompRetKill       = 0x00000000
	seccompSetModeFilter = 1
)

// dangerousSyscalls lists syscalls that should always be blocked in the sandbox.
var dangerousSyscalls = []int{
	unix.SYS_MOUNT,
	unix.SYS_UMOUNT2,
	unix.SYS_PIVOT_ROOT,
	unix.SYS_REBOOT,
	unix.SYS_SWAPON,
	unix.SYS_SWAPOFF,
	unix.SYS_OPEN_BY_HANDLE_AT,
	unix.SYS_PERF_EVENT_OPEN,
	unix.SYS_BPF,
	unix.SYS_PTRACE,
	unix.SYS_KEXEC_LOAD,
	unix.SYS_CREATE_MODULE,
	unix.SYS_INIT_MODULE,
	unix.SYS_DELETE_MODULE,
	unix.SYS_IOPL,
	unix.SYS_IOPERM,
	unix.SYS_PROCESS_VM_WRITEV,
	unix.SYS_PROCESS_VM_READV,
	unix.SYS_SYSLOG,
	unix.SYS_FANOTIFY_INIT,
	unix.SYS_NAME_TO_HANDLE_AT,
	unix.SYS_SETNS,
	unix.SYS_UNSHARE,
	unix.SYS_SOCKET,
	unix.SYS_SOCKETPAIR,
	unix.SYS_CONNECT,
	unix.SYS_ACCEPT,
	unix.SYS_ACCEPT4,
	unix.SYS_BIND,
	unix.SYS_LISTEN,
}

// allowedSyscalls lists syscalls that the sandboxed command is permitted to use.
var allowedSyscalls = []int{
	unix.SYS_READ,
	unix.SYS_WRITE,
	unix.SYS_OPEN,
	unix.SYS_OPENAT,
	unix.SYS_CLOSE,
	unix.SYS_FSTAT,
	unix.SYS_NEWFSTATAT,
	unix.SYS_LSEEK,
	unix.SYS_MMAP,
	unix.SYS_MPROTECT,
	unix.SYS_MUNMAP,
	unix.SYS_BRK,
	unix.SYS_RT_SIGACTION,
	unix.SYS_RT_SIGPROCMASK,
	unix.SYS_RT_SIGRETURN,
	unix.SYS_IOCTL,
	unix.SYS_PREAD64,
	unix.SYS_PWRITE64,
	unix.SYS_ACCESS,
	unix.SYS_PIPE,
	unix.SYS_PIPE2,
	unix.SYS_DUP,
	unix.SYS_DUP2,
	unix.SYS_DUP3,
	unix.SYS_EXECVE,
	unix.SYS_EXECVEAT,
	unix.SYS_FORK,
	unix.SYS_VFORK,
	unix.SYS_CLONE3,
	unix.SYS_GETPID,
	unix.SYS_GETPPID,
	unix.SYS_GETTID,
	unix.SYS_EXIT,
	unix.SYS_EXIT_GROUP,
	unix.SYS_CLONE,
	unix.SYS_WAIT4,
	unix.SYS_NANOSLEEP,
	unix.SYS_CLOCK_GETTIME,
	unix.SYS_ARCH_PRCTL,
	unix.SYS_SET_TID_ADDRESS,
	unix.SYS_SET_ROBUST_LIST,
	unix.SYS_PRLIMIT64,
	unix.SYS_GETRANDOM,
	unix.SYS_UNAME,
	unix.SYS_READLINK,
	unix.SYS_READLINKAT,
	unix.SYS_GETCWD,
	unix.SYS_CHDIR,
	unix.SYS_FCNTL,
	unix.SYS_FUTEX,
	unix.SYS_SCHED_GETAFFINITY,
	unix.SYS_SCHED_YIELD,
	unix.SYS_GETDENTS64,
	unix.SYS_STAT,
	unix.SYS_LSTAT,
	unix.SYS_UNLINK,
	unix.SYS_UNLINKAT,
	unix.SYS_RENAME,
	unix.SYS_RENAMEAT,
	unix.SYS_RENAMEAT2,
	unix.SYS_RMDIR,
	unix.SYS_GETUID,
	unix.SYS_GETEUID,
	unix.SYS_GETGID,
	unix.SYS_GETEGID,
	unix.SYS_GETRESUID,
	unix.SYS_GETRESGID,
	unix.SYS_SETUID,
	unix.SYS_SETGID,
	unix.SYS_SETRESUID,
	unix.SYS_SETRESGID,
	unix.SYS_PRCTL,
	unix.SYS_SECCOMP,
	unix.SYS_FACCESSAT,
	unix.SYS_FACCESSAT2,
	unix.SYS_GETRLIMIT,
	unix.SYS_SETRLIMIT,
	unix.SYS_UMASK,
	unix.SYS_CHMOD,
	unix.SYS_FCHMOD,
	unix.SYS_FCHMODAT,
	unix.SYS_MADVISE,
	unix.SYS_MINCORE,
	unix.SYS_ALARM,
	unix.SYS_SIGALTSTACK,
	unix.SYS_TGKILL,
	unix.SYS_KILL,
	unix.SYS_WAITID,
	unix.SYS_EPOLL_CREATE1,
	unix.SYS_EPOLL_CTL,
	unix.SYS_EPOLL_PWAIT,
	unix.SYS_EVENTFD2,
	unix.SYS_TIMERFD_CREATE,
	unix.SYS_TIMERFD_SETTIME,
	unix.SYS_TIMERFD_GETTIME,
	unix.SYS_INOTIFY_INIT1,
	unix.SYS_INOTIFY_ADD_WATCH,
	unix.SYS_INOTIFY_RM_WATCH,
	unix.SYS_GETSOCKNAME,
	unix.SYS_GETPEERNAME,
}

// bpfStmt returns a single BPF instruction.
func bpfStmt(code uint16, k uint32) unix.SockFilter {
	return unix.SockFilter{Code: code, K: k}
}

const (
	auditArchX8664        = 0xc000003e // AUDIT_ARCH_X86_64
	seccompRetKillProcess = 0x80000000
)

func auditArchFor(goarch string) (uint32, error) {
	if goarch != "amd64" {
		return 0, fmt.Errorf("seccomp sandbox supports Linux amd64 only (got %s)", goarch)
	}
	return auditArchX8664, nil
}

func buildSeccompFilterForArch(arch uint32) ([]unix.SockFilter, error) {
	if arch == 0 {
		return nil, fmt.Errorf("invalid seccomp audit architecture")
	}
	filter := make([]unix.SockFilter, 0, 4+2*(len(dangerousSyscalls)+len(allowedSyscalls)))

	// Load arch into accumulator; matching the compiled architecture skips the
	// next instruction, while any mismatch kills the process immediately.
	filter = append(filter, bpfStmt(unix.BPF_LD+unix.BPF_W+unix.BPF_ABS, 4))
	filter = append(filter, unix.SockFilter{Code: unix.BPF_JMP + unix.BPF_JEQ + unix.BPF_K, Jt: 1, Jf: 0, K: arch})
	filter = append(filter, bpfStmt(unix.BPF_RET+unix.BPF_K, uint32(seccompRetKillProcess)))

	// Load syscall number.
	filter = append(filter, bpfStmt(unix.BPF_LD+unix.BPF_W+unix.BPF_ABS, 0))

	// Deny dangerous syscalls.
	for _, nr := range dangerousSyscalls {
		filter = append(filter, unix.SockFilter{Code: unix.BPF_JMP + unix.BPF_JEQ + unix.BPF_K, Jt: 0, Jf: 1, K: uint32(nr)})
		filter = append(filter, bpfStmt(unix.BPF_RET+unix.BPF_K, uint32(seccompRetErrno|38)))
	}

	// Allow common syscalls.
	for _, nr := range allowedSyscalls {
		filter = append(filter, unix.SockFilter{Code: unix.BPF_JMP + unix.BPF_JEQ + unix.BPF_K, Jt: 0, Jf: 1, K: uint32(nr)})
		filter = append(filter, bpfStmt(unix.BPF_RET+unix.BPF_K, uint32(seccompRetAllow)))
	}

	// Default: deny with ENOSYS.
	filter = append(filter, bpfStmt(unix.BPF_RET+unix.BPF_K, uint32(seccompRetErrno|38)))
	return filter, nil
}

// InstallSeccomp installs a seccomp-bpf filter that denies dangerous syscalls
// and allows a restricted set of safe syscalls.
func InstallSeccomp() error {
	arch, err := auditArchFor(runtime.GOARCH)
	if err != nil {
		return err
	}
	filter, err := buildSeccompFilterForArch(arch)
	if err != nil {
		return err
	}

	prog := unix.SockFprog{
		Len:    uint16(len(filter)),
		Filter: (*unix.SockFilter)(unsafe.Pointer(&filter[0])),
	}

	if err := unix.Prctl(unix.PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0); err != nil {
		return fmt.Errorf("prctl(NO_NEW_PRIVS): %w", err)
	}

	_, _, errno := unix.Syscall(unix.SYS_SECCOMP, seccompSetModeFilter, 0, uintptr(unsafe.Pointer(&prog)))
	if errno != 0 {
		return fmt.Errorf("seccomp filter install failed: %w", errno)
	}
	return nil
}
