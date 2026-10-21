package business

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

var readOnlyPrefixes = []string{"get-", "list-", "query-", "report-", "resolve-", "download-"}

func IsWrite(command string) bool {
	for _, prefix := range readOnlyPrefixes {
		if strings.HasPrefix(command, prefix) {
			return false
		}
	}
	return true
}

func RequestHash(command string, args []string) (string, error) {
	hash := sha256.New()
	encoded, _ := json.Marshal(map[string]any{"command": command, "args": args})
	_, _ = hash.Write(encoded)
	for index, arg := range args {
		if arg != "--data-file" || index+1 >= len(args) {
			continue
		}
		data, err := os.ReadFile(args[index+1])
		if err != nil {
			return "", fmt.Errorf("read data file for confirmation: %w", err)
		}
		_, _ = hash.Write(data)
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func ConfirmationToken(secret, requestHash string, now time.Time) string {
	expiresAt := now.Add(5 * time.Minute).Unix()
	payload := requestHash + ":" + strconv.FormatInt(expiresAt, 10)
	signature := hmac.New(sha256.New, []byte(secret))
	_, _ = signature.Write([]byte(payload))
	return base64.RawURLEncoding.EncodeToString([]byte(payload)) + "." +
		base64.RawURLEncoding.EncodeToString(signature.Sum(nil))
}

func VerifyConfirmation(secret, token, requestHash string, now time.Time) error {
	parts := strings.Split(token, ".")
	if len(parts) != 2 {
		return errors.New("invalid confirmation token")
	}
	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return errors.New("invalid confirmation token")
	}
	signatureBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return errors.New("invalid confirmation token")
	}
	payload := string(payloadBytes)
	payloadParts := strings.Split(payload, ":")
	if len(payloadParts) != 2 || payloadParts[0] != requestHash {
		return errors.New("confirmation token does not match the request")
	}
	expiresAt, err := strconv.ParseInt(payloadParts[1], 10, 64)
	if err != nil || expiresAt <= now.Unix() {
		return errors.New("confirmation token expired")
	}
	expected := hmac.New(sha256.New, []byte(secret))
	_, _ = expected.Write(payloadBytes)
	if !hmac.Equal(expected.Sum(nil), signatureBytes) {
		return errors.New("invalid confirmation token")
	}
	return nil
}
