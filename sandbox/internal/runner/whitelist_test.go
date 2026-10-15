package runner

import "testing"

func TestValidateCommandChecksEveryExplicitCommand(t *testing.T) {
	allowed := []string{"echo", "cat"}
	tests := []struct {
		name    string
		command string
		wantErr bool
	}{
		{name: "single allowed command", command: "echo hello"},
		{name: "allowed pipeline", command: `echo "a; b" | cat`},
		{name: "quoted separator is an argument", command: `echo "safe; forbidden"`},
		{name: "forbidden command after separator", command: "echo safe; forbidden", wantErr: true},
		{name: "forbidden command in pipeline", command: "echo safe | forbidden", wantErr: true},
		{name: "forbidden command substitution", command: "echo $(forbidden)", wantErr: true},
		{name: "dynamic command name", command: "$TOOL safe", wantErr: true},
		{name: "PATH override before command", command: "PATH=/tmp cat /etc/passwd", wantErr: true},
		{name: "persistent PATH override", command: "PATH=/tmp; cat /etc/passwd", wantErr: true},
		{name: "absolute command path", command: "/tmp/echo safe", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateCommand(tt.command, allowed)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ValidateCommand(%q) error = %v, wantErr %v", tt.command, err, tt.wantErr)
			}
		})
	}
}

func TestDefaultAllowlistRejectsCommandDispatchers(t *testing.T) {
	for _, command := range []string{"ash", "bash", "sh", "env", "find", "sudo", "xargs"} {
		if err := ValidateCommand(command+" echo", DefaultAllowedBinaries); err == nil {
			t.Errorf("ValidateCommand(%q) unexpectedly allowed a command dispatcher", command)
		}
	}
}
