package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"

	"github.com/SolveaCX/cx_claw_codex/internal/auth"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
	"github.com/SolveaCX/cx_claw_codex/internal/update"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if err := run(ctx, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "cxclaw-bootstrap:", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	flags := flag.NewFlagSet("cxclaw-bootstrap", flag.ContinueOnError)
	server := flags.String("server", "", "shulex-cloud authorization base URL")
	channel := flags.String("channel", "stable", "stable, canary or dev")
	installRoot := flags.String("install-root", filepath.Join(home, ".codex", "cxclaw"), "CXClaw runtime directory")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(*server) == "" {
		return errors.New("--server is required")
	}
	root, err := safeInstallRoot(*installRoot, home)
	if err != nil {
		return err
	}
	if !validChannel(*channel) {
		return errors.New("--channel must be stable, canary or dev")
	}
	if err := os.MkdirAll(root, 0o755); err != nil {
		return err
	}
	if err := os.Setenv("CXCLAW_PLUGIN_ROOT", root); err != nil {
		return err
	}
	session := &config.Session{Channel: *channel}
	version, err := update.Install(ctx, session)
	if err != nil {
		return err
	}
	if version == "" {
		return errors.New("authorization server did not provide an installable plugin release")
	}
	if err := installStableLauncher(root, version); err != nil {
		return err
	}
	if err := installMarketplace(ctx, *channel); err != nil {
		return err
	}
	if _, err := auth.Login(ctx, *server, *channel, os.Stderr); err != nil {
		return err
	}
	launcher := filepath.Join(root, "bin", launcherName())
	if err := installScheduler(ctx, launcher, root); err != nil {
		return fmt.Errorf("install automatic update task: %w", err)
	}
	fmt.Printf("CXClaw %s 已安装并注册到 Git Marketplace。请新建 Codex 会话或重启 Codex。\n", version)
	return nil
}

func validChannel(channel string) bool {
	return channel == "stable" || channel == "canary" || channel == "dev"
}

var runCommand = func(ctx context.Context, name string, args ...string) ([]byte, error) {
	return exec.CommandContext(ctx, name, args...).CombinedOutput()
}

func installMarketplace(ctx context.Context, channel string) error {
	if !validChannel(channel) {
		return errors.New("invalid marketplace channel")
	}
	if _, err := exec.LookPath("codex"); err != nil {
		return errors.New("codex CLI is required to install the CXClaw plugin")
	}
	output, err := runCommand(ctx, "codex", "plugin", "marketplace", "add", "SolveaCX/cx_claw_codex", "--ref", "marketplace/"+channel)
	if err != nil {
		message := strings.ToLower(string(output))
		if !strings.Contains(message, "already") && !strings.Contains(message, "exists") {
			return fmt.Errorf("add CXClaw marketplace: %w: %s", err, strings.TrimSpace(string(output)))
		}
		if output, err = runCommand(ctx, "codex", "plugin", "marketplace", "upgrade", "cxclaw"); err != nil {
			return fmt.Errorf("upgrade CXClaw marketplace: %w: %s", err, strings.TrimSpace(string(output)))
		}
	}
	if output, err = runCommand(ctx, "codex", "plugin", "add", "cxclaw@cxclaw"); err != nil {
		message := strings.ToLower(string(output))
		if !strings.Contains(message, "already") && !strings.Contains(message, "installed") {
			return fmt.Errorf("install CXClaw plugin: %w: %s", err, strings.TrimSpace(string(output)))
		}
	}
	return nil
}

func launcherName() string {
	if runtime.GOOS == "windows" {
		return "cxclaw-launcher.exe"
	}
	return "cxclaw-launcher"
}

func installScheduler(ctx context.Context, launcher, root string) error {
	command := exec.CommandContext(ctx, launcher, "update", "--install-scheduler")
	command.Env = append(os.Environ(), "CXCLAW_PLUGIN_ROOT="+root)
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func safeInstallRoot(value, home string) (string, error) {
	root, err := filepath.Abs(value)
	if err != nil {
		return "", err
	}
	cleanHome, err := filepath.Abs(home)
	if err != nil {
		return "", err
	}
	if root == filepath.Clean(string(os.PathSeparator)) || root == cleanHome {
		return "", errors.New("refusing to use a broad install root")
	}
	return root, nil
}

func installStableLauncher(root, version string) error {
	name := "cxclaw-launcher"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	source := filepath.Join(root, "versions", version, "bin", name)
	data, err := os.ReadFile(source)
	if err != nil {
		return fmt.Errorf("read installed launcher: %w", err)
	}
	targetDir := filepath.Join(root, "bin")
	if err := os.MkdirAll(targetDir, 0o755); err != nil {
		return err
	}
	temporary := filepath.Join(targetDir, name+".new")
	if err := os.WriteFile(temporary, data, 0o755); err != nil {
		return err
	}
	if err := os.Rename(temporary, filepath.Join(targetDir, name)); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return nil
}
