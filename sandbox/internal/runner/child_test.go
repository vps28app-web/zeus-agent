package runner

import (
	"errors"
	"strings"
	"testing"
)

func TestRunAfterSeccompDoesNotRunPayloadWhenInstallFails(t *testing.T) {
	payloadRan := false
	err := runAfterSeccomp(
		func() error { return errors.New("filter unavailable") },
		func() error {
			payloadRan = true
			return nil
		},
	)
	if err == nil || !strings.Contains(err.Error(), "seccomp") {
		t.Fatalf("runAfterSeccomp() error = %v, want seccomp failure", err)
	}
	if payloadRan {
		t.Fatal("payload ran even though the mandatory seccomp filter failed")
	}
}

func TestRunAfterSeccompRunsPayloadAfterSuccessfulInstall(t *testing.T) {
	payloadRan := false
	err := runAfterSeccomp(
		func() error { return nil },
		func() error {
			payloadRan = true
			return nil
		},
	)
	if err != nil {
		t.Fatalf("runAfterSeccomp() error = %v", err)
	}
	if !payloadRan {
		t.Fatal("payload did not run after seccomp installation succeeded")
	}
}
