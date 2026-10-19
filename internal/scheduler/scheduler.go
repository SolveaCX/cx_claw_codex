package scheduler

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

func Install(executable string) error {
	switch runtime.GOOS {
	case "darwin":
		return installLaunchAgent(executable)
	case "windows":
		return installTaskScheduler(executable)
	case "linux":
		return installSystemd(executable)
	default:
		return fmt.Errorf("automatic updates are unsupported on %s", runtime.GOOS)
	}
}

func installLaunchAgent(executable string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	dir := filepath.Join(home, "Library", "LaunchAgents")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	var escaped bytes.Buffer
	if err := xml.EscapeText(&escaped, []byte(executable)); err != nil {
		return err
	}
	content := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.solvea.cxclaw.update</string>
<key>ProgramArguments</key><array><string>%s</string><string>update</string><string>--scheduled</string></array>
<key>StartInterval</key><integer>21600</integer>
<key>RunAtLoad</key><true/>
</dict></plist>`, escaped.String())
	path := filepath.Join(dir, "com.solvea.cxclaw.update.plist")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		return err
	}
	_ = exec.Command("launchctl", "unload", path).Run()
	return exec.Command("launchctl", "load", path).Run()
}

func installTaskScheduler(executable string) error {
	command := fmt.Sprintf("\"%s\" update --scheduled", executable)
	return exec.Command(
		"schtasks", "/Create", "/F", "/SC", "HOURLY", "/MO", "6",
		"/TN", "Solvea CXClaw Update", "/TR", command,
	).Run()
}

func installSystemd(executable string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	dir := filepath.Join(home, ".config", "systemd", "user")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	service := fmt.Sprintf("[Unit]\nDescription=Update Solvea CXClaw\n[Service]\nType=oneshot\nExecStart=%s update --scheduled\n", quoteSystemd(executable))
	timer := "[Unit]\nDescription=Check Solvea CXClaw updates\n[Timer]\nOnBootSec=5m\nOnUnitActiveSec=6h\nRandomizedDelaySec=30m\nPersistent=true\n[Install]\nWantedBy=timers.target\n"
	if err := os.WriteFile(filepath.Join(dir, "cxclaw-update.service"), []byte(service), 0o600); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(dir, "cxclaw-update.timer"), []byte(timer), 0o600); err != nil {
		return err
	}
	if err := exec.Command("systemctl", "--user", "daemon-reload").Run(); err != nil {
		return err
	}
	return exec.Command("systemctl", "--user", "enable", "--now", "cxclaw-update.timer").Run()
}

func quoteSystemd(value string) string {
	return `"` + strings.NewReplacer(`\`, `\\`, `"`, `\"`).Replace(value) + `"`
}
