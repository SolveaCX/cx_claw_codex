package slsquery

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"

	"github.com/SolveaCX/cx_claw_codex/internal/api"
	"github.com/SolveaCX/cx_claw_codex/internal/config"
	sls "github.com/aliyun/aliyun-log-go-sdk"
)

type Credentials struct {
	AccessKeyID     string `json:"accessKeyId"`
	AccessKeySecret string `json:"accessKeySecret"`
	SecurityToken   string `json:"securityToken"`
	Expiration      string `json:"expiration"`
}

type Limits struct {
	MaxTimeRangeSeconds int64 `json:"maxTimeRangeSeconds"`
	MaxResults          int64 `json:"maxResults"`
	MaxConcurrency      int   `json:"maxConcurrency"`
	MaxMessageChars     int   `json:"maxMessageChars"`
}

type Session struct {
	Endpoint    string      `json:"endpoint"`
	Project     string      `json:"project"`
	Logstore    string      `json:"logstore"`
	Credentials Credentials `json:"credentials"`
	Limits      Limits      `json:"limits"`
}

type Query struct {
	From    int64  `json:"fromTime"`
	To      int64  `json:"toTime"`
	Query   string `json:"query"`
	Line    int64  `json:"line"`
	Offset  int64  `json:"offset"`
	Reverse bool   `json:"reverse"`
}

type Result struct {
	Count    int64               `json:"count"`
	Progress string              `json:"progress"`
	Logs     []map[string]string `json:"logs"`
}

var concurrency = struct {
	sync.Mutex
	active int
}{}

func Run(ctx context.Context, appSession *config.Session, query Query) (*Result, error) {
	var temporary Session
	if err := api.New(appSession).Do(ctx, http.MethodPost, "/codex/v1/sls/session", map[string]any{}, &temporary, true); err != nil {
		return nil, err
	}
	if query.From <= 0 || query.To <= 0 || query.To < query.From ||
		query.To-query.From > temporary.Limits.MaxTimeRangeSeconds {
		return nil, errors.New("SLS time range exceeds the server limit")
	}
	if temporary.Limits.MaxConcurrency <= 0 {
		return nil, errors.New("SLS concurrency is disabled by the server")
	}
	concurrency.Lock()
	if concurrency.active >= temporary.Limits.MaxConcurrency {
		concurrency.Unlock()
		return nil, errors.New("SLS concurrent query limit reached")
	}
	concurrency.active++
	concurrency.Unlock()
	defer func() {
		concurrency.Lock()
		concurrency.active--
		concurrency.Unlock()
	}()
	if query.Line <= 0 {
		query.Line = 50
	}
	if query.Line > temporary.Limits.MaxResults {
		query.Line = temporary.Limits.MaxResults
	}
	provider := sls.NewStaticCredentialsProvider(
		temporary.Credentials.AccessKeyID,
		temporary.Credentials.AccessKeySecret,
		temporary.Credentials.SecurityToken,
	)
	client := sls.CreateNormalInterfaceV2(temporary.Endpoint, provider)
	response, err := client.GetLogs(
		temporary.Project, temporary.Logstore, "", query.From, query.To,
		query.Query, query.Line, query.Offset, query.Reverse,
	)
	if err != nil {
		return nil, err
	}
	for _, log := range response.Logs {
		for key, value := range log {
			if temporary.Limits.MaxMessageChars > 0 && len(value) > temporary.Limits.MaxMessageChars {
				log[key] = value[:temporary.Limits.MaxMessageChars] + "<truncated>"
			}
			log[key] = strings.ToValidUTF8(log[key], "�")
		}
	}
	return &Result{Count: response.Count, Progress: response.Progress, Logs: response.Logs}, nil
}
