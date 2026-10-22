package main

import (
	"context"
	"encoding/json"
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
	installRoot := flags.String("install-root", filepath.Join(home, ".codex", "plugins", "cxclaw"), "plugin source directory")
	marketplaceRoot := flags.String("marketplace-root", home, "personal marketplace root")
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
	marketRoot, err := filepath.Abs(*marketplaceRoot)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(root, 0o755); err != nil {
		return err
	}
	if err := os.Setenv("CXCLAW_PLUGIN_ROOT", root); err != nil {
		return err
	}
	session, err := auth.Login(ctx, *server, *channel, os.Stderr)
	if err != nil {
		return err
	}
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
	if err := registerMarketplace(marketRoot, root); err != nil {
		return err
	}
	launcher := filepath.Join(root, "bin", launcherName())
	if err := installScheduler(ctx, launcher, root); err != nil {
		return fmt.Errorf("install automatic update task: %w", err)
	}
	fmt.Printf("CXClaw %s 已下载并注册到个人插件市场。请重启 Codex，并在插件目录确认 CXClaw 已启用。\n", version)
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

func registerMarketplace(marketplaceRoot, pluginRoot string) error {
	relativePlugin, err := filepath.Rel(marketplaceRoot, pluginRoot)
	if err != nil {
		return err
	}
	if relativePlugin == ".." || strings.HasPrefix(relativePlugin, ".."+string(os.PathSeparator)) {
		return errors.New("plugin source must be inside the marketplace root")
	}
	path := filepath.Join(marketplaceRoot, ".agents", "plugins", "marketplace.json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	manifest := map[string]interface{}{}
	if data, readErr := os.ReadFile(path); readErr == nil {
		if err := json.Unmarshal(data, &manifest); err != nil {
			return fmt.Errorf("existing marketplace is invalid JSON: %w", err)
		}
	} else if !os.IsNotExist(readErr) {
		return readErr
	}
	if _, exists := manifest["name"]; !exists {
		manifest["name"] = "solvea-internal"
	}
	if _, exists := manifest["interface"]; !exists {
		manifest["interface"] = map[string]interface{}{"displayName": "Solvea Internal"}
	}
	plugins, _ := manifest["plugins"].([]interface{})
	entry := map[string]interface{}{
		"name": "cxclaw",
		"source": map[string]interface{}{
			"source": "local",
			"path":   "./" + filepath.ToSlash(relativePlugin),
		},
		"policy": map[string]interface{}{
			"installation":   "INSTALLED_BY_DEFAULT",
			"authentication": "ON_INSTALL",
		},
		"category":  "Developer Tools",
		"interface": map[string]interface{}{"displayName": "CXClaw"},
	}
	replaced := false
	for index, raw := range plugins {
		item, ok := raw.(map[string]interface{})
		if ok && item["name"] == "cxclaw" {
			plugins[index] = entry
			replaced = true
			break
		}
	}
	if !replaced {
		plugins = append(plugins, entry)
	}
	manifest["plugins"] = plugins
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o600)
}
