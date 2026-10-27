package server

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateLoopbackAddress(t *testing.T) {
	for _, addr := range []string{"127.0.0.1:9876", "[::1]:9876"} {
		if err := validateLoopbackAddress(addr); err != nil {
			t.Errorf("validateLoopbackAddress(%q) error = %v", addr, err)
		}
	}
	for _, addr := range []string{"0.0.0.0:9876", ":9876", "192.168.1.10:9876", "sandbox.example:9876"} {
		if err := validateLoopbackAddress(addr); err == nil {
			t.Errorf("validateLoopbackAddress(%q) succeeded; non-loopback binds must be rejected", addr)
		}
	}
}

func TestRunRequiresConfiguredBearerTokenBeforeListening(t *testing.T) {
	srv := New("127.0.0.1:0")
	srv.authToken = ""
	if err := srv.Run(); err == nil || !strings.Contains(err.Error(), "ZEUS_SANDBOX_AUTH_TOKEN") {
		t.Fatalf("Run() error = %v, want missing-auth-token error", err)
	}
}

func TestRunHandlerRejectsMissingAuthConfiguration(t *testing.T) {
	srv := New("127.0.0.1:9876")
	srv.authToken = ""
	request := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(`{"command":"echo hi"}`))
	response := httptest.NewRecorder()
	srv.runHandler(response, request)
	if response.Code != http.StatusServiceUnavailable || !strings.Contains(response.Body.String(), "authentication token") {
		t.Fatalf("status = %d body=%s, want missing-auth-token service error", response.Code, response.Body.String())
	}
}

func TestRunHandlerRequiresConfiguredBearerToken(t *testing.T) {
	srv := New("127.0.0.1:9876")
	srv.authToken = "test-secret"
	request := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(`{"command":"echo hi"}`))
	response := httptest.NewRecorder()
	srv.runHandler(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestRunHandlerRejectsInvalidResourceLimits(t *testing.T) {
	srv := New("127.0.0.1:9876")
	srv.authToken = "test-secret"
	request := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(`{"command":"echo hi","memory_mb":4097}`))
	request.Header.Set("Authorization", "Bearer test-secret")
	response := httptest.NewRecorder()
	srv.runHandler(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body=%s", response.Code, http.StatusBadRequest, response.Body.String())
	}
}
