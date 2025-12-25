# Alpaca Operator Console Smoke Test

This document provides step-by-step smoke tests for the Alpaca operator console PowerShell script (`tools\alpaca.ps1`).

## Prerequisites

### PAPER Mode
Set the following environment variables:
```powershell
$env:ALPACA_PAPER_KEY_ID = "PK..."
$env:ALPACA_PAPER_SECRET_KEY = "your_paper_secret"
```

### LIVE Mode
Set the following environment variables:
```powershell
$env:ALPACA_LIVE_KEY_ID = "AK..."
$env:ALPACA_LIVE_SECRET_KEY = "your_live_secret"
```

---

## PAPER Mode Smoke Test

### 1. Check Account Status
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status
```
**Expected:** JSON response with account details (buying_power, equity, etc.)

### 2. Place Limit Buy Order
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Extended
```
**Expected:** JSON response with order details (order_id, status=accepted, etc.)

### 3. List Open Orders
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
```
**Expected:** JSON array containing the order placed in step 2

### 4. Cancel All Orders
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 cancel-all
```
**Expected:** JSON array of cancelled orders

### 5. Verify Orders Cleared
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
```
**Expected:** Empty JSON array `[]`

### 6. Check Positions
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions
```
**Expected:** JSON array of current positions (may be empty)

---

## LIVE Mode Read-Only Test

⚠️ **Note:** Read-only operations do NOT require `ALPACA_LIVE_ARM` to be set.

### 1. Check Live Account Status
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status -Mode live
```
**Expected:** JSON response with live account details

### 2. List Live Orders
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode live
```
**Expected:** JSON array of open orders (may be empty)

### 3. Check Live Positions
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions -Mode live
```
**Expected:** JSON array of current positions (may be empty)

---

## LIVE Mode Destructive Test (⚠️ CAUTION ⚠️)

⚠️ **WARNING:** These operations use REAL MONEY. Only proceed if you understand the risks.

### Prerequisites
Set the arming environment variable:
```powershell
$env:ALPACA_LIVE_ARM = "YES"
```

### Cancel All Live Orders
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 cancel-all -Mode live
```
**Expected:** JSON array of cancelled orders

### Place Live Order (Example - DO NOT RUN without understanding)
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Mode live -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Confirm "LIVE-SPY-1-buy"
```
**Expected:** JSON response with order details

---

## Safety Gate Tests

### Test 1: Missing Credentials
Unset credentials and verify error:
```powershell
Remove-Item Env:\ALPACA_PAPER_KEY_ID -ErrorAction SilentlyContinue
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status
```
**Expected:** Error message indicating missing credentials, exit code 1

### Test 2: LIVE Trading Without Arming
Ensure `ALPACA_LIVE_ARM` is NOT set:
```powershell
Remove-Item Env:\ALPACA_LIVE_ARM -ErrorAction SilentlyContinue
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Mode live -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Confirm "LIVE-SPY-1-buy"
```
**Expected:** Error message "LIVE trading blocked. Set $env:ALPACA_LIVE_ARM='YES' to arm live trading.", exit code 1

### Test 3: LIVE Trading Without Confirmation
Set arming but omit confirmation:
```powershell
$env:ALPACA_LIVE_ARM = "YES"
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Mode live -Symbol SPY -Qty 1 -Type limit -Limit 400.00
```
**Expected:** Error message with expected confirmation string, exit code 1

### Test 4: LIVE Trading With Wrong Confirmation
Set arming with wrong confirmation:
```powershell
$env:ALPACA_LIVE_ARM = "YES"
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Mode live -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Confirm "WRONG"
```
**Expected:** Error message showing expected confirmation format, exit code 1

### Test 5: Limit Order Without Price
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Symbol SPY -Qty 1 -Type limit
```
**Expected:** Error message "Limit orders require -Limit parameter", exit code 1

---

## Success Criteria

- ✅ All PAPER operations complete successfully
- ✅ All LIVE read-only operations complete successfully
- ✅ All safety gates block invalid operations with clear error messages
- ✅ Script returns exit code 0 on success, 1 on error
- ✅ JSON responses are well-formed and parseable
