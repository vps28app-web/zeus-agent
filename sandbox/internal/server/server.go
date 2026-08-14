package server

import (
	"encoding/json"
	"log"
	"net/http"

	"zeus/sandbox/internal/runner"
)

// Server exposes the sandbox runner over HTTP.
type Server struct {
	addr string
}

// New creates a new sandbox HTTP server.
func New(addr string) *Server {
	return &Server{addr: addr}
}

// Run starts the HTTP server and blocks until it exits.
func (s *Server) Run() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/run", runHandler)
	log.Printf("Zeus sandbox server listening on %s", s.addr)
	return http.ListenAndServe(s.addr, mux)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func runHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req runner.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
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
