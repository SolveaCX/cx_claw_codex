package update

import (
	"archive/zip"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"

	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
)

func TestVerifySignedPackageAndRejectTampering(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	originalKey := buildinfo.UpdatePublicKeyBase64
	buildinfo.UpdatePublicKeyBase64 = base64.StdEncoding.EncodeToString(publicKey)
	t.Cleanup(func() { buildinfo.UpdatePublicKeyBase64 = originalKey })
	path := filepath.Join(t.TempDir(), "package.zip")
	data := []byte("signed package")
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(data)
	hash := hex.EncodeToString(digest[:])
	signature := base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey, []byte(hash)))
	if err := verify(path, hash, signature); err != nil {
		t.Fatalf("valid signature rejected: %v", err)
	}
	if err := os.WriteFile(path, []byte("tampered"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := verify(path, hash, signature); err == nil {
		t.Fatal("tampered package was accepted")
	}
}

func TestExtractZipRejectsTraversalAndSymlink(t *testing.T) {
	tests := []struct {
		name, path string
		mode       os.FileMode
	}{
		{name: "traversal", path: "../escape"},
		{name: "symlink", path: "link", mode: os.ModeSymlink | 0o777},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			archive := filepath.Join(t.TempDir(), "bad.zip")
			file, err := os.Create(archive)
			if err != nil {
				t.Fatal(err)
			}
			writer := zip.NewWriter(file)
			header := &zip.FileHeader{Name: test.path, Method: zip.Store}
			if test.mode != 0 {
				header.SetMode(test.mode)
			}
			entry, err := writer.CreateHeader(header)
			if err != nil {
				t.Fatal(err)
			}
			_, _ = entry.Write([]byte("bad"))
			_ = writer.Close()
			_ = file.Close()
			if err := extractZip(archive, filepath.Join(t.TempDir(), "out")); err == nil {
				t.Fatal("unsafe archive was accepted")
			}
		})
	}
}

func TestRetainAndPruneVersions(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"1.0.0", "1.1.0", "1.2.0", "old"} {
		if err := os.Mkdir(filepath.Join(root, name), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	history := retainHistory([]string{"1.2.0", "1.1.0", "1.2.0", "1.0.0"}, 3)
	if err := pruneVersions(root, history); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "old")); !os.IsNotExist(err) {
		t.Fatal("old version was not removed")
	}
	for _, name := range history {
		if _, err := os.Stat(filepath.Join(root, name)); err != nil {
			t.Fatalf("retained version %s is missing: %v", name, err)
		}
	}
}

func TestActivateAssetsUpdatesLocalPluginPackage(t *testing.T) {
	root := t.TempDir()
	version := filepath.Join(root, "versions", "2.0.0")
	for _, base := range []string{root, version} {
		if err := os.MkdirAll(filepath.Join(base, "skills", "demo"), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.MkdirAll(filepath.Join(base, "runtime", "python", "bin"), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.MkdirAll(filepath.Join(base, ".codex-plugin"), 0o755); err != nil {
			t.Fatal(err)
		}
		for _, name := range []string{"plugin.json", "capabilities.lock.json", "README.md", "requirements-cli.txt"} {
			if err := os.WriteFile(filepath.Join(base, name), []byte(base), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		if err := os.WriteFile(filepath.Join(base, ".codex-plugin", "plugin.json"), []byte(base), 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(base, "skills", "demo", "SKILL.md"), []byte(base), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if err := activateAssets(root, version); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(root, "skills", "demo", "SKILL.md"))
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != version {
		t.Fatalf("root skill was not activated: %s", data)
	}
}
