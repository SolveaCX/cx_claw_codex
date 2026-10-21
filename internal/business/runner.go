package business

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/SolveaCX/cx_claw_codex/internal/config"
	updatepkg "github.com/SolveaCX/cx_claw_codex/internal/update"
)

const outputLimit = 8 << 20

type Result struct {
	Value  any
	Stderr string
}

func Run(ctx context.Context, session *config.Session, command string, args []string, stdin io.Reader) (*Result, error) {
	if session == nil || session.Tenant.BusinessToken == "" || session.Tenant.BusinessURL == "" {
		return nil, errors.New("tenant business credentials are unavailable; select the tenant again")
	}
	root, err := updatepkg.Root()
	if err != nil {
		return nil, err
	}
	script := filepath.Join(root, "skills", "__lib__", "solvea-api", "solvea_api.py")
	if _, err := os.Stat(script); err != nil {
		return nil, fmt.Errorf("business command runtime is missing: %w", err)
	}
	python, err := PythonExecutable()
	if err != nil {
		return nil, err
	}
	commandArgs := append([]string{script, command}, args...)
	cmd := exec.CommandContext(ctx, python, commandArgs...)
	cmd.Stdin = stdin
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &limitedWriter{writer: &stdout, remaining: outputLimit}
	cmd.Stderr = &limitedWriter{writer: &stderr, remaining: outputLimit}
	cmd.Env = businessEnvironment(session, root)
	if err := cmd.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = strings.TrimSpace(stdout.String())
		}
		if message == "" {
			message = err.Error()
		}
		return nil, fmt.Errorf("business command %s failed: %s", command, message)
	}
	var value any
	if err := json.Unmarshal(stdout.Bytes(), &value); err != nil {
		return nil, fmt.Errorf("business command returned invalid JSON: %w", err)
	}
	return &Result{Value: value, Stderr: strings.TrimSpace(stderr.String())}, nil
}

func businessEnvironment(session *config.Session, root string) []string {
	environment := make([]string, 0, len(os.Environ())+6)
	blocked := []string{
		"SOLVEA_ENV=", "SOLVEA_BASE_URL=", "SOLVEA_PROD_URL=", "SOLVEA_TOKEN=",
		"SOLVEA_PROD_TOKEN=", "SOLVEA_PROJECT_ID=", "CXCLAW_PLUGIN_ROOT=", "PYTHONPATH=",
	}
	for _, item := range os.Environ() {
		allowed := true
		for _, prefix := range blocked {
			if strings.HasPrefix(item, prefix) {
				allowed = false
				break
			}
		}
		if allowed {
			environment = append(environment, item)
		}
	}
	environment = append(environment,
		"SOLVEA_ENV="+session.Tenant.Environment,
		"SOLVEA_BASE_URL="+session.Tenant.BusinessURL,
		"SOLVEA_PROD_URL="+session.Tenant.BusinessURL,
		"SOLVEA_TOKEN="+session.Tenant.BusinessToken,
		"SOLVEA_PROD_TOKEN="+session.Tenant.BusinessToken,
		"CXCLAW_PLUGIN_ROOT="+root,
	)
	pythonPath := filepath.Join(root, "python")
	if inherited := strings.TrimSpace(os.Getenv("PYTHONPATH")); inherited != "" {
		pythonPath += string(os.PathListSeparator) + inherited
	}
	environment = append(environment, "PYTHONPATH="+pythonPath)
	return environment
}

func PythonExecutable() (string, error) {
	if configured := strings.TrimSpace(os.Getenv("CXCLAW_PYTHON")); configured != "" {
		return configured, nil
	}
	candidates := []string{"python3", "python"}
	if runtime.GOOS == "windows" {
		candidates = []string{"python.exe", "python3.exe", "py.exe"}
	}
	for _, candidate := range candidates {
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	return "", errors.New("Python 3 is required for CXClaw business commands; run cxclawctl doctor for details")
}

func CheckRuntime(ctx context.Context, root string) error {
	python, err := PythonExecutable()
	if err != nil {
		return err
	}
	script := filepath.Join(root, "skills", "__lib__", "solvea-api", "solvea_api.py")
	if _, err := os.Stat(script); err != nil {
		return fmt.Errorf("business command runtime is missing: %w", err)
	}
	cmd := exec.CommandContext(ctx, python, "-c", "import sys,httpx,boto3; assert sys.version_info >= (3, 9)")
	cmd.Env = append(os.Environ(), "PYTHONPATH="+filepath.Join(root, "python"))
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("Python business runtime dependencies are unavailable: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

type limitedWriter struct {
	writer    io.Writer
	remaining int
}

func (w *limitedWriter) Write(value []byte) (int, error) {
	if len(value) > w.remaining {
		return 0, errors.New("business command output exceeds 8 MiB")
	}
	count, err := w.writer.Write(value)
	w.remaining -= count
	return count, err
}
