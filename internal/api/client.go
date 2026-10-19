package api

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

	"github.com/SolveaCX/cx_claw_codex/internal/buildinfo"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

type Client struct {
	HTTP    *http.Client
	Session *config.Session
}

func New(session *config.Session) *Client {
	transport := &http.Transport{
		DialContext:           (&net.Dialer{Timeout: 3 * time.Second}).DialContext,
		TLSHandshakeTimeout:   3 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
	}
	return &Client{HTTP: &http.Client{Timeout: 30 * time.Second, Transport: transport}, Session: session}
}

func (c *Client) Do(ctx context.Context, method, path string, body any, out any, withTenant bool) error {
	if c.Session == nil {
		return errors.New("not logged in")
	}
	var payload []byte
	var err error
	if body != nil {
		payload, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	url := strings.TrimRight(c.Session.ServerURL, "/") + path
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, method, url, bytes.NewReader(payload))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		if c.Session.AccessToken != "" {
			req.Header.Set("Authorization", "Bearer "+c.Session.AccessToken)
		}
		if withTenant {
			if c.Session.Tenant.Context == "" {
				return errors.New("no tenant selected; run cxclawctl tenant use")
			}
			req.Header.Set("X-CXClaw-Tenant-Context", c.Session.Tenant.Context)
		}
		req.Header.Set("X-CXClaw-Client-Version", buildinfo.CLIVersion)
		resp, err := c.HTTP.Do(req)
		if err != nil {
			if attempt < 2 {
				time.Sleep(time.Duration(200*(1<<attempt)) * time.Millisecond)
				continue
			}
			return err
		}
		data, readErr := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
		resp.Body.Close()
		if readErr != nil {
			return readErr
		}
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return fmt.Errorf("server returned %d: %s", resp.StatusCode, strings.TrimSpace(string(data)))
		}
		if out != nil && len(data) > 0 {
			if err := json.Unmarshal(data, out); err != nil {
				return fmt.Errorf("decode server response: %w", err)
			}
		}
		return nil
	}
	return errors.New("request failed")
}
