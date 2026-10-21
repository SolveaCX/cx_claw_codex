package auth

import "testing"

func TestEnvelopeCodeReadsBusinessStatus(t *testing.T) {
	if got := envelopeCode([]byte(`{"code":428,"message":"authorization_pending"}`)); got != 428 {
		t.Fatalf("envelopeCode() = %d, want 428", got)
	}
}

func TestEnvelopeCodeRejectsInvalidJSON(t *testing.T) {
	if got := envelopeCode([]byte(`not-json`)); got != 0 {
		t.Fatalf("envelopeCode() = %d, want 0", got)
	}
}
