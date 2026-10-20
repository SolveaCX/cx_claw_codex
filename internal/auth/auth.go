package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

type deviceStartResponse struct {
	DeviceCode              string `json:"deviceCode"`
	UserCode                string `json:"userCode"`
	VerificationURIComplete string `json:"verificationUriComplete"`
	ExpiresIn               int64  `json:"expiresIn"`
	Interval                int    `json:"interval"`
}

type tokenResponse struct {
	AccessToken      string `json:"accessToken"`
	ExpiresIn        int64  `json:"expiresIn"`
	RefreshToken     string `json:"refreshToken"`
	RefreshExpiresIn int64  `json:"refreshExpiresIn"`
	Employee         struct {
		ID    string `json:"id"`
		Email string `json:"email"`
	} `json:"employee"`
}

func Login(ctx context.Context, serverURL, channel string, output io.Writer) (*config.Session, error) {
	session := &config.Session{ServerURL: strings.TrimRight(serverURL, "/"), Channel: channel}
	client := api.New(session)
	var start deviceStartResponse
	if err := client.Do(ctx, http.MethodPost, "/auth/device/start", map[string]any{
		"clientVersion": buildinfo.CLIVersion,
	}, &start, false); err != nil {
		return nil, err
	}
	fmt.Fprintf(output, "请在浏览器打开以下地址完成钉钉授权：\n%s\n设备码：%s\n", start.VerificationURIComplete, start.UserCode)
	interval := time.Duration(start.Interval) * time.Second
	if interval < 2*time.Second {
		interval = 2 * time.Second
	}
	deadline := time.Now().Add(time.Duration(start.ExpiresIn) * time.Second)
	for time.Now().Before(deadline) {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(interval):
		}
		status, data, err := postRaw(ctx, session.ServerURL+"/auth/device/token", map[string]any{
			"deviceCode": start.DeviceCode, "clientVersion": buildinfo.CLIVersion,
		})
		if err != nil {
			return nil, err
		}
		if status == http.StatusPreconditionRequired {
			continue
		}
		if status < 200 || status >= 300 {
			return nil, fmt.Errorf("device login failed: HTTP %d", status)
		}
		var tokens tokenResponse
		if err := json.Unmarshal(data, &tokens); err != nil {
			return nil, err
		}
		session.AccessToken = tokens.AccessToken
		session.RefreshToken = tokens.RefreshToken
		session.AccessExpiry = time.Now().Unix() + tokens.ExpiresIn
		session.EmployeeID = tokens.Employee.ID
		session.Email = tokens.Employee.Email
		if err := config.Save(session); err != nil {
			return nil, err
		}
		return session, nil
	}
	return nil, errors.New("device authorization expired")
}

func EnsureAccess(ctx context.Context, session *config.Session) error {
	if session.AccessValid() {
		return nil
	}
	if session.RefreshToken == "" {
		return errors.New("not logged in")
	}
	status, data, err := postRaw(ctx, strings.TrimRight(session.ServerURL, "/")+"/auth/refresh", map[string]any{
		"refreshToken": session.RefreshToken, "clientVersion": buildinfo.CLIVersion,
	})
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("refresh failed: HTTP %d", status)
	}
	var tokens tokenResponse
	if err := json.Unmarshal(data, &tokens); err != nil {
		return err
	}
	session.AccessToken = tokens.AccessToken
	session.RefreshToken = tokens.RefreshToken
	session.AccessExpiry = time.Now().Unix() + tokens.ExpiresIn
	return config.Save(session)
}

func Logout(ctx context.Context, session *config.Session) error {
	if session != nil && session.RefreshToken != "" {
		_, _, _ = postRaw(ctx, strings.TrimRight(session.ServerURL, "/")+"/auth/logout", map[string]any{
			"refreshToken": session.RefreshToken,
		})
	}
	return config.Delete()
}

func postRaw(ctx context.Context, url string, body any) (int, []byte, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return 0, nil, err
	}
	transport := &http.Transport{
		DialContext:           (&net.Dialer{Timeout: 3 * time.Second}).DialContext,
		TLSHandshakeTimeout:   3 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
	}
	client := &http.Client{Timeout: 30 * time.Second, Transport: transport}
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
		if err != nil {
			return 0, nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			if attempt < 2 {
				select {
				case <-ctx.Done():
					return 0, nil, ctx.Err()
				case <-time.After(time.Duration(200*(1<<attempt)) * time.Millisecond):
					continue
				}
			}
			return 0, nil, err
		}
		data, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		resp.Body.Close()
		if readErr != nil {
			return 0, nil, readErr
		}
		return resp.StatusCode, data, nil
	}
	return 0, nil, errors.New("request failed")
}
