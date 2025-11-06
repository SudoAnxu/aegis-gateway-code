#!/bin/bash

# Aegis Gateway Demo Script
# This script demonstrates the four test cases:
# 1. Blocked high-value payment
# 2. Allowed payment within limits
# 3. Allowed HR file read inside /hr-docs/
# 4. Blocked HR file read outside /hr-docs/

echo "=========================================="
echo "Aegis Gateway Demo"
echo "=========================================="
echo ""

GATEWAY_URL="http://localhost:8080"

# Test 1: Blocked high-value payment
echo "Test 1: Blocked high-value payment (amount exceeds max_amount=5000)"
echo "-------------------------------------------------------------------"
curl -s -H "X-Agent-ID: finance-agent" \
  -H "Content-Type: application/json" \
  -X POST "$GATEWAY_URL/tools/payments/create" \
  -d '{"amount":50000,"currency":"USD","vendor_id":"V99"}'
echo ""
echo ""

# Test 2: Allowed payment within limits
echo "Test 2: Allowed payment within limits"
echo "--------------------------------------"
curl -s -H "X-Agent-ID: finance-agent" \
  -H "Content-Type: application/json" \
  -X POST "$GATEWAY_URL/tools/payments/create" \
  -d '{"amount":3000,"currency":"USD","vendor_id":"V123","memo":"Test payment"}'
echo ""
echo ""

# Test 3: Allowed HR file read inside /hr-docs/
echo "Test 3: Allowed HR file read inside /hr-docs/"
echo "----------------------------------------------"
# First, write a file to the files service directly (or use gateway if write is allowed)
# For demo, we'll assume the file exists or create it via direct service call
curl -s -H "Content-Type: application/json" \
  -X POST "http://localhost:8082/write" \
  -d '{"path":"/hr-docs/employee1.txt","content":"Employee data"}'
echo ""
echo "Now reading via gateway..."
curl -s -H "X-Agent-ID: hr-agent" \
  -H "Content-Type: application/json" \
  -X POST "$GATEWAY_URL/tools/files/read" \
  -d '{"path":"/hr-docs/employee1.txt"}'
echo ""
echo ""

# Test 4: Blocked HR file read outside /hr-docs/
echo "Test 4: Blocked HR file read outside /hr-docs/"
echo "-----------------------------------------------"
# First create a file outside the allowed prefix
curl -s -H "Content-Type: application/json" \
  -X POST "http://localhost:8082/write" \
  -d '{"path":"/legal/contract.docx","content":"Legal document"}'
echo ""
echo "Now trying to read via gateway (should be blocked)..."
curl -s -H "X-Agent-ID: hr-agent" \
  -H "Content-Type: application/json" \
  -X POST "$GATEWAY_URL/tools/files/read" \
  -d '{"path":"/legal/contract.docx"}'
echo ""
echo ""

echo "=========================================="
echo "Demo complete!"
echo "=========================================="

