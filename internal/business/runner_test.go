package business

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

func TestBusinessEnvironmentReplacesInheritedTenantCredentials(t *testing.T) {
	t.Setenv("SOLVEA_TOKEN", "stale-token")
	t.Setenv("SOLVEA_PROD_TOKEN", "stale-prod-token")
	t.Setenv("SOLVEA_BASE_URL", "https://stale.example.test")
	t.Setenv("PYTHONPATH", "/existing/python")
	session := &config.Session{Tenant: config.Tenant{
		Environment:   "staging",
		BusinessURL:   "https://business.example.test",
		BusinessToken: "fresh-token",
	}}

	environment := businessEnvironment(session, "/plugin")
	joined := strings.Join(environment, "\n")

	if strings.Contains(joined, "stale-token") || strings.Contains(joined, "stale-prod-token") {
		t.Fatal("inherited tenant token leaked into child environment")
	}
	if !strings.Contains(joined, "SOLVEA_TOKEN=fresh-token") {
		t.Fatal("selected tenant token was not supplied to child environment")
	}
	expectedPath := "PYTHONPATH=" + filepath.Join("/plugin", "python") + string(os.PathListSeparator) + "/existing/python"
	if !strings.Contains(joined, expectedPath) {
		t.Fatalf("vendored Python dependencies missing from PYTHONPATH: %s", joined)
	}
}

func TestLimitedWriterRejectsOversizedOutput(t *testing.T) {
	var output bytes.Buffer
	writer := &limitedWriter{writer: &output, remaining: 4}
	if _, err := writer.Write([]byte("12345")); err == nil {
		t.Fatal("expected oversized output to be rejected")
	}
	if output.Len() != 0 {
		t.Fatal("oversized output must not be partially written")
	}
}
