package runner

import "testing"

func TestValidateRequestRejectsUnsafeLimits(t *testing.T) {
	cases := []Request{
		{Command: "echo ok", TimeoutSec: -1},
		{Command: "echo ok", TimeoutSec: 301},
		{Command: "echo ok", MemoryMB: 4097},
		{Command: "echo ok", CpuPct: 101},
		{Command: "echo ok", MaxPids: 257},
		{Command: "echo ok", WorkDir: "/etc"},
		{Command: "  "},
	}
	for _, request := range cases {
		if err := ValidateRequest(request); err == nil {
			t.Errorf("ValidateRequest(%+v) succeeded; want rejection", request)
		}
	}
}

func TestValidateRequestAllowsDefaults(t *testing.T) {
	if err := ValidateRequest(Request{Command: "echo ok"}); err != nil {
		t.Fatalf("ValidateRequest() error = %v", err)
	}
}
