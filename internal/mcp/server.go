package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/auth"
	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
	slsquery "github.com/SolveaCX/cx_claw_codex/internal/sls"
	"github.com/SolveaCX/cx_claw_codex/internal/tenant"
)

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  any             `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type tool struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"inputSchema"`
	Annotations map[string]any `json:"annotations,omitempty"`
}

type Server struct {
	mu      sync.Mutex
	session *config.Session
}

func Serve(ctx context.Context, input io.Reader, output io.Writer) error {
	server := &Server{}
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 64*1024), 8<<20)
	encoder := json.NewEncoder(output)
	for scanner.Scan() {
		var req request
		if err := json.Unmarshal(scanner.Bytes(), &req); err != nil {
			_ = encoder.Encode(response{JSONRPC: "2.0", Error: &rpcError{Code: -32700, Message: "parse error"}})
			continue
		}
		if req.Method == "notifications/initialized" {
			continue
		}
		resp := server.handle(ctx, req)
		if err := encoder.Encode(resp); err != nil {
			return err
		}
	}
	return scanner.Err()
}

func (s *Server) handle(ctx context.Context, req request) response {
	result, err := s.dispatch(ctx, req.Method, req.Params)
	if err != nil {
		return response{JSONRPC: "2.0", ID: req.ID, Error: &rpcError{Code: -32000, Message: err.Error()}}
	}
	return response{JSONRPC: "2.0", ID: req.ID, Result: result}
}

func (s *Server) dispatch(ctx context.Context, method string, raw json.RawMessage) (any, error) {
	switch method {
	case "initialize":
		return map[string]any{
			"protocolVersion": "2025-06-18",
			"capabilities":    map[string]any{"tools": map[string]any{"listChanged": false}},
			"serverInfo":      map[string]any{"name": "cxclaw", "version": buildinfo.CLIVersion},
			"instructions":    "Select a tenant before tenant-scoped calls. For writes, show the preview and ask the user before returning the confirmation token and idempotency key.",
		}, nil
	case "ping":
		return map[string]any{}, nil
	case "tools/list":
		tools := localTools()
		if session, err := s.loadSession(ctx); err == nil && session.Tenant.Context != "" {
			if remote, err := remoteTools(ctx, session); err == nil {
				tools = append(tools, remote...)
			}
		}
		return map[string]any{"tools": tools}, nil
	case "tools/call":
		var call struct {
			Name      string         `json:"name"`
			Arguments map[string]any `json:"arguments"`
		}
		if err := json.Unmarshal(raw, &call); err != nil {
			return nil, err
		}
		return s.callTool(ctx, call.Name, call.Arguments)
	default:
		return nil, fmt.Errorf("method not found: %s", method)
	}
}

func (s *Server) loadSession(ctx context.Context) (*config.Session, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.session == nil {
		loaded, err := config.Load()
		if err != nil {
			return nil, err
		}
		s.session = loaded
	}
	if err := auth.EnsureAccess(ctx, s.session); err != nil {
		return nil, err
	}
	return s.session, nil
}

func (s *Server) callTool(ctx context.Context, name string, arguments map[string]any) (any, error) {
	switch name {
	case "cxclaw.auth_status":
		session, err := s.loadSession(ctx)
		if err != nil {
			return content(map[string]any{"loggedIn": false}), nil
		}
		return content(map[string]any{"loggedIn": true, "employeeId": session.EmployeeID, "email": session.Email}), nil
	case "cxclaw.tenant_current":
		session, err := s.loadSession(ctx)
		if err != nil {
			return nil, err
		}
		return content(session.Tenant), nil
	case "cxclaw.tenant_search":
		session, err := s.loadSession(ctx)
		if err != nil {
			return nil, err
		}
		items, err := tenant.Search(ctx, session, stringArg(arguments, "query"), stringArg(arguments, "environment"))
		if err != nil {
			return nil, err
		}
		return content(items), nil
	case "cxclaw.tenant_use":
		session, err := s.loadSession(ctx)
		if err != nil {
			return nil, err
		}
		accountID, err := int64Arg(arguments, "accountId")
		if err != nil {
			return nil, err
		}
		if err := tenant.Use(ctx, session, accountID, stringArg(arguments, "environment"), stringArg(arguments, "purpose")); err != nil {
			return nil, err
		}
		return content(session.Tenant), nil
	case "cxclaw.sls_query":
		session, err := s.loadSession(ctx)
		if err != nil {
			return nil, err
		}
		query, err := queryArgs(arguments)
		if err != nil {
			return nil, err
		}
		result, err := slsquery.Run(ctx, session, query)
		if err != nil {
			return nil, err
		}
		return content(result), nil
	case "cxclaw.file_read":
		path := stringArg(arguments, "path")
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		if len(data) > 1<<20 {
			return nil, errors.New("file exceeds 1 MiB")
		}
		return content(map[string]any{"path": path, "content": string(data)}), nil
	case "cxclaw.git_status":
		path := stringArg(arguments, "path")
		command := exec.CommandContext(ctx, "git", "-C", path, "status", "--short", "--branch")
		data, err := command.CombinedOutput()
		if err != nil {
			return nil, fmt.Errorf("git status: %w", err)
		}
		return content(map[string]any{"path": path, "status": string(data)}), nil
	case "cxclaw.json_format":
		var value any
		if err := json.Unmarshal([]byte(stringArg(arguments, "json")), &value); err != nil {
			return nil, err
		}
		pretty, _ := json.MarshalIndent(value, "", "  ")
		return content(map[string]any{"json": string(pretty)}), nil
	default:
		session, err := s.loadSession(ctx)
		if err != nil {
			return nil, err
		}
		return remoteCall(ctx, session, name, arguments)
	}
}

