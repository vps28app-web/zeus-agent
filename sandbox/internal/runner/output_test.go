package runner

import "testing"

func TestBoundedBufferRetainsOnlyConfiguredOutput(t *testing.T) {
	buffer := boundedBuffer{limit: 4}
	written, err := buffer.Write([]byte("abcdef"))
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}
	if written != 6 {
		t.Fatalf("Write() = %d, want full input length 6", written)
	}
	if got := buffer.String(); got != "abcd" {
		t.Fatalf("String() = %q, want %q", got, "abcd")
	}
	if !buffer.truncated {
		t.Fatal("buffer did not mark output as truncated")
	}
}

func TestBoundedBufferDoesNotMarkExactLimitAsTruncated(t *testing.T) {
	buffer := boundedBuffer{limit: 4}
	if _, err := buffer.Write([]byte("abcd")); err != nil {
		t.Fatal(err)
	}
	if buffer.truncated {
		t.Fatal("exactly-sized output was marked truncated")
	}
}
