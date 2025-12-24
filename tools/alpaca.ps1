#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Alpaca operator console - paper-first, live-gated
.DESCRIPTION
    Safe-by-default PowerShell script for Alpaca trading operations.
    PAPER mode is default. LIVE mode requires strong safety gates.
#>

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet('status', 'positions', 'orders', 'cancel-all', 'buy', 'sell')]
    [string]$Action,

    [Parameter()]
    [ValidateSet('paper', 'live')]
    [string]$Mode = 'paper',

    # Buy/Sell parameters
    [Parameter()]
    [string]$Symbol = 'SPY',

    [Parameter()]
    [int]$Qty = 1,

    [Parameter()]
    [ValidateSet('limit', 'market')]
    [string]$Type = 'limit',

    [Parameter()]
    [string]$Limit = '',

    [Parameter()]
    [ValidateSet('day', 'gtc', 'ioc', 'fok')]
    [string]$Tif = 'day',

    [Parameter()]
    [switch]$Extended,

    [Parameter()]
    [string]$Confirm = ''
)

# Determine base URL and credentials based on mode
if ($Mode -eq 'paper') {
    $ApiKey = $env:ALPACA_PAPER_KEY_ID
    $SecretKey = $env:ALPACA_PAPER_SECRET_KEY
    $BaseUrl = if ($env:ALPACA_BASE_URL) { $env:ALPACA_BASE_URL } else { 'https://paper-api.alpaca.markets' }
} else {
    $ApiKey = $env:ALPACA_LIVE_KEY_ID
    $SecretKey = $env:ALPACA_LIVE_SECRET_KEY
    $BaseUrl = if ($env:ALPACA_BASE_URL) { $env:ALPACA_BASE_URL } else { 'https://api.alpaca.markets' }
}

# Validate credentials
if ([string]::IsNullOrWhiteSpace($ApiKey) -or [string]::IsNullOrWhiteSpace($SecretKey)) {
    if ($Mode -eq 'paper') {
        Write-Error "ERROR: Paper mode requires credentials. Set environment variables:`n  ALPACA_PAPER_KEY_ID`n  ALPACA_PAPER_SECRET_KEY"
    } else {
        Write-Error "ERROR: Live mode requires credentials. Set environment variables:`n  ALPACA_LIVE_KEY_ID`n  ALPACA_LIVE_SECRET_KEY"
    }
    exit 1
}

# Determine if action is destructive/trading
$IsReadOnly = $Action -in @('status', 'positions', 'orders')
$IsTrading = $Action -in @('buy', 'sell')
$IsCancelAll = $Action -eq 'cancel-all'

# LIVE mode safety gates
if ($Mode -eq 'live') {
    # Trading actions require ALPACA_LIVE_ARM and confirmation
    if ($IsTrading) {
        if ($env:ALPACA_LIVE_ARM -ne 'YES') {
            Write-Error "LIVE trading blocked. Set `$env:ALPACA_LIVE_ARM='YES' to arm live trading."
            exit 1
        }

        # Determine side
        $Side = $Action

        # Build expected confirmation string
        $ExpectedConfirm = "LIVE-$Symbol-$Qty-$Side"

        if ($Confirm -ne $ExpectedConfirm) {
            Write-Error "LIVE trading requires confirmation. Expected: -Confirm `"$ExpectedConfirm`""
            exit 1
        }
    }

    # Cancel-all requires ALPACA_LIVE_ARM (destructive)
    if ($IsCancelAll) {
        if ($env:ALPACA_LIVE_ARM -ne 'YES') {
            Write-Error "LIVE cancel-all blocked. Set `$env:ALPACA_LIVE_ARM='YES' to arm live trading."
            exit 1
        }
    }
}

# Validate limit order requirements
if ($IsTrading -and $Type -eq 'limit' -and [string]::IsNullOrWhiteSpace($Limit)) {
    Write-Error "ERROR: Limit orders require -Limit parameter (e.g., -Limit 400.00)"
    exit 1
}

# Execute action
switch ($Action) {
    'status' {
        $Url = "$BaseUrl/v2/account"
        $Result = curl.exe -s -f --fail-with-body -X GET $Url `
            -H "APCA-API-KEY-ID: $ApiKey" `
            -H "APCA-API-SECRET-KEY: $SecretKey"

        if ($LASTEXITCODE -ne 0) {
            Write-Error "HTTP request failed"
            exit 1
        }
        Write-Output $Result
    }

    'positions' {
        $Url = "$BaseUrl/v2/positions"
        $Result = curl.exe -s -f --fail-with-body -X GET $Url `
            -H "APCA-API-KEY-ID: $ApiKey" `
            -H "APCA-API-SECRET-KEY: $SecretKey"

        if ($LASTEXITCODE -ne 0) {
            Write-Error "HTTP request failed"
            exit 1
        }
        Write-Output $Result
    }

    'orders' {
        $Url = "$BaseUrl/v2/orders?status=open&limit=50"
        $Result = curl.exe -s -f --fail-with-body -X GET $Url `
            -H "APCA-API-KEY-ID: $ApiKey" `
            -H "APCA-API-SECRET-KEY: $SecretKey"

        if ($LASTEXITCODE -ne 0) {
            Write-Error "HTTP request failed"
            exit 1
        }
        Write-Output $Result
    }

    'cancel-all' {
        $Url = "$BaseUrl/v2/orders"
        $Result = curl.exe -s -f --fail-with-body -X DELETE $Url `
            -H "APCA-API-KEY-ID: $ApiKey" `
            -H "APCA-API-SECRET-KEY: $SecretKey"

        if ($LASTEXITCODE -ne 0) {
            Write-Error "HTTP request failed"
            exit 1
        }
        Write-Output $Result
    }

    { $_ -in @('buy', 'sell') } {
        $Side = $Action

        # Build order payload
        $OrderPayload = @{
            symbol = $Symbol
            qty = $Qty
            side = $Side
            type = $Type
            time_in_force = $Tif
        }

        if ($Type -eq 'limit') {
            $OrderPayload.limit_price = $Limit
        }

        if ($Extended) {
            $OrderPayload.extended_hours = $true
        }

        $JsonPayload = $OrderPayload | ConvertTo-Json -Compress

        $Url = "$BaseUrl/v2/orders"
        $Result = curl.exe -s -f --fail-with-body -X POST $Url `
            -H "APCA-API-KEY-ID: $ApiKey" `
            -H "APCA-API-SECRET-KEY: $SecretKey" `
            -H "Content-Type: application/json" `
            -d $JsonPayload

        if ($LASTEXITCODE -ne 0) {
            Write-Error "HTTP request failed"
            exit 1
        }
        Write-Output $Result
    }
}

exit 0
