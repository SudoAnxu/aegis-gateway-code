# Aegis Gateway

A production-style reverse-proxy gateway that enforces least-privilege policies on agent → tool calls and emits audit-grade telemetry.

## Features

- **Reverse-Proxy Gateway**: Sits between agents and tools, enforcing policies before forwarding requests
- **Policy-as-Code**: YAML-based policies with hot-reload support
- **Mock Tools**: Payments and Files services for testing
- **Telemetry**: OpenTelemetry spans and structured JSON audit logs
- **Hot Reload**: Policies automatically reload when files change

## Architecture

```
┌─────────────┐
│   Agent     │
└──────┬──────┘
       │ POST /tools/:tool/:action
       │ X-Agent-ID: finance-agent
       ▼
┌─────────────────┐
│ Aegis Gateway    │
│ - Policy Engine │
│ - Telemetry     │
└──────┬──────────┘
       │
       ├──► Payments Service (port 8081)
       └──► Files Service (port 8082)
```

## Quick Start

### Prerequisites

- Go 1.21 or later ([Install Go](https://go.dev/doc/install))
- Docker and Docker Compose (optional, for containerized deployment)

### Local Development

1. **Install dependencies**:
   ```bash
   go mod download
   ```

2. **Run the gateway**:
   ```bash
   go run cmd/aegis/main.go
   ```

   The gateway will start on port 8080, with payments service on 8081 and files service on 8082.

3. **Run the demo**:
   ```bash
   # Linux/Mac
   chmod +x scripts/demo.sh
   ./scripts/demo.sh

   # Windows
   .\scripts\demo.ps1
   ```

### Docker Deployment

1. **Build and run**:
   ```bash
   docker-compose up --build
   ```

2. **Run the demo** (same commands as above)

## API Reference

### Gateway Endpoint

**POST** `/tools/:tool/:action`

**Headers:**
- `X-Agent-ID` (required): The agent's identity
- `X-Parent-Agent` (optional): For future chain-of-calls support

**Request Body:** JSON (tool-specific)

**Responses:**
- `200 OK`: Tool response passthrough
- `403 Forbidden`: Policy violation
  ```json
  {
    "error": "PolicyViolation",
    "reason": "Amount exceeds max_amount=5000"
  }
  ```

### Payments Tool

**POST** `/create`
```json
{
  "amount": 3000,
  "currency": "USD",
  "vendor_id": "V123",
  "memo": "Optional memo"
}
```

**POST** `/refund`
```json
{
  "payment_id": "PAY-1",
  "reason": "Optional reason"
}
```

### Files Tool

**POST** `/read`
```json
{
  "path": "/hr-docs/employee1.txt"
}
```

**POST** `/write`
```json
{
  "path": "/hr-docs/employee1.txt",
  "content": "File content"
}
```

## Policy Configuration

Policies are defined in YAML files in the `./policies/` directory. They support hot-reload - changes are automatically picked up without restarting the gateway.

### Policy Schema

```yaml
version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        actions: [create, refund]
        conditions:
          max_amount: 5000
          currencies: [USD, EUR]
  - id: hr-agent
    allow:
      - tool: files
        actions: [read]
        conditions:
          folder_prefix: "/hr-docs/"
```

### Supported Conditions

- `max_amount`: Maximum allowed payment amount (numeric)
- `currencies`: Allowed currency codes (array of strings)
- `folder_prefix`: Required path prefix for file operations (string)

## Demo Test Cases

The demo script demonstrates four scenarios:

1. **Blocked high-value payment**: Agent tries to create a payment exceeding the max_amount limit
2. **Allowed payment within limits**: Agent creates a payment within allowed limits
3. **Allowed HR file read**: Agent reads a file within the allowed `/hr-docs/` prefix
4. **Blocked HR file read**: Agent tries to read a file outside the allowed prefix

## Telemetry

### OpenTelemetry

The gateway emits OpenTelemetry spans with the following attributes:
- `agent.id`: Agent identifier
- `tool.name`: Tool name
- `tool.action`: Action being performed
- `decision.allow`: Whether the request was allowed (boolean)
- `params.hash`: SHA-256 hash of request parameters (for privacy)
- `latency.ms`: Request latency in milliseconds
- `trace.id`: OpenTelemetry trace ID

### Audit Logs

Structured JSON logs are written to:
- `stdout`
- `./logs/aegis.log`

Each log entry includes all span attributes plus a human-readable reason for denied requests.

## Project Structure

```
aegis-gateway/
├── cmd/
│   ├── aegis/          # Main gateway application
│   ├── payments/       # Standalone payments service
│   └── files/          # Standalone files service
├── internal/
│   ├── gateway/        # Gateway core logic
│   ├── policy/         # Policy engine with hot-reload
│   └── adapters/       # Tool adapters (payments, files)
├── pkg/
│   └── telemetry/      # OpenTelemetry and logging
├── policies/           # Policy YAML files
├── scripts/            # Demo scripts
├── deploy/             # Deployment configurations
└── logs/               # Log output directory
```

## Security Features

- **Input Validation**: All requests are validated before processing
- **Parameter Hashing**: Request parameters are hashed (SHA-256) before logging to avoid PII exposure
- **Safe Error Messages**: Error messages don't leak sensitive information
- **Schema Validation**: Policies are validated on load
- **Graceful Error Handling**: Invalid policies don't crash the service

## Hot Reload

Policies are automatically reloaded when files in the `./policies/` directory change. The gateway watches for:
- File creation
- File modification
- File deletion

Invalid policy files are logged but don't crash the service, allowing other valid policies to continue working.

## Building

```bash
go build -o aegis ./cmd/aegis
```

## Development

### Running Locally

```bash
go run cmd/aegis/main.go
```

### Using Docker

```bash
docker-compose up --build
```

## Extending

### Adding New Tools

1. Create a new adapter in `internal/adapters/<toolname>/`
2. Add the tool URL to `internal/gateway/gateway.go` in the `toolURLs` map
3. Start the tool service (or integrate it into the main process)

### Adding New Policy Conditions

1. Extend the condition checking logic in `internal/policy/policy.go` in the `checkConditions` method
2. Update policy schema documentation

## License

This project is created for the Aegis Gateway coding test.
