package runner

import (
	"fmt"
	"strings"

	"mvdan.cc/sh/v3/syntax"
)

// DefaultAllowedBinaries lists direct command names permitted inside the sandbox.
// Shell interpreters and command dispatchers are omitted because they can execute
// binaries that are not visible as direct commands in the parsed shell program.
var DefaultAllowedBinaries = []string{
	"apt",
	"apt-get",
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
	"dpkg",
	"du",
	"echo",
	"expr",
	"false",
	"git",
	"grep",
	"gunzip",
	"gzip",
	"head",
	"host",
	"id",
	"jq",
	"kill",
	"less",
	"ln",
	"ls",
	"mkdir",
	"more",
	"mv",
	"nc",
	"netcat",
	"node",
	"npm",
	"nslookup",
	"openssl",
	"perl",
	"pgrep",
	"ping",
	"pip",
	"pip3",
	"printf",
	"ps",
	"pwd",
	"python",
	"python3",
	"rm",
	"rmdir",
	"scp",
	"sed",
	"sleep",
	"snap",
	"sort",
	"ssh",
	"ssh-keygen",
	"ssh-keyscan",
	"systemctl",
	"tail",
	"tar",
	"tee",
	"telnet",
	"test",
	"touch",
	"tr",
	"traceroute",
	"true",
	"uname",
	"uniq",
	"unzip",
	"wc",
	"wget",
	"whoami",
	"xz",
	"zip",
}

// ValidateCommand parses the shell program and checks every explicit simple
// command against the allowlist. Dynamic command names and explicit executable
// paths are rejected. This is an additional filter, not a replacement for OS
// isolation: an allowed program may itself spawn other processes.
func ValidateCommand(command string, allowed []string) error {
	if len(allowed) == 0 {
		return nil
	}
	parsed, err := syntax.NewParser(syntax.Variant(syntax.LangPOSIX)).Parse(strings.NewReader(command), "")
	if err != nil {
		return fmt.Errorf("invalid shell syntax: %w", err)
	}
	if len(parsed.Stmts) == 0 {
		return fmt.Errorf("empty command")
	}
	allowedSet := make(map[string]struct{}, len(allowed))
	for _, allowedName := range allowed {
		allowedSet[allowedName] = struct{}{}
	}

	var validationErr error
	syntax.Walk(parsed, func(node syntax.Node) bool {
		if validationErr != nil {
			return false
		}
		if assignment, ok := node.(*syntax.Assign); ok && assignment.Name != nil && assignment.Name.Value == "PATH" {
			validationErr = fmt.Errorf("overriding PATH is not allowed")
			return false
		}
		call, ok := node.(*syntax.CallExpr)
		if !ok || len(call.Args) == 0 {
			return true
		}
		name, literal := literalWord(call.Args[0])
		if !literal {
			validationErr = fmt.Errorf("dynamic command names are not allowed")
			return false
		}
		if strings.Contains(name, "/") {
			validationErr = fmt.Errorf("explicit command paths are not allowed: %q", name)
			return false
		}
		if _, ok := allowedSet[name]; !ok {
			validationErr = fmt.Errorf("binary %q is not in the sandbox allowlist", name)
			return false
		}
		return true
	})
	return validationErr
}

func literalWord(word *syntax.Word) (string, bool) {
	var value strings.Builder
	for _, part := range word.Parts {
		literal, ok := literalWordPart(part)
		if !ok {
			return "", false
		}
		value.WriteString(literal)
	}
	return value.String(), value.Len() > 0
}

func literalWordPart(part syntax.WordPart) (string, bool) {
	switch part := part.(type) {
	case *syntax.Lit:
		return part.Value, true
	case *syntax.SglQuoted:
		return part.Value, true
	case *syntax.DblQuoted:
		var value strings.Builder
		for _, nested := range part.Parts {
			literal, ok := literalWordPart(nested)
			if !ok {
				return "", false
			}
			value.WriteString(literal)
		}
		return value.String(), true
	default:
		return "", false
	}
}
