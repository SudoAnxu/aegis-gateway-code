# Aegis Gateway Demo Script (PowerShell)
# This script demonstrates the four test cases

Write-Host "=========================================="
Write-Host "Aegis Gateway Demo"
Write-Host "=========================================="
Write-Host ""

$GATEWAY_URL = "http://localhost:8080"

# Test 1: Blocked high-value payment
Write-Host "Test 1: Blocked high-value payment (amount exceeds max_amount=5000)"
Write-Host "-------------------------------------------------------------------"
Invoke-RestMethod -Uri "$GATEWAY_URL/tools/payments/create" `
  -Method Post `
  -Headers @{"X-Agent-ID"="finance-agent"; "Content-Type"="application/json"} `
  -Body '{"amount":50000,"currency":"USD","vendor_id":"V99"}' `
  -ErrorAction SilentlyContinue
Write-Host ""

# Test 2: Allowed payment within limits
Write-Host "Test 2: Allowed payment within limits"
Write-Host "--------------------------------------"
Invoke-RestMethod -Uri "$GATEWAY_URL/tools/payments/create" `
  -Method Post `
  -Headers @{"X-Agent-ID"="finance-agent"; "Content-Type"="application/json"} `
  -Body '{"amount":3000,"currency":"USD","vendor_id":"V123","memo":"Test payment"}'
Write-Host ""

# Test 3: Allowed HR file read inside /hr-docs/
Write-Host "Test 3: Allowed HR file read inside /hr-docs/"
Write-Host "----------------------------------------------"
Invoke-RestMethod -Uri "http://localhost:8082/write" `
  -Method Post `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"path":"/hr-docs/employee1.txt","content":"Employee data"}'
Write-Host "Now reading via gateway..."
Invoke-RestMethod -Uri "$GATEWAY_URL/tools/files/read" `
  -Method Post `
  -Headers @{"X-Agent-ID"="hr-agent"; "Content-Type"="application/json"} `
  -Body '{"path":"/hr-docs/employee1.txt"}'
Write-Host ""

# Test 4: Blocked HR file read outside /hr-docs/
Write-Host "Test 4: Blocked HR file read outside /hr-docs/"
Write-Host "-----------------------------------------------"
Invoke-RestMethod -Uri "http://localhost:8082/write" `
  -Method Post `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"path":"/legal/contract.docx","content":"Legal document"}'
Write-Host "Now trying to read via gateway (should be blocked)..."
try {
  Invoke-RestMethod -Uri "$GATEWAY_URL/tools/files/read" `
    -Method Post `
    -Headers @{"X-Agent-ID"="hr-agent"; "Content-Type"="application/json"} `
    -Body '{"path":"/legal/contract.docx"}'
} catch {
  Write-Host $_.Exception.Message
}
Write-Host ""

Write-Host "=========================================="
Write-Host "Demo complete!"
Write-Host "=========================================="

