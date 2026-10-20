package cli

import (
	"context"
	cryptorand "crypto/rand"
	"encoding/binary"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/auth"
	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
	"github.com/SolveaCX/cx_claw_codex/internal/mcp"
	"github.com/SolveaCX/cx_claw_codex/internal/scheduler"
	slsquery "github.com/SolveaCX/cx_claw_codex/internal/sls"
	"github.com/SolveaCX/cx_claw_codex/internal/tenant"
	updatepkg "github.com/SolveaCX/cx_claw_codex/internal/update"
)

func Run(ctx context.Context, args []string, stdin io.Reader, stdout, stderr io.Writer) error {
	if len(args) == 0 {
		usage(stdout)
		return nil
	}
	switch args[0] {
	case "version":
		return printJSON(stdout, map[string]string{
			"pluginVersion": buildinfo.PluginVersion, "cliVersion": buildinfo.CLIVersion,
			"toolSchemaVersion": buildinfo.ToolSchemaVersion, "serverApiVersion": buildinfo.ServerAPIVersion,
		})
	case "login":
		flags := flag.NewFlagSet("login", flag.ContinueOnError)
		flags.SetOutput(stderr)
		server := flags.String("server", "", "solvea-kit base URL")
		channel := flags.String("channel", "stable", "stable, canary or dev")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if *server == "" {
			return errors.New("--server is required")
		}
		session, err := auth.Login(ctx, *server, *channel, stdout)
		if err != nil {
			return err
		}
		fmt.Fprintf(stdout, "已登录：%s\n", session.Email)
		return nil
	case "logout":
		session, _ := config.Load()
		if err := auth.Logout(ctx, session); err != nil {
			return err
		}
		fmt.Fprintln(stdout, "已退出登录")
		return nil
	case "tenant":
		return runTenant(ctx, args[1:], stdout, stderr)
	case "sls":
		return runSLS(ctx, args[1:], stdout, stderr)
	case "api":
		return runAPI(ctx, args[1:], stdout)
	case "mcp":
		if len(args) == 2 && args[1] == "serve" {
			return mcp.Serve(ctx, stdin, stdout)
		}
		return errors.New("usage: cxclawctl mcp serve")
	case "doctor":
		return doctor(args[1:], stdout, stderr)
	case "update":
		return runUpdate(ctx, args[1:], stdout, stderr)
	case "rollback":
		version, err := updatepkg.Rollback()
		if err != nil {
			return err
		}
		fmt.Fprintf(stdout, "已回滚到 %s；新会话或重启 Codex 后生效。\n", version)
		return nil
	case "dev-link":
		return devLink(args[1:], stdout, stderr)
	default:
		return fmt.Errorf("unknown command: %s", args[0])
	}
}

func runTenant(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	if len(args) == 0 {
		return errors.New("usage: cxclawctl tenant search|use|current")
	}
	session, err := loadAuthenticated(ctx)
	if err != nil {
		return err
	}
	switch args[0] {
	case "current":
		return printJSON(stdout, session.Tenant)
	case "search":
		flags := flag.NewFlagSet("tenant search", flag.ContinueOnError)
		flags.SetOutput(stderr)
		environment := flags.String("env", "prod", "prod or staging")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if flags.NArg() != 1 {
			return errors.New("tenant search requires one query")
		}
		items, err := tenant.Search(ctx, session, flags.Arg(0), *environment)
		if err != nil {
			return err
		}
		return printJSON(stdout, items)
	case "use":
		flags := flag.NewFlagSet("tenant use", flag.ContinueOnError)
		flags.SetOutput(stderr)
		environment := flags.String("env", "prod", "prod or staging")
		purpose := flags.String("purpose", "", "access purpose")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if flags.NArg() != 1 {
			return errors.New("tenant use requires one account ID")
		}
		accountID, err := strconv.ParseInt(flags.Arg(0), 10, 64)
		if err != nil || accountID <= 0 {
			return errors.New("account ID must be a positive integer")
		}
		if err := tenant.Use(ctx, session, accountID, *environment, *purpose); err != nil {
			return err
		}
		return printJSON(stdout, session.Tenant)
	default:
		return fmt.Errorf("unknown tenant command: %s", args[0])
	}
}

func runSLS(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	if len(args) == 0 || args[0] != "query" {
		return errors.New("usage: cxclawctl sls query --from UNIX --to UNIX --query DSL")
	}
	flags := flag.NewFlagSet("sls query", flag.ContinueOnError)
	flags.SetOutput(stderr)
	from := flags.Int64("from", 0, "start epoch seconds")
	to := flags.Int64("to", 0, "end epoch seconds")
	query := flags.String("query", "", "SLS query DSL")
	line := flags.Int64("line", 50, "maximum rows")
	offset := flags.Int64("offset", 0, "row offset")
	reverse := flags.Bool("reverse", false, "reverse order")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	session, err := loadAuthenticated(ctx)
	if err != nil {
		return err
	}
	result, err := slsquery.Run(ctx, session, slsquery.Query{
		From: *from, To: *to, Query: *query, Line: *line, Offset: *offset, Reverse: *reverse,
	})
	if err != nil {
		return err
	}
	return printJSON(stdout, result)
}

