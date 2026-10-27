package server

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"
)

func TestServeWithShutdownCancelsActiveRequests(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	started := make(chan struct{})
	srv := &http.Server{
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			close(started)
			<-r.Context().Done()
		}),
		BaseContext: func(net.Listener) context.Context { return ctx },
	}
	serveDone := make(chan error, 1)
	go func() { serveDone <- serveWithShutdown(ctx, srv, listener) }()
	responseDone := make(chan struct{})
	go func() {
		defer close(responseDone)
		_, _ = http.Get("http://" + listener.Addr().String())
	}()
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("request handler did not start")
	}
	cancel()
	select {
	case err := <-serveDone:
		if err != nil {
			t.Fatalf("serveWithShutdown() error = %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("server did not shut down after cancellation")
	}
	select {
	case <-responseDone:
	case <-time.After(2 * time.Second):
		t.Fatal("active HTTP request was not cancelled")
	}
}
