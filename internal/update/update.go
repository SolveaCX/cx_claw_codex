package update

import (
	"archive/zip"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

var safeVersion = regexp.MustCompile(`^[0-9A-Za-z._-]{1,64}$`)

type CheckResponse struct {
	UpdateAvailable bool   `json:"updateAvailable"`
	Channel         string `json:"channel"`
	Version         string `json:"version"`
	SHA256          string `json:"sha256"`
	Signature       string `json:"signature"`
	DownloadURL     string `json:"downloadUrl"`
}

type Pointer struct {
	Current  string   `json:"current"`
	Previous string   `json:"previous,omitempty"`
	History  []string `json:"history,omitempty"`
}

func Root() (string, error) {
	if value := os.Getenv("CXCLAW_PLUGIN_ROOT"); value != "" {
		return filepath.Abs(value)
	}
	executable, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.Dir(filepath.Dir(executable)), nil
}

func Check(ctx context.Context, session *config.Session) (*CheckResponse, error) {
	channel := session.Channel
	if channel == "" {
		channel = "stable"
	}
	var response CheckResponse
	path := fmt.Sprintf(
		"/releases/check?channel=%s&currentVersion=%s",
		channel, buildinfo.PluginVersion,
	)
	if err := api.New(session).Do(ctx, http.MethodGet, path, nil, &response, false); err != nil {
		return nil, err
	}
	return &response, nil
}

func Install(ctx context.Context, session *config.Session) (string, error) {
	release, err := Check(ctx, session)
	if err != nil {
		return "", err
	}
	if !release.UpdateAvailable {
		return "", nil
	}
	if !safeVersion.MatchString(release.Version) {
		return "", errors.New("server returned an unsafe version")
	}
	root, err := Root()
	if err != nil {
		return "", err
	}
	tempFile, err := os.CreateTemp("", "cxclaw-update-*.zip")
	if err != nil {
		return "", err
	}
	tempPath := tempFile.Name()
	tempFile.Close()
	defer os.Remove(tempPath)
	if err := download(ctx, release.DownloadURL, tempPath); err != nil {
		return "", err
	}
	if err := verify(tempPath, release.SHA256, release.Signature); err != nil {
		return "", err
	}
	versionsRoot := filepath.Join(root, "versions")
	if err := os.MkdirAll(versionsRoot, 0o755); err != nil {
		return "", err
	}
	target := filepath.Join(versionsRoot, release.Version)
	if err := os.RemoveAll(target); err != nil {
		return "", err
	}
	if err := extractZip(tempPath, target); err != nil {
		_ = os.RemoveAll(target)
		return "", err
	}
	cli := filepath.Join(target, "bin", binaryName("cxclawctl"))
	command := exec.CommandContext(ctx, cli, "doctor", "--install-root", target)
	if output, err := command.CombinedOutput(); err != nil {
		_ = os.RemoveAll(target)
		return "", fmt.Errorf("new version doctor failed: %w: %s", err, strings.TrimSpace(string(output)))
	}
	if err := activateAssets(root, target); err != nil {
		_ = os.RemoveAll(target)
		return "", fmt.Errorf("activate plugin assets: %w", err)
	}
	pointer, _ := readPointer(root)
	previous := pointer.Current
	pointer.Previous = previous
	pointer.Current = release.Version
	pointer.History = retainHistory(
		append([]string{release.Version, previous}, pointer.History...),
		3,
	)
	if err := writePointer(root, pointer); err != nil {
		return "", err
	}
	if err := pruneVersions(versionsRoot, pointer.History); err != nil {
		return "", fmt.Errorf("installed update but could not prune old versions: %w", err)
	}
	return release.Version, nil
}

func Rollback() (string, error) {
	root, err := Root()
	if err != nil {
		return "", err
	}
	pointer, err := readPointer(root)
	if err != nil {
		return "", err
	}
	if pointer.Previous == "" {
		return "", errors.New("no previous version is available")
	}
	if _, err := os.Stat(filepath.Join(root, "versions", pointer.Previous)); err != nil {
		return "", errors.New("previous version directory is missing")
	}
	if err := activateAssets(root, filepath.Join(root, "versions", pointer.Previous)); err != nil {
		return "", fmt.Errorf("restore plugin assets: %w", err)
	}
	pointer.Current, pointer.Previous = pointer.Previous, pointer.Current
	if err := writePointer(root, pointer); err != nil {
		return "", err
	}
	return pointer.Current, nil
}

func readPointer(root string) (Pointer, error) {
	var pointer Pointer
	data, err := os.ReadFile(filepath.Join(root, "current.json"))
	if err != nil {
		if os.IsNotExist(err) {
			return pointer, nil
		}
		return pointer, err
	}
	err = json.Unmarshal(data, &pointer)
	return pointer, err
}

func writePointer(root string, pointer Pointer) error {
	data, err := json.MarshalIndent(pointer, "", "  ")
	if err != nil {
		return err
	}
	temp, err := os.CreateTemp(root, "current-*.json")
	if err != nil {
		return err
	}
	tempName := temp.Name()
	defer os.Remove(tempName)
	if _, err := temp.Write(data); err != nil {
		temp.Close()
		return err
	}
	if err := temp.Sync(); err != nil {
		temp.Close()
		return err
	}
	if err := temp.Close(); err != nil {
		return err
	}
	return os.Rename(tempName, filepath.Join(root, "current.json"))
}

func verify(path, expectedHash, signatureBase64 string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(data)
	actual := hex.EncodeToString(digest[:])
	if !strings.EqualFold(actual, expectedHash) {
		return errors.New("update package SHA-256 mismatch")
	}
	publicKey, err := base64.StdEncoding.DecodeString(buildinfo.UpdatePublicKeyBase64)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return errors.New("update verification public key is not configured")
	}
	signature, err := base64.StdEncoding.DecodeString(signatureBase64)
	if err != nil || !ed25519.Verify(publicKey, []byte(strings.ToLower(expectedHash)), signature) {
		return errors.New("update package signature is invalid")
	}
	return nil
}

