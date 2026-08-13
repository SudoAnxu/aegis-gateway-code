# Controlled tool fixtures

These fixtures are experiment-only stand-ins for the missing `cmd/payments` and `cmd/files` services. They are not part of the Aegis gateway implementation.

## Start the three services

From the repository root, use three terminals:

```bash
python research/fixtures/tool_services.py payments --port 8081
python research/fixtures/tool_services.py files --port 8082
python research/fixtures/tool_services.py rbac --port 8090
```

The B1 RBAC proxy forwards authorized calls to the two controlled tool fixtures. Its authorization matrix is intentionally coarse:

- `finance-agent -> payments -> create, refund`
- `hr-agent -> files -> read`

It does not inspect amount, currency, or file path. Those constraints are reserved for B2/Aegis.

## Smoke tests

Payments:

```bash
curl -s -X POST http://localhost:8081/create -H 'Content-Type: application/json' -d '{"amount":1250,"currency":"USD"}'
```

Files:

```bash
curl -s -X POST http://localhost:8082/read -H 'Content-Type: application/json' -d '{"path":"/hr-docs/policies/leave.txt"}'
```

B1 authorized:

```bash
curl -s -X POST http://localhost:8090/tools/payments/create -H 'Content-Type: application/json' -H 'X-Agent-ID: finance-agent' -d '{"amount":7500,"currency":"USD"}'
```

The last request should be forwarded and return `ALLOW`, because B1 deliberately does not enforce parameter-level constraints. This is a key construct-validity check for the B1 baseline.

B1 unauthorized action:

```bash
curl -i -s -X POST http://localhost:8090/tools/payments/delete -H 'Content-Type: application/json' -H 'X-Agent-ID: finance-agent' -d '{}'
```

This should return HTTP 403 from the RBAC proxy without reaching a tool fixture.
