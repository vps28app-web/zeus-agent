package server

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"zeus/sandbox/internal/runner"
)

// Server exposes the sandbox runner over loopback HTTP only.
type Server struct {
	addr      string
	authToken string
	mu        sync.Mutex
	rateMap   map[string][]time.Time
	active    chan struct{}
}

func New(addr string) *Server {
	return &Server{
		addr:      addr,
		authToken: os.Getenv("ZEUS_SANDBOX_AUTH_TOKEN"),
		rateMap:   make(map[string][]time.Time),
		active:    make(chan struct{}, maxConcurrentRuns),
	}
}

func validateLoopbackAddress(addr string) error {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return errors.New("sandbox HTTP listener must bind to a loopback IP; use a TLS/authenticated reverse proxy for remote access")
	}
	return nil
}

func (s *Server) Run() error {
	if strings.TrimSpace(s.authToken) == "" {
		return errors.New("ZEUS_SANDBOX_AUTH_TOKEN must be configured; refusing to start an unauthenticated sandbox server")
	}
	if err := validateLoopbackAddress(s.addr); err != nil {
		return fmt.Errorf("unsafe sandbox listener address: %w", err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/run", s.runHandler)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	server := &http.Server{
		Addr:              s.addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      (runner.MaxTimeoutSec + 10) * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    8 * 1024,
		BaseContext:       func(net.Listener) context.Context { return ctx },
	}
	listener, err := net.Listen("tcp", s.addr)
	if err != nil {
		return fmt.Errorf("listen on sandbox address: %w", err)
	}
	log.Printf("Zeus sandbox server listening on %s", listener.Addr())
	return serveWithShutdown(ctx, server, listener)
}

func serveWithShutdown(ctx context.Context, server *http.Server, listener net.Listener) error {
	serveErr := make(chan error, 1)
	go func() { serveErr <- server.Serve(listener) }()
	select {
	case err := <-serveErr:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			_ = server.Close()
			return fmt.Errorf("sandbox graceful shutdown failed: %w", err)
		}
		err := <-serveErr
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

const (
	maxRequestsPerMinute = 60
	maxBodyBytes         = 64 * 1024
	maxConcurrentRuns    = 4
	maxTrackedClients    = 1024
)

func (s *Server) runHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if strings.TrimSpace(s.authToken) == "" {
		writeResult(w, http.StatusServiceUnavailable, runner.Result{Error: "sandbox authentication token is not configured", ExitCode: 1})
		return
	}
	auth := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if !strings.HasPrefix(auth, prefix) || subtle.ConstantTimeCompare([]byte(auth[len(prefix):]), []byte(s.authToken)) != 1 {
		writeResult(w, http.StatusUnauthorized, runner.Result{Error: "unauthorized", ExitCode: 1})
		return
	}

	clientIP, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		clientIP = r.RemoteAddr
	}
	if !s.allowRequest(clientIP) {
		writeResult(w, http.StatusTooManyRequests, runner.Result{Error: "rate limit exceeded", ExitCode: 1})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	var req runner.Request
	if err := decoder.Decode(&req); err != nil {
		var maxErr *http.MaxBytesError
		status := http.StatusBadRequest
		if errors.As(err, &maxErr) {
			status = http.StatusRequestEntityTooLarge
		}
		writeResult(w, status, runner.Result{Error: "invalid request body", ExitCode: 1})
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeResult(w, http.StatusBadRequest, runner.Result{Error: "request must contain exactly one JSON object", ExitCode: 1})
		return
	}
	if err := runner.ValidateRequest(req); err != nil {
		writeResult(w, http.StatusBadRequest, runner.Result{Error: err.Error(), ExitCode: 1})
		return
	}

	if err := runner.ValidateCommand(req.Command, runner.DefaultAllowedBinaries); err != nil {
		writeResult(w, http.StatusForbidden, runner.Result{Error: err.Error(), ExitCode: 1})
		return
	}

	select {
	case s.active <- struct{}{}:
		defer func() { <-s.active }()
	default:
		writeResult(w, http.StatusServiceUnavailable, runner.Result{Error: "sandbox is at its concurrent execution limit", ExitCode: 1})
		return
	}

	result := runner.Run(r.Context(), req)
	status := http.StatusOK
	if result.Error != "" {
		status = http.StatusServiceUnavailable
	}
	writeResult(w, status, result)
}

func writeResult(w http.ResponseWriter, status int, result runner.Result) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(result)
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
	if len(requests) == 0 && len(s.rateMap) >= maxTrackedClients {
		for ip, timestamps := range s.rateMap {
			active := false
			for _, timestamp := range timestamps {
				if timestamp.After(windowStart) {
					active = true
					break
				}
			}
			if !active {
				delete(s.rateMap, ip)
			}
		}
		if len(s.rateMap) >= maxTrackedClients {
			return false
		}
	}
	s.rateMap[clientIP] = append(valid, now)
	return true
}
