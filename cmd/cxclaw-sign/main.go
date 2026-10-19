package main

import (
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"strings"
)

func main() {
	if len(os.Args) != 2 {
		fatal(errors.New("usage: cxclaw-sign <sha256-hex>"))
	}
	encoded := os.Getenv("CXCLAW_ED25519_PRIVATE_KEY_BASE64")
	key, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		fatal(fmt.Errorf("decode signing key: %w", err))
	}
	if len(key) == ed25519.SeedSize {
		key = ed25519.NewKeyFromSeed(key)
	}
	if len(key) != ed25519.PrivateKeySize {
		fatal(errors.New("signing key must be an Ed25519 seed or private key"))
	}
	hash := strings.ToLower(strings.TrimSpace(os.Args[1]))
	signature := ed25519.Sign(ed25519.PrivateKey(key), []byte(hash))
	fmt.Println(base64.StdEncoding.EncodeToString(signature))
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
