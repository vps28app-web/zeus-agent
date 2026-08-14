package main

import (
	"flag"
	"log"

	"zeus/sandbox/internal/runner"
	"zeus/sandbox/internal/server"
)

func main() {
	if runner.IsChildMode() {
		runner.ExecChild()
	}
	if runner.IsInternalChildMode() {
		runner.ExecInternalChild()
	}

	addr := flag.String("addr", "127.0.0.1:9876", "Address to listen on")
	flag.Parse()

	srv := server.New(*addr)
	if err := srv.Run(); err != nil {
		log.Fatalf("sandbox server failed: %v", err)
	}
}
