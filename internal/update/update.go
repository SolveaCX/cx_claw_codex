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

	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

var safeVersion = regexp.MustCompile(`^[0-9A-Za-z._-]{1,64}$`)

const githubReleasesURL = "https://api.github.com/repos/SolveaCX/cx_claw_codex/releases"

type CheckResponse struct {
	UpdateAvailable bool   `json:"updateAvailable"`
	Channel         string `json:"channel"`
	Version         string `json:"version"`
	SHA256          string `json:"sha256"`
	Signature       string `json:"signature"`
	DownloadURL     string `json:"downloadUrl"`
}

type githubRelease struct {
	TagName    string        `json:"tag_name"`
	Draft      bool          `json:"draft"`
	Prerelease bool          `json:"prerelease"`
	Assets     []githubAsset `json:"assets"`
}
type githubAsset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
}

type releaseManifest struct {
	Version string `json:"version"`
	Channel string `json:"channel"`
	Assets  map[string]struct {
		File      string `json:"file"`
		SHA256    string `json:"sha256"`
		Signature string `json:"signature"`
	} `json:"assets"`
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
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".codex", "cxclaw"), nil
}

func Check(ctx context.Context, session *config.Session) (*CheckResponse, error) {
	channel := "stable"
	if session != nil && session.Channel != "" {
		channel = session.Channel
	}
	release, asset, err := latestRelease(ctx, channel)
	if err != nil {
		return nil, err
	}
	version := strings.TrimPrefix(release.TagName, "v")
	if version == buildinfo.PluginVersion {
		return &CheckResponse{Channel: channel, Version: version}, nil
	}
	assetName := runtimeAssetName(version)
	if asset.Name != assetName {
		return nil, fmt.Errorf("GitHub release %s has no runtime asset %s", release.TagName, assetName)
	}
	manifestAsset := findAsset(release, "cxclaw-release.json")
	if manifestAsset.BrowserDownloadURL == "" {
		return nil, errors.New("GitHub release metadata is missing")
	}
	signatureAsset := findAsset(release, "cxclaw-release.sig")
	if signatureAsset.BrowserDownloadURL == "" {
		return nil, errors.New("GitHub release manifest signature is missing")
	}
	manifest, err := fetchManifest(ctx, manifestAsset.BrowserDownloadURL, signatureAsset.BrowserDownloadURL)
	if err != nil {
		return nil, err
	}
	entry, ok := manifest.Assets[assetName]
	if !ok || entry.SHA256 == "" || entry.Signature == "" {
		return nil, fmt.Errorf("GitHub release metadata is missing %s integrity data", assetName)
	}
	return &CheckResponse{UpdateAvailable: true, Channel: channel, Version: version, SHA256: entry.SHA256, Signature: entry.Signature, DownloadURL: asset.BrowserDownloadURL}, nil
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
	if previous != "" {
		if output, err := exec.CommandContext(ctx, "codex", "plugin", "marketplace", "upgrade", "cxclaw").CombinedOutput(); err != nil {
			_ = activateAssets(root, filepath.Join(root, "versions", previous))
			_ = os.RemoveAll(target)
			return "", fmt.Errorf("upgrade Git marketplace: %w: %s", err, strings.TrimSpace(string(output)))
		}
	}
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

func latestRelease(ctx context.Context, channel string) (githubRelease, githubAsset, error) {
	if channel != "stable" && channel != "canary" && channel != "dev" {
		return githubRelease{}, githubAsset{}, errors.New("invalid update channel")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, githubReleasesURL, nil)
	if err != nil {
		return githubRelease{}, githubAsset{}, err
	}
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("User-Agent", "cxclawctl/"+buildinfo.CLIVersion)
	response, err := (&http.Client{Timeout: 30 * time.Second}).Do(request)
	if err != nil {
		return githubRelease{}, githubAsset{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return githubRelease{}, githubAsset{}, fmt.Errorf("GitHub releases returned HTTP %d", response.StatusCode)
	}
	var releases []githubRelease
	if err := json.NewDecoder(io.LimitReader(response.Body, 4<<20)).Decode(&releases); err != nil {
		return githubRelease{}, githubAsset{}, err
	}
	for _, release := range releases {
		if release.Draft || !channelMatches(release.TagName, channel) {
			continue
		}
		for _, asset := range release.Assets {
			if asset.Name == runtimeAssetName(strings.TrimPrefix(release.TagName, "v")) {
				return release, asset, nil
			}
		}
	}
	return githubRelease{}, githubAsset{}, fmt.Errorf("no %s release is available", channel)
}

func findAsset(release githubRelease, name string) githubAsset {
	for _, asset := range release.Assets {
		if asset.Name == name {
			return asset
		}
	}
	return githubAsset{}
}

func fetchManifest(ctx context.Context, url, signatureURL string) (releaseManifest, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return releaseManifest{}, err
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", "cxclawctl/"+buildinfo.CLIVersion)
	response, err := (&http.Client{Timeout: 30 * time.Second}).Do(request)
	if err != nil {
		return releaseManifest{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return releaseManifest{}, fmt.Errorf("GitHub release metadata returned HTTP %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if err != nil {
		return releaseManifest{}, err
	}
	sigRequest, err := http.NewRequestWithContext(ctx, http.MethodGet, signatureURL, nil)
	if err != nil {
		return releaseManifest{}, err
	}
	sigRequest.Header.Set("User-Agent", "cxclawctl/"+buildinfo.CLIVersion)
	sigResponse, err := (&http.Client{Timeout: 30 * time.Second}).Do(sigRequest)
	if err != nil {
		return releaseManifest{}, err
	}
	defer sigResponse.Body.Close()
	if sigResponse.StatusCode != http.StatusOK {
		return releaseManifest{}, fmt.Errorf("GitHub release signature returned HTTP %d", sigResponse.StatusCode)
	}
	sigText, err := io.ReadAll(io.LimitReader(sigResponse.Body, 16<<10))
	if err != nil {
		return releaseManifest{}, err
	}
	digest := sha256.Sum256(body)
	if err := verifyDigestSignature(hex.EncodeToString(digest[:]), strings.TrimSpace(string(sigText))); err != nil {
		return releaseManifest{}, fmt.Errorf("release metadata signature invalid: %w", err)
	}
	var manifest releaseManifest
	if err := json.Unmarshal(body, &manifest); err != nil {
		return releaseManifest{}, err
	}
	return manifest, nil
}

func channelMatches(tag, channel string) bool {
	version := strings.TrimPrefix(tag, "v")
	switch channel {
	case "stable":
		return !strings.Contains(version, "-")
	case "canary":
		return strings.Contains(version, "-canary.")
	case "dev":
		return strings.Contains(version, "-dev.")
	}
	return false
}

func runtimeAssetName(version string) string {
	return fmt.Sprintf("cxclaw-runtime-%s-%s-%s.zip", version, runtime.GOOS, runtime.GOARCH)
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
	_ = exec.Command("codex", "plugin", "marketplace", "remove", "cxclaw").Run()
	if output, err := exec.Command("codex", "plugin", "marketplace", "add", "SolveaCX/cx_claw_codex", "--ref", "v"+pointer.Current).CombinedOutput(); err != nil {
		return "", fmt.Errorf("runtime rolled back but marketplace pin failed: %w: %s", err, strings.TrimSpace(string(output)))
	}
	if err := os.WriteFile(filepath.Join(root, "updates.paused"), []byte("rollback\n"), 0o600); err != nil {
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
	return verifyDigestSignature(actual, signatureBase64)
}

func verifyDigestSignature(digest, signatureBase64 string) error {
	publicKey, err := base64.StdEncoding.DecodeString(buildinfo.UpdatePublicKeyBase64)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return errors.New("update verification public key is not configured")
	}
	signature, err := base64.StdEncoding.DecodeString(signatureBase64)
	if err != nil || !ed25519.Verify(publicKey, []byte(strings.ToLower(digest)), signature) {
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
	".codex-plugin",
	"capabilities.lock.json",
	"README.md",
	"requirements-cli.txt",
	"runtime",
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
