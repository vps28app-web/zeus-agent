package runner

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildSandboxHelperEnvDoesNotExposeRequestKeys(t *testing.T) {
	helperEnv, err := buildSandboxHelperEnv(map[string]string{
		"LD_PRELOAD": "/tmp/payload.so",
		"SAFE_VALUE": "value",
	})
	if err != nil {
		t.Fatalf("buildSandboxHelperEnv() error = %v", err)
	}

	var encoded string
	for _, entry := range helperEnv {
		if strings.HasPrefix(entry, "LD_PRELOAD=") {
			t.Fatal("request-controlled LD_PRELOAD was passed directly to the privileged helper")
		}
		if strings.HasPrefix(entry, payloadEnvJSONKey+"=") {
			encoded = strings.TrimPrefix(entry, payloadEnvJSONKey+"=")
		}
	}
	if encoded == "" {
		t.Fatal("request environment was not passed through the neutral transport variable")
	}
	var decoded map[string]string
	if err := json.Unmarshal([]byte(encoded), &decoded); err != nil {
		t.Fatalf("payload environment transport is invalid JSON: %v", err)
	}
	if decoded["LD_PRELOAD"] != "/tmp/payload.so" || decoded["SAFE_VALUE"] != "value" {
		t.Fatalf("decoded payload environment = %#v", decoded)
	}
}

func TestBuildPayloadEnvAppliesRequestVariablesAfterPrivilegeDrop(t *testing.T) {
	payloadEnv, err := buildPayloadEnv(`{"LD_PRELOAD":"/tmp/payload.so","ZEUS_PROJECT_DIR":"/workspace"}`)
	if err != nil {
		t.Fatalf("buildPayloadEnv() error = %v", err)
	}
	got := make(map[string]string, len(payloadEnv))
	for _, entry := range payloadEnv {
		key, value, found := strings.Cut(entry, "=")
		if !found {
			t.Fatalf("environment entry %q has no value separator", entry)
		}
		got[key] = value
	}
	for key, want := range map[string]string{
		"PATH":             "/usr/bin:/bin",
		"HOME":             "/tmp",
		"TMPDIR":           "/tmp",
		"LD_PRELOAD":       "/tmp/payload.so",
		"ZEUS_PROJECT_DIR": "/workspace",
	} {
		if got[key] != want {
			t.Errorf("payload environment %s = %q, want %q", key, got[key], want)
		}
	}
}

func TestBuildSandboxHelperEnvRejectsInvalidVariables(t *testing.T) {
	for _, env := range []map[string]string{
		{"BAD=KEY": "value"},
		{"BAD\x00KEY": "value"},
		{"KEY": "bad\x00value"},
	} {
		if _, err := buildSandboxHelperEnv(env); err == nil {
			t.Errorf("buildSandboxHelperEnv(%q) succeeded; want validation error", env)
		}
	}
}