func runAPI(ctx context.Context, args []string, stdout io.Writer) error {
	if len(args) == 0 {
		return errors.New("usage: cxclawctl api <command> [arguments]")
	}
	session, err := loadAuthenticated(ctx)
	if err != nil {
		return err
	}
	command := args[0]
	commandArgs := make([]string, 0, len(args)-1)
	confirmation := ""
	idempotency := ""
	traceID := ""
	for index := 1; index < len(args); index++ {
		switch args[index] {
		case "--confirmation-token":
			index++
			if index >= len(args) {
				return errors.New("--confirmation-token requires a value")
			}
			confirmation = args[index]
		case "--idempotency-key":
			index++
			if index >= len(args) {
				return errors.New("--idempotency-key requires a value")
			}
			idempotency = args[index]
		case "--trace-id":
			index++
			if index >= len(args) {
				return errors.New("--trace-id requires a value")
			}
			traceID = args[index]
		default:
			commandArgs = append(commandArgs, args[index])
		}
	}
	arguments := map[string]any{"command": command, "args": commandArgs}
	if confirmation != "" {
		arguments["confirmationToken"] = confirmation
	}
	if idempotency != "" {
		arguments["idempotencyKey"] = idempotency
	}
	if traceID != "" {
		arguments["traceId"] = traceID
	}
	var response any
	err = api.New(session).Do(ctx, http.MethodPost, "/mcp", map[string]any{
		"jsonrpc": "2.0", "id": "cli", "method": "tools/call",
		"params": map[string]any{"name": "cxclaw.api", "arguments": arguments},
	}, &response, true)
	if err != nil {
		return err
	}
	return printJSON(stdout, response)
}

func runUpdate(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("update", flag.ContinueOnError)
	flags.SetOutput(stderr)
	scheduled := flags.Bool("scheduled", false, "scheduled update with jitter")
	installScheduler := flags.Bool("install-scheduler", false, "install the six-hour update timer")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *installScheduler {
		executable, err := os.Executable()
		if err != nil {
			return err
		}
		if err := scheduler.Install(executable); err != nil {
			return err
		}
		fmt.Fprintln(stdout, "自动更新任务已安装")
		return nil
	}
	if *scheduled {
		var random [8]byte
		if _, err := cryptorand.Read(random[:]); err == nil {
			jitter := time.Duration(binary.LittleEndian.Uint64(random[:])%1800) * time.Second
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(jitter):
			}
		}
	}
	session, err := loadAuthenticated(ctx)
	if err != nil {
		return err
	}
	version, err := updatepkg.Install(ctx, session)
	if err != nil {
		return err
	}
	if version == "" {
		fmt.Fprintln(stdout, "当前已是最新版本")
	} else {
		fmt.Fprintf(stdout, "已安装 %s；新会话或重启 Codex 后生效。\n", version)
	}
	return nil
}

func doctor(args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("doctor", flag.ContinueOnError)
	flags.SetOutput(stderr)
	installRoot := flags.String("install-root", "", "installation root")
	if err := flags.Parse(args); err != nil {
		return err
	}
	root := *installRoot
	if root == "" {
		var err error
		root, err = updatepkg.Root()
		if err != nil {
			return err
		}
	}
	required := []string{"plugin.json", "mcp.json", "skills", "capabilities.lock.json"}
	for _, item := range required {
		if _, err := os.Stat(filepath.Join(root, item)); err != nil {
			return fmt.Errorf("doctor: missing %s", item)
		}
	}
	fmt.Fprintf(stdout, "doctor ok: root=%s cli=%s\n", root, buildinfo.CLIVersion)
	return nil
}

func devLink(args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("dev-link", flag.ContinueOnError)
	flags.SetOutput(stderr)
	marketplaceRoot := flags.String("marketplace-root", "", "marketplace root directory")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *marketplaceRoot == "" {
		return errors.New("--marketplace-root is required")
	}
	pluginRoot, err := updatepkg.Root()
	if err != nil {
		return err
	}
	absoluteMarketplace, err := filepath.Abs(*marketplaceRoot)
	if err != nil {
		return err
	}
	relativePlugin, err := filepath.Rel(absoluteMarketplace, pluginRoot)
	if err != nil {
		return err
	}
	if relativePlugin == ".." || strings.HasPrefix(relativePlugin, ".."+string(os.PathSeparator)) {
		return errors.New("plugin root must be inside marketplace root for a portable local marketplace")
	}
	relativePlugin = "./" + filepath.ToSlash(relativePlugin)
	path := filepath.Join(*marketplaceRoot, ".agents", "plugins")
	if err := os.MkdirAll(path, 0o755); err != nil {
		return err
	}
	manifest := map[string]any{
		"name":      "cxclaw-dev",
		"interface": map[string]any{"displayName": "CXClaw Dev"},
		"plugins": []any{map[string]any{
			"name": "cxclaw", "source": map[string]any{"source": "local", "path": relativePlugin},
			"policy":   map[string]any{"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
			"category": "Developer Tools",
		}},
	}
	data, _ := json.MarshalIndent(manifest, "", "  ")
	file := filepath.Join(path, "marketplace.json")
	if err := os.WriteFile(file, data, 0o600); err != nil {
		return err
	}
	fmt.Fprintln(stdout, file)
	return nil
}

func loadAuthenticated(ctx context.Context) (*config.Session, error) {
	session, err := config.Load()
	if err != nil {
		return nil, errors.New("未登录，请先运行 cxclawctl login")
	}
	if err := auth.EnsureAccess(ctx, session); err != nil {
		return nil, err
	}
	return session, nil
}

func printJSON(output io.Writer, value any) error {
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	encoder.SetEscapeHTML(false)
	return encoder.Encode(value)
}

func usage(output io.Writer) {
	fmt.Fprintln(output, strings.TrimSpace(`cxclawctl commands:
  login/logout
  tenant search|use|current
  sls query
  api <command>
  mcp serve
  doctor/update/rollback/dev-link/version`))
}
