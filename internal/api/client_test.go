package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

func TestDoAppendsEndpointToExistingSolveaKitBasePath(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/api_v2/solvea-kit/tenants/search" {
			t.Fatalf("unexpected request path: %s", request.URL.Path)
		}
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(map[string]any{"items": []any{}})
	}))
	t.Cleanup(server.Close)

	session := &config.Session{ServerURL: server.URL + "/api_v2/solvea-kit"}
	var response map[string]any
	if err := New(session).Do(
		context.Background(),
		http.MethodPost,
		"/tenants/search",
		map[string]any{"query": "acme", "environment": "staging"},
		&response,
		false,
	); err != nil {
		t.Fatal(err)
	}
}
