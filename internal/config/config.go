package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/zalando/go-keyring"
)

const (
	keyringService = "com.solvea.cxclaw"
	keyringUser    = "session"
)

type Tenant struct {
	AccountID     int64  `json:"accountId"`
	AccountCode   string `json:"accountCode"`
	AccountName   string `json:"accountName"`
	Environment   string `json:"environment"`
	Purpose       string `json:"purpose"`
	Context       string `json:"context,omitempty"`
	BusinessToken string `json:"businessToken,omitempty"`
	BusinessURL   string `json:"businessUrl,omitempty"`
	SLSURL        string `json:"slsUrl,omitempty"`
	ExpiresAt     int64  `json:"expiresAt"`
}

type IdempotencyRecord struct {
	RequestHash string `json:"requestHash"`
	CompletedAt int64  `json:"completedAt"`
}

type Session struct {
	ServerURL    string                       `json:"serverUrl"`
	AccessToken  string                       `json:"accessToken"`
	RefreshToken string                       `json:"refreshToken"`
	AccessExpiry int64                        `json:"accessExpiry"`
	EmployeeID   string                       `json:"employeeId"`
	Email        string                       `json:"email"`
	Channel      string                       `json:"channel"`
	Tenant       Tenant                       `json:"tenant"`
	Idempotency  map[string]IdempotencyRecord `json:"idempotency,omitempty"`
}

func Load() (*Session, error) {
	raw, err := keyring.Get(keyringService, keyringUser)
	if err != nil {
		return nil, err
	}
	var session Session
	if err := json.Unmarshal([]byte(raw), &session); err != nil {
		return nil, fmt.Errorf("decode credential: %w", err)
	}
	return &session, nil
}

func Save(session *Session) error {
	if session == nil || session.RefreshToken == "" {
		return errors.New("refusing to persist an empty session")
	}
	if runtime.GOOS == "linux" && os.Getenv("DBUS_SESSION_BUS_ADDRESS") == "" {
		return errors.New("Linux Secret Service is unavailable; persistent login is disabled")
	}
	raw, err := json.Marshal(session)
	if err != nil {
		return err
	}
	if err := keyring.Set(keyringService, keyringUser, string(raw)); err != nil {
		return fmt.Errorf("secure credential store: %w", err)
	}
	return nil
}

func Delete() error {
	err := keyring.Delete(keyringService, keyringUser)
	if errors.Is(err, keyring.ErrNotFound) {
		return nil
	}
	return err
}

func (s *Session) AccessValid() bool {
	return s != nil && s.AccessToken != "" && time.Now().Unix()+30 < s.AccessExpiry
}
