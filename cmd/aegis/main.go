package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"aegis-gateway/internal/gateway"
	"aegis-gateway/internal/identity"
	"aegis-gateway/internal/policy"
	"aegis-gateway/pkg/telemetry"
)

func main() {
	gatewayPort := flag.String("gateway-port", "8080", "HTTP port for the Aegis gateway")
	paymentsPort := flag.String("payments-port", "8081", "Port used by the payments tool service")
	filesPort := flag.String("files-port", "8082", "Port used by the files tool service")
	policiesDir := flag.String("policies-dir", "./policies", "Directory containing policy YAML files")
	logDir := flag.String("log-dir", "./logs", "Directory for Aegis logs")
	flag.Parse()

	// The gateway currently uses the conventional local tool-service ports
	// directly. Keep these flags for compatibility with the Docker interface
	// and make accidental mismatches visible at startup.
	if *paymentsPort != "8081" || *filesPort != "8082" {
		log.Printf("WARNING: gateway forwarding currently targets payments=:8081 and files=:8082; configured payments=%s files=%s", *paymentsPort, *filesPort)
	}

	if _, err := os.Stat(*policiesDir); err != nil {
		log.Fatalf("policies directory unavailable: %v", err)
	}

	policyEngine, err := policy.NewPolicyEngine(*policiesDir)
	if err != nil {
		log.Fatalf("failed to initialize policy engine: %v", err)
	}

	telemetryClient, err := telemetry.NewTelemetry("aegis-gateway", *logDir)
	if err != nil {
		log.Fatalf("failed to initialize telemetry: %v", err)
	}
	defer func() {
		if err := telemetryClient.Close(); err != nil {
			log.Printf("failed to close telemetry: %v", err)
		}
	}()

	// Identity binding: test-mode uses static token map, production uses HMAC.
	// The gateway NEVER trusts the model-claimed identity for authorization.
	var auth *identity.Authenticator
	if os.Getenv("AEGIS_EVALUATION_MODE") == "1" {
		auth = identity.NewTestAuthenticator(identity.StandardTestAgents())
		fmt.Println("Identity binding: test mode (X-Test-Auth-Token)")
	} else if hmacSecret := os.Getenv("AEGIS_HMAC_SECRET"); hmacSecret != "" {
		auth = identity.NewAuthenticator([]byte(hmacSecret))
		fmt.Println("Identity binding: HMAC mode")
	} else {
		// Production default: fail closed on missing authentication
		auth = identity.NewAuthenticator([]byte{})
		fmt.Println("Identity binding: HMAC mode (no secret configured — all unauthenticated requests will be rejected)")
	}

	g := gateway.NewGatewayWithAuth(policyEngine, telemetryClient, auth)

	fmt.Printf("Aegis Gateway starting on :%s (policies=%s)\n", *gatewayPort, *policiesDir)
	if err := g.StartServer(*gatewayPort); err != nil {
		log.Fatalf("gateway server stopped: %v", err)
	}
}
