package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func TestInitializeAndLocalToolList(t *testing.T) {
	input := strings.NewReader(
		"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}\n" +
			"{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\",\"params\":{}}\n",
	)
	var output bytes.Buffer
	if err := Serve(context.Background(), input, &output); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(output.String()), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected two responses, got %d", len(lines))
	}
	var initialize map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &initialize); err != nil {
		t.Fatal(err)
	}
	if initialize["result"] == nil {
		t.Fatal("initialize result missing")
	}
	var listed struct {
		Result struct {
			Tools []tool `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal([]byte(lines[1]), &listed); err != nil {
		t.Fatal(err)
	}
	names := map[string]bool{}
	for _, item := range listed.Result.Tools {
		names[item.Name] = true
	}
	for _, required := range []string{"cxclaw.sls_query", "cxclaw.tenant_search", "cxclaw.file_read"} {
		if !names[required] {
			t.Fatalf("local tool %s is missing", required)
		}
	}
}

func TestJSONFormatTool(t *testing.T) {
	server := &Server{}
	result, err := server.callTool(context.Background(), "cxclaw.json_format", map[string]any{"json": "{\"answer\":42}"})
	if err != nil {
		t.Fatal(err)
	}
	items := result.(map[string]any)["content"].([]map[string]any)
	payload := items[0]["text"].(string)
	var wrapper struct {
		JSON string `json:"json"`
	}
	if err := json.Unmarshal([]byte(payload), &wrapper); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(wrapper.JSON, `"answer": 42`) {
		t.Fatalf("unexpected formatted result: %s", payload)
	}
}