func localTools() []tool {
	object := func(properties map[string]any, required ...string) map[string]any {
		return map[string]any{"type": "object", "properties": properties, "required": required}
	}
	readOnly := map[string]any{"readOnlyHint": true, "destructiveHint": false, "openWorldHint": false}
	return []tool{
		{Name: "cxclaw.auth_status", Description: "Show the current DingTalk login identity.", InputSchema: object(map[string]any{}), Annotations: readOnly},
		{Name: "cxclaw.tenant_current", Description: "Show the selected tenant and environment.", InputSchema: object(map[string]any{}), Annotations: readOnly},
		{Name: "cxclaw.tenant_search", Description: "Search authorized tenants by name, code, or ID.", InputSchema: object(map[string]any{"query": map[string]any{"type": "string"}, "environment": map[string]any{"type": "string", "enum": []string{"staging", "prod"}}}, "query", "environment"), Annotations: readOnly},
		{Name: "cxclaw.tenant_use", Description: "Select and sign a tenant context for later calls.", InputSchema: object(map[string]any{"accountId": map[string]any{"type": "integer"}, "environment": map[string]any{"type": "string", "enum": []string{"staging", "prod"}}, "purpose": map[string]any{"type": "string"}}, "accountId", "environment", "purpose")},
		{Name: "cxclaw.sls_query", Description: "Query Aliyun SLS directly from this client using short-lived read-only STS credentials.", InputSchema: object(map[string]any{"fromTime": map[string]any{"type": "integer"}, "toTime": map[string]any{"type": "integer"}, "query": map[string]any{"type": "string"}, "line": map[string]any{"type": "integer"}, "offset": map[string]any{"type": "integer"}, "reverse": map[string]any{"type": "boolean"}}, "fromTime", "toTime", "query"), Annotations: readOnly},
		{Name: "cxclaw.file_read", Description: "Read a local text or attachment file up to 1 MiB.", InputSchema: object(map[string]any{"path": map[string]any{"type": "string"}}, "path"), Annotations: readOnly},
		{Name: "cxclaw.git_status", Description: "Read the concise Git status of a local repository.", InputSchema: object(map[string]any{"path": map[string]any{"type": "string"}}, "path"), Annotations: readOnly},
		{Name: "cxclaw.json_format", Description: "Parse and pretty-format JSON locally without network access.", InputSchema: object(map[string]any{"json": map[string]any{"type": "string"}}, "json"), Annotations: readOnly},
	}
}

func remoteTools(ctx context.Context, session *config.Session) ([]tool, error) {
	var rpc struct {
		Result struct {
			Tools []tool `json:"tools"`
		} `json:"result"`
	}
	err := api.New(session).Do(ctx, http.MethodPost, "/codex/v1/mcp", map[string]any{
		"jsonrpc": "2.0", "id": "tools", "method": "tools/list", "params": map[string]any{},
	}, &rpc, true)
	return rpc.Result.Tools, err
}

func remoteCall(ctx context.Context, session *config.Session, name string, arguments map[string]any) (any, error) {
	var rpc map[string]any
	err := api.New(session).Do(ctx, http.MethodPost, "/codex/v1/mcp", map[string]any{
		"jsonrpc": "2.0", "id": fmt.Sprintf("call-%d", time.Now().UnixNano()),
		"method": "tools/call", "params": map[string]any{"name": name, "arguments": arguments},
	}, &rpc, true)
	if err != nil {
		return nil, err
	}
	if rpcError, ok := rpc["error"]; ok {
		return nil, fmt.Errorf("remote MCP error: %v", rpcError)
	}
	return rpc["result"], nil
}

func content(value any) map[string]any {
	data, _ := json.Marshal(value)
	return map[string]any{"content": []map[string]any{{"type": "text", "text": string(data)}}, "isError": false}
}

func stringArg(arguments map[string]any, name string) string {
	value, _ := arguments[name].(string)
	return strings.TrimSpace(value)
}

func int64Arg(arguments map[string]any, name string) (int64, error) {
	value, ok := arguments[name].(float64)
	if !ok || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return int64(value), nil
}

func queryArgs(arguments map[string]any) (slsquery.Query, error) {
	from, okFrom := arguments["fromTime"].(float64)
	to, okTo := arguments["toTime"].(float64)
	if !okFrom || !okTo {
		return slsquery.Query{}, errors.New("fromTime and toTime are required")
	}
	query := slsquery.Query{From: int64(from), To: int64(to), Query: stringArg(arguments, "query"), Line: 50}
	if line, ok := arguments["line"].(float64); ok {
		query.Line = int64(line)
	}
	if offset, ok := arguments["offset"].(float64); ok {
		query.Offset = int64(offset)
	}
	query.Reverse, _ = arguments["reverse"].(bool)
	return query, nil
}

func PluginRoot() string {
	if root := os.Getenv("CXCLAW_PLUGIN_ROOT"); root != "" {
		return root
	}
	executable, _ := os.Executable()
	return filepath.Dir(filepath.Dir(executable))
}
