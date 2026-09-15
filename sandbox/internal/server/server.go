package server

import (
	"encoding/json"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"zeus/sandbox/internal/runner"
)

// Server exposes the sandbox runner over HTTP.
type Server struct {
	addr      string
	authToken string
	mu        sync.Mutex
	rateMap   map[string][]time.Time
}

// New creates a new sandbox HTTP server.
func New(addr string) *Server {
	return &Server{
		addr:      addr,
		authToken: os.Getenv("ZEUS_SANDBOX_AUTH_TOKEN"),
		rateMap:   make(map[string][]time.Time),
	}
}

// Run starts the HTTP server and blocks until it exits.
func (s *Server) Run() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/run", s.runHandler)
	log.Printf("Zeus sandbox server listening on %s", s.addr)
	return http.ListenAndServe(s.addr, mux)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

const (
	maxRequestsPerMinute = 60
	maxBodyBytes         = 64 * 1024
)

func (s *Server) runHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Optional bearer-token authentication.
	if s.authToken != "" {
		auth := r.Header.Get("Authorization")
		const prefix = "Bearer "
		if !strings.HasPrefix(auth, prefix) || auth[len(prefix):] != s.authToken {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(runner.Result{Error: "unauthorized", ExitCode: 1})
			return
		}
	}

	// Rate limit per client IP.
	clientIP, _, _ := net.SplitHostPort(r.RemoteAddr)
	if clientIP == "" {
		clientIP = r.RemoteAddr
	}
	if !s.allowRequest(clientIP) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		json.NewEncoder(w).Encode(runner.Result{Error: "rate limit exceeded", ExitCode: 1})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	var req runner.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(runner.Result{Error: err.Error(), ExitCode: 1})
		return
	}

	// Optional binary whitelist. Empty allowlist disables the check.
	allowed := runner.DefaultAllowedBinaries
	if len(allowed) > 0 {
		if err := runner.ValidateCommand(req.Command, allowed); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(runner.Result{Error: err.Error(), ExitCode: 1})
			return
		}
	}

	result := runner.Run(r.Context(), req)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(result)
}

func (s *Server) allowRequest(clientIP string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	windowStart := now.Add(-time.Minute)
	requests := s.rateMap[clientIP]
	var valid []time.Time
	for _, t := range requests {
		if t.After(windowStart) {
			valid = append(valid, t)
		}
	}
	if len(valid) >= maxRequestsPerMinute {
		s.rateMap[clientIP] = valid
		return false
	}
	s.rateMap[clientIP] = append(valid, now)
	return true
}