func download(ctx context.Context, url, target string) error {
	transport := &http.Transport{
		DialContext:           (&net.Dialer{Timeout: 3 * time.Second}).DialContext,
		TLSHandshakeTimeout:   3 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
	}
	client := &http.Client{Timeout: 5 * time.Minute, Transport: transport}
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return err
		}
		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
		} else if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			resp.Body.Close()
			return fmt.Errorf("download returned HTTP %d", resp.StatusCode)
		} else {
			file, openErr := os.OpenFile(target, os.O_WRONLY|os.O_TRUNC, 0o600)
			if openErr != nil {
				resp.Body.Close()
				return openErr
			}
			written, copyErr := io.Copy(file, io.LimitReader(resp.Body, (512<<20)+1))
			closeErr := file.Close()
			resp.Body.Close()
			if written > 512<<20 {
				return errors.New("update package exceeds 512 MiB")
			}
			if copyErr == nil && closeErr == nil {
				return nil
			}
			if copyErr != nil {
				lastErr = copyErr
			} else {
				lastErr = closeErr
			}
		}
		if attempt < 2 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Duration(500*(1<<attempt)) * time.Millisecond):
			}
		}
	}
	return lastErr
}

func extractZip(archive, target string) error {
	reader, err := zip.OpenReader(archive)
	if err != nil {
		return err
	}
	defer reader.Close()
	if err := os.MkdirAll(target, 0o755); err != nil {
		return err
	}
	cleanTarget := filepath.Clean(target) + string(os.PathSeparator)
	for _, entry := range reader.File {
		if entry.Mode()&os.ModeSymlink != 0 {
			return errors.New("update archive contains a symbolic link")
		}
		destination := filepath.Join(target, entry.Name)
		if !strings.HasPrefix(filepath.Clean(destination)+string(os.PathSeparator), cleanTarget) {
			return errors.New("unsafe path in update archive")
		}
		if entry.FileInfo().IsDir() {
			if err := os.MkdirAll(destination, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
			return err
		}
		source, err := entry.Open()
		if err != nil {
			return err
		}
		mode := entry.Mode()
		if mode == 0 {
			mode = 0o644
		}
		output, err := os.OpenFile(destination, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, mode)
		if err != nil {
			source.Close()
			return err
		}
		_, copyErr := io.Copy(output, source)
		output.Close()
		source.Close()
		if copyErr != nil {
			return copyErr
		}
	}
	return nil
}

func pruneVersions(root string, keep []string) error {
	allowed := make(map[string]bool, len(keep))
	for _, version := range keep {
		allowed[version] = true
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if !entry.IsDir() || allowed[entry.Name()] {
			continue
		}
		if err := os.RemoveAll(filepath.Join(root, entry.Name())); err != nil {
			return err
		}
	}
	return nil
}

var pluginAssets = []string{
	"plugin.json",
	"mcp.json",
	"capabilities.lock.json",
	"README.md",
	"skills",
}

func activateAssets(root, versionRoot string) error {
	stage, err := os.MkdirTemp(root, ".cxclaw-activate-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(stage)
	backup, err := os.MkdirTemp(root, ".cxclaw-backup-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(backup)
	for _, name := range pluginAssets {
		source := filepath.Join(versionRoot, name)
		if _, err := os.Lstat(source); err != nil {
			return fmt.Errorf("version is missing %s", name)
		}
		if err := copyTree(source, filepath.Join(stage, name)); err != nil {
			return err
		}
	}
	activated := make([]string, 0, len(pluginAssets))
	for _, name := range pluginAssets {
		current := filepath.Join(root, name)
		saved := filepath.Join(backup, name)
		if _, err := os.Lstat(current); err == nil {
			if err := os.Rename(current, saved); err != nil {
				restoreAssets(root, backup, activated)
				return err
			}
		} else if !os.IsNotExist(err) {
			restoreAssets(root, backup, activated)
			return err
		}
		if err := os.Rename(filepath.Join(stage, name), current); err != nil {
			if _, savedErr := os.Lstat(saved); savedErr == nil {
				_ = os.Rename(saved, current)
			}
			restoreAssets(root, backup, activated)
			return err
		}
		activated = append(activated, name)
	}
	return nil
}

func restoreAssets(root, backup string, activated []string) {
	for index := len(activated) - 1; index >= 0; index-- {
		name := activated[index]
		_ = os.RemoveAll(filepath.Join(root, name))
		_ = os.Rename(filepath.Join(backup, name), filepath.Join(root, name))
	}
}

func copyTree(source, target string) error {
	info, err := os.Lstat(source)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return errors.New("plugin assets may not contain symbolic links")
	}
	if !info.IsDir() {
		data, err := os.ReadFile(source)
		if err != nil {
			return err
		}
		return os.WriteFile(target, data, info.Mode().Perm())
	}
	if err := os.MkdirAll(target, info.Mode().Perm()); err != nil {
		return err
	}
	entries, err := os.ReadDir(source)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if err := copyTree(filepath.Join(source, entry.Name()), filepath.Join(target, entry.Name())); err != nil {
			return err
		}
	}
	return nil
}

func retainHistory(input []string, limit int) []string {
	seen := map[string]bool{}
	result := make([]string, 0, limit)
	for _, item := range input {
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		result = append(result, item)
		if len(result) == limit {
			break
		}
	}
	return result
}

func binaryName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}
