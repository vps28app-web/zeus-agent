package runner

import (
	"fmt"
	"os/exec"
	"strings"
)

// DefaultAllowedBinaries lists binaries that may be invoked inside the sandbox.
// Commands are parsed as shell words; only the first word (the binary) is checked.
var DefaultAllowedBinaries = []string{
	"ash",
	"bash",
	"bc",
	"cat",
	"chmod",
	"cp",
	"curl",
	"cut",
	"date",
	"dd",
	"df",
	"diff",
	"dirname",
	"du",
	"echo",
	"env",
	"expr",
	"false",
	"find",
	"grep",
	"gunzip",
	"gzip",
	"head",
	"id",
	"jq",
	"kill",
	"less",
	"ln",
	"ls",
	"mkdir",
	"more",
	"mv",
	"node",
	"npm",
	"openssl",
	"perl",
	"pip",
	"pip3",
	"printf",
	"ps",
	"pwd",
	"python",
	"python3",
	"rm",
	"rmdir",
	"sed",
	"sh",
	"sleep",
	"sort",
	"tail",
	"tar",
	"tee",
	"test",
	"touch",
	"tr",
	"true",
	"uname",
	"uniq",
	"unzip",
	"wc",
	"wget",
	"whoami",
	"xargs",
	"xz",
	"zip",
}

// ValidateCommand checks whether the first binary in a shell command is allowed.
// The caller is responsible for sanitizing the command string; this function only
// enforces the binary allowlist because legitimate Zeus commands use shell pipes
// and substitutions (e.g. `echo ... | base64 -d | bash`).
func ValidateCommand(command string, allowed []string) error {
	if len(allowed) == 0 {
		return nil
	}
	fields := strings.Fields(command)
	if len(fields) == 0 {
		return fmt.Errorf("empty command")
	}
	name := fields[0]
	// Strip any leading path; only base names are allowed.
	if idx := strings.LastIndex(name, "/"); idx >= 0 {
		name = name[idx+1:]
	}
	for _, allowedName := range allowed {
		if name == allowedName {
			return nil
		}
	}
	return fmt.Errorf("binary %q is not in the sandbox allowlist", name)
}

// parseCommandWords parses a shell command into words without invoking a shell.
// It uses /bin/sh -n to validate syntax and falls back to simple field splitting.
func parseCommandWords(command string) ([]string, error) {
	if _, err := exec.Command("/bin/sh", "-n", "-c", command).Output(); err != nil {
		return nil, fmt.Errorf("invalid shell syntax: %w", err)
	}
	return strings.Fields(command), nil
}
