package tenant

import (
	"context"
	"errors"
	"net/http"
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
	var response struct {
		Items []Summary `json:"items"`
	}
	err := api.New(session).Do(ctx, http.MethodPost, "/tenants/search", map[string]any{
		"query": query, "environment": environment,
	}, &response, false)
	return response.Items, err
}

func Use(ctx context.Context, session *config.Session, accountID int64, environment, purpose string) error {
	if purpose == "" {
		return errors.New("purpose is required")
	}
	var response struct {
		TenantContext string  `json:"tenantContext"`
		ExpiresIn     int64   `json:"expiresIn"`
		Tenant        Summary `json:"tenant"`
		Environment   string  `json:"environment"`
	}
	err := api.New(session).Do(ctx, http.MethodPost, "/tenant-contexts", map[string]any{
		"accountId": accountID, "environment": environment, "purpose": purpose,
	}, &response, false)
	if err != nil {
		return err
	}
	session.Tenant = config.Tenant{
		AccountID: response.Tenant.AccountID, AccountCode: response.Tenant.AccountCode,
		AccountName: response.Tenant.AccountName, Environment: response.Environment,
		Purpose: purpose, Context: response.TenantContext, ExpiresAt: time.Now().Unix() + response.ExpiresIn,
	}
	return config.Save(session)
}
