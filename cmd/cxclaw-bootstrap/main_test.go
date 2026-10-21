package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRegisterMarketplacePreservesExistingPlugins(t *testing.T) {
	root := t.TempDir()
	pluginRoot := filepath.Join(root, ".codex", "plugins", "cxclaw")
	if err := os.MkdirAll(filepath.Join(root, ".agents", "plugins"), 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, ".agents", "plugins", "marketplace.json")
	existing := []byte(`{"name":"personal","plugins":[{"name":"existing"}]}`)
	if err := os.WriteFile(path, existing, 0o600); err != nil {
		t.Fatal(err)
	}

	if err := registerMarketplace(root, pluginRoot); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Name    string                   `json:"name"`
		Plugins []map[string]interface{} `json:"plugins"`
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Name != "personal" || len(manifest.Plugins) != 2 {
		t.Fatalf("existing marketplace content was not preserved: %s", data)
	}
}

func TestSafeInstallRootRejectsHome(t *testing.T) {
	home := t.TempDir()
	if _, err := safeInstallRoot(home, home); err == nil {
		t.Fatal("expected broad home install root to be rejected")
	}
}
