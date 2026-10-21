package business

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestConfirmationBindsCommandArgumentsAndFileContents(t *testing.T) {
	directory := t.TempDir()
	file := filepath.Join(directory, "payload.json")
	if err := os.WriteFile(file, []byte(`{"name":"before"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	hash, err := RequestHash("update-agent", []string{"--data-file", file})
	if err != nil {
		t.Fatal(err)
	}
	now := time.Unix(1_800_000_000, 0)
	token := ConfirmationToken("refresh-secret", hash, now)
	if err := VerifyConfirmation("refresh-secret", token, hash, now.Add(time.Minute)); err != nil {
		t.Fatalf("valid confirmation rejected: %v", err)
	}
	if err := os.WriteFile(file, []byte(`{"name":"after"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	changedHash, err := RequestHash("update-agent", []string{"--data-file", file})
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyConfirmation("refresh-secret", token, changedHash, now.Add(time.Minute)); err == nil {
		t.Fatal("confirmation accepted modified file contents")
	}
}

func TestConfirmationExpires(t *testing.T) {
	now := time.Unix(1_800_000_000, 0)
	token := ConfirmationToken("refresh-secret", "hash", now)
	if err := VerifyConfirmation("refresh-secret", token, "hash", now.Add(6*time.Minute)); err == nil {
		t.Fatal("expired confirmation was accepted")
	}
}

func TestReadOnlyClassification(t *testing.T) {
	for _, command := range []string{"get-agent", "list-agents", "query-mock-data", "report-agent", "resolve-transcript-chat-id"} {
		if IsWrite(command) {
			t.Fatalf("%s classified as write", command)
		}
	}
	for _, command := range []string{"create-agent", "update-agent", "delete-plugin", "chat"} {
		if !IsWrite(command) {
			t.Fatalf("%s classified as read", command)
		}
	}
}
