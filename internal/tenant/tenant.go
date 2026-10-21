package tenant

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
)

type Summary struct {
	AccountID   int64  `json:"accountId"`
	AccountCode string `json:"accountCode"`
	AccountName string `json:"accountName"`
	Status      int    `json:"status"`
}

func Search(ctx context.Context, session *config.Session, query, environment string) ([]Summary, error) {
	environment, err := NormalizeEnvironment(environment)
	if err != nil {
		return nil, err
	}
	var response struct {
		Items []Summary `json:"items"`
	}
	err = api.New(session).Do(ctx, http.MethodPost, "/tenants/search", map[string]any{
		"query": query, "environment": environment,
	}, &response, false)
	return response.Items, err
}

func Use(ctx context.Context, session *config.Session, accountID int64, environment, purpose string) error {
	if purpose == "" {
		return errors.New("purpose is required")
	}
	environment, err := NormalizeEnvironment(environment)
	if err != nil {
		return err
	}
	var response struct {
		TenantContext          string  `json:"tenantContext"`
		ExpiresIn              int64   `json:"expiresIn"`
		BusinessToken          string  `json:"businessToken"`
		BusinessTokenExpiresAt int64   `json:"businessTokenExpiresAt"`
		Tenant                 Summary `json:"tenant"`
		Environment            string  `json:"environment"`
		Services               struct {
			BusinessURL string `json:"businessUrl"`
			SLSURL      string `json:"slsUrl"`
		} `json:"services"`
	}
	err = api.New(session).Do(ctx, http.MethodPost, "/tenant-contexts", map[string]any{
		"accountId": accountID, "environment": environment, "purpose": purpose,
	}, &response, false)
	if err != nil {
		return err
	}
	if response.BusinessToken == "" || response.Services.BusinessURL == "" {
		return errors.New("authorization server did not return a business token and service URL")
	}
	expiresAt := response.BusinessTokenExpiresAt
	if expiresAt == 0 {
		expiresAt = time.Now().Unix() + response.ExpiresIn
	}
	session.Tenant = config.Tenant{
		AccountID: response.Tenant.AccountID, AccountCode: response.Tenant.AccountCode,
		AccountName: response.Tenant.AccountName, Environment: response.Environment,
		Purpose: purpose, Context: response.TenantContext, BusinessToken: response.BusinessToken,
		BusinessURL: strings.TrimRight(response.Services.BusinessURL, "/"),
		SLSURL:      strings.TrimRight(response.Services.SLSURL, "/"), ExpiresAt: expiresAt,
	}
	return config.Save(session)
}

func Ensure(ctx context.Context, session *config.Session) error {
	if session == nil || session.Tenant.AccountID <= 0 {
		return errors.New("no tenant selected; run cxclawctl tenant use")
	}
	if session.Tenant.BusinessToken != "" && time.Now().Unix()+30 < session.Tenant.ExpiresAt {
		return nil
	}
	return Use(ctx, session, session.Tenant.AccountID, session.Tenant.Environment, session.Tenant.Purpose)
}

func NormalizeEnvironment(environment string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(environment)) {
	case "test", "staging":
		return "staging", nil
	case "prod", "production":
		return "prod", nil
	default:
		return "", fmt.Errorf("unsupported environment %q; use test/staging or prod", environment)
	}
}
