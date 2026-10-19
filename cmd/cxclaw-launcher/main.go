package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"syscall"

	"github.com/SolveaCX/cx_claw_codex/internal/cli"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	root := pluginRoot()
	if target := currentCLI(root); target != "" {
		command := exec.CommandContext(ctx, target, os.Args[1:]...)
		command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
		command.Env = append(os.Environ(), "CXCLAW_PLUGIN_ROOT="+root)
		if err := command.Run(); err != nil {
			if exit, ok := err.(*exec.ExitError); ok {
				os.Exit(exit.ExitCode())
			}
			fmt.Fprintln(os.Stderr, "cxclaw-launcher:", err)
			os.Exit(1)
		}
		return
	}
	if err := cli.Run(ctx, os.Args[1:], os.Stdin, os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "cxclaw-launcher:", err)
		os.Exit(1)
	}
}

func pluginRoot() string {
	if root := os.Getenv("CXCLAW_PLUGIN_ROOT"); root != "" {
		return root
	}
	executable, _ := os.Executable()
	return filepath.Dir(filepath.Dir(executable))
}

func currentCLI(root string) string {
	data, err := os.ReadFile(filepath.Join(root, "current.json"))
	if err != nil {
		return ""
	}
	var pointer struct {
		Current string `json:"current"`
	}
	if json.Unmarshal(data, &pointer) != nil || pointer.Current == "" {
		return ""
	}
	name := "cxclawctl"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	path := filepath.Join(root, "versions", pointer.Current, "bin", name)
	if _, err := os.Stat(path); err != nil {
		return ""
	}
	return path
}
