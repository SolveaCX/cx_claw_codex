package main

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestInstallMarketplaceRunsOfficialCommands(t *testing.T) {
	original := runCommand
	t.Cleanup(func() { runCommand = original })
	var calls [][]string
	runCommand = func(_ context.Context, name string, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{name}, args...))
		return nil, nil
	}
	dir := t.TempDir()
	if err := os.Symlink(os.Args[0], filepath.Join(dir, "codex")); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir)
	if err := installMarketplace(context.Background(), "stable"); err != nil {
		t.Fatal(err)
	}
	want := [][]string{
		{"codex", "plugin", "marketplace", "add", "SolveaCX/cx_claw_codex", "--ref", "marketplace/stable"},
		{"codex", "plugin", "add", "cxclaw@cxclaw"},
	}
	if !reflect.DeepEqual(calls, want) {
		t.Fatalf("commands = %#v", calls)
	}
}

func TestInstallMarketplaceRejectsInvalidChannel(t *testing.T) {
	if err := installMarketplace(context.Background(), "stable;rm"); err == nil {
		t.Fatal("unsafe channel accepted")
	}
}

func TestInstallMarketplaceReportsCodexMissing(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	if err := installMarketplace(context.Background(), "stable"); err == nil {
		t.Fatal("missing codex accepted")
	}
}

func TestSafeInstallRootRejectsHome(t *testing.T) {
	home := t.TempDir()
	if _, err := safeInstallRoot(home, home); err == nil {
		t.Fatal("expected broad home install root to be rejected")
	}
}
