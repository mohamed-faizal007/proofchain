<#
.SYNOPSIS
  End-to-end ProofChain demo: start the full stack with an anchoring chain, seed data, verify it.

.DESCRIPTION
  1. Starts MongoDB, MinIO, the Hardhat chain and the app (backend with the NLP models baked in,
     frontend) with docker compose, deploys ProofChainRegistry and hands its address to the backend.
  2. Seeds the demo users, then registers a lease (v1), approves it, submits and approves an
     amendment (v2), waits for both on-chain anchors.
  3. Verifies the original, v2, four altered copies and a re-saved copy, and prints the verdicts.
  Safe to rerun: it reuses the running stack, the deployed registry and the demo document.

  Run from the repo root:   .\scripts\demo.ps1
  Rebuild the images after code changes (otherwise an existing image is reused; a missing one is built,
  which takes a long time the first time because the backend image carries the NLP models):
                            .\scripts\demo.ps1 -Build
  Chain was reset (container recreated) and the database still has anchors for the old registry:
                            .\scripts\demo.ps1 -Reset      (wipes the demo database and object store)
  Public testnet instead of the local chain (spends test ETH; NOT exercised by the project tests):
      $env:ANCHOR_PRIVATE_KEY = '<funded Sepolia key>'; $env:CHAIN_RPC_URL = '<Sepolia RPC URL>'
      .\scripts\demo.ps1 -Network sepolia
  Needs Docker Desktop, Node 20 (contracts) and backend\.venv (py -3.11 -m venv .venv; pip install -e ".[dev]").
#>
[CmdletBinding()]
param(
    [ValidateSet('localhost', 'sepolia')][string]$Network = 'localhost',
    [switch]$Reset,
    [switch]$Build,
    [int]$HealthTimeoutSec = 600
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'infra\docker-compose.yml'
$demoDir = Join-Path $root 'demo'
$statePath = Join-Path $demoDir 'state.json'
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$apiBase = 'http://127.0.0.1:8000/api/v1'
$rpcUrl = 'http://127.0.0.1:8545'
$profiles = @('--profile', 'app')
if ($Network -eq 'localhost') { $profiles += @('--profile', 'chain') }
$clock = [Diagnostics.Stopwatch]::StartNew()
$timings = [ordered]@{}

# Public Hardhat dev account #0 (printed by every `hardhat node`); only ever used on the local chain.
$hardhatDevKey = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }

function Invoke-Native([scriptblock]$Command, [string]$What) {
    # Native tools write progress to stderr; that must not abort the script, only a bad exit code.
    $ErrorActionPreference = 'Continue'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Invoke-Compose {
    $composeArgs = $args
    Invoke-Native { docker compose -f $composeFile @composeArgs } "docker compose $($composeArgs -join ' ')"
}

function Invoke-Rpc([string]$Method, [object[]]$Params = @()) {
    $body = @{ jsonrpc = '2.0'; id = 1; method = $Method; params = $Params } | ConvertTo-Json -Compress
    (Invoke-RestMethod -Uri $rpcUrl -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 5).result
}

function Assert-PortsAvailable {
    # Ports this stack publishes. Something else holding one (e.g. another project's MongoDB)
    # would make compose fail halfway, or worse, talk to the wrong service.
    $ports = @(27017, 9000, 9001, 8000, 8080)
    if ($Network -eq 'localhost') { $ports += 8545 }
    # docker ps prints single ports ("127.0.0.1:8000->8000/tcp") and ranges ("127.0.0.1:9000-9001->9000-9001/tcp").
    $published = (docker ps --filter 'label=com.docker.compose.project=proofchain' --format '{{.Ports}}') -join ' '
    $ours = @()
    foreach ($m in [regex]::Matches($published, ':(\d+)(?:-(\d+))?->')) {
        $low = [int]$m.Groups[1].Value
        $high = if ($m.Groups[2].Success) { [int]$m.Groups[2].Value } else { $low }
        $ours += $low..$high
    }
    foreach ($port in $ports) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($listener -and ($ours -notcontains $port)) {
            throw "Port $port is already in use by something that is not this project's containers. Stop it first (docker ps shows other stacks)."
        }
    }
}

function Wait-Until([scriptblock]$Condition, [int]$TimeoutSec, [string]$What) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try { if (& $Condition) { return } } catch { }
        Start-Sleep -Seconds 3
    }
    throw "Timed out after ${TimeoutSec}s waiting for $What"
}

if (-not (Test-Path $python)) {
    throw "backend\.venv not found. From backend\: py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -e '.[dev]'"
}
Invoke-Native { docker info --format '{{.ServerVersion}}' | Out-Null } 'docker (is Docker Desktop running?)'
New-Item -ItemType Directory -Force -Path $demoDir | Out-Null

if ($Reset) {
    Write-Step 'Reset: removing containers and the demo database / object store volumes'
    Invoke-Compose --profile app --profile chain down -v
    Remove-Item -Force -ErrorAction SilentlyContinue $statePath
}
Assert-PortsAvailable

# --- 1. infrastructure and chain -------------------------------------------------------------
$phase = [Diagnostics.Stopwatch]::StartNew()
if ($Network -eq 'localhost') {
    Write-Step 'Starting MongoDB, MinIO and the Hardhat chain'
    Invoke-Compose --profile chain up -d mongo minio minio-init hardhat
    Wait-Until { $null -ne (Invoke-Rpc 'eth_blockNumber') } 300 'the Hardhat node on 8545 (first start runs npm install)'

    $address = $null
    if (Test-Path $statePath) {
        $address = (Get-Content -Raw $statePath | ConvertFrom-Json).address
        if ((Invoke-Rpc 'eth_getCode' @($address, 'latest')) -eq '0x') {
            throw "The chain was reset: no contract at $address any more, but the database may still hold anchors for it. Rerun with -Reset to start the demo data from scratch."
        }
        Write-Host "Reusing the registry deployed at $address"
    } else {
        Write-Step 'Deploying ProofChainRegistry to the local chain'
        Push-Location (Join-Path $root 'contracts')
        try {
            if (-not (Test-Path 'node_modules')) { Invoke-Native { npm ci --no-audit --no-fund } 'npm ci' }
            $deployOutput = (& { $ErrorActionPreference = 'Continue'; npx hardhat run scripts/deploy.ts --network localhost 2>&1 } | Out-String)
            if ($LASTEXITCODE -ne 0) { throw "contract deploy failed:`n$deployOutput" }
        } finally { Pop-Location }
        if ($deployOutput -notmatch 'REGISTRY_ADDRESS=(0x[0-9a-fA-F]{40})') { throw "deploy printed no REGISTRY_ADDRESS:`n$deployOutput" }
        $address = $Matches[1]
        @{ address = $address; network = $Network } | ConvertTo-Json | Set-Content -Encoding UTF8 $statePath
        Write-Host "Registry deployed at $address"
    }
    $env:REGISTRY_ADDRESS = $address
    $env:ANCHOR_PRIVATE_KEY = $hardhatDevKey
} else {
    # The anchoring key comes from this shell only (never a file); the address from the committed record.
    foreach ($name in 'ANCHOR_PRIVATE_KEY', 'CHAIN_RPC_URL') {
        if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) { throw "Set `$env:$name in this shell before using -Network sepolia." }
    }
    $env:REGISTRY_ADDRESS = (Get-Content -Raw (Join-Path $root 'contracts\deployments\sepolia.json') | ConvertFrom-Json).address
    $env:CHAIN_ID = '11155111'
    Write-Step "Starting MongoDB and MinIO; anchoring to Sepolia registry $($env:REGISTRY_ADDRESS)"
    Invoke-Compose up -d mongo minio minio-init
}
$timings['chain'] = $phase.Elapsed.TotalSeconds

# --- 2. the app ------------------------------------------------------------------------------
Write-Step 'Starting the app (backend image includes the NLP models; built only if missing or with -Build)'
$phase.Restart()
$buildFlag = if ($Build) { @('--build') } else { @() }
Invoke-Compose @profiles up -d @buildFlag
Wait-Until { (docker inspect -f '{{.State.Health.Status}}' proofchain-backend-1) -eq 'healthy' } $HealthTimeoutSec 'the backend container to become healthy'
$timings['app up + backend healthy'] = $phase.Elapsed.TotalSeconds

$health = Invoke-RestMethod -Uri "$apiBase/health" -TimeoutSec 10
if ($health.chain -ne 'ok') {
    throw "chain is not ready: /health reports chain=$($health.chain) (mongo=$($health.mongo), s3=$($health.s3)). Approved revisions would stay unanchored."
}
Write-Host "health: status=$($health.status) mongo=$($health.mongo) s3=$($health.s3) chain=$($health.chain)"

# --- 3. users, documents, verification ---------------------------------------------------------
Write-Step 'Seeding demo users'
Invoke-Compose @profiles exec -T backend python -m app.scripts.seed

Write-Step 'Seeding the demo document and verifying every demo file'
$phase.Restart()
Invoke-Native { & $python (Join-Path $PSScriptRoot 'demo_seed.py') --base-url $apiBase } 'the demo seed (a verdict did not match the expected one)'
$timings['seed + verify'] = $phase.Elapsed.TotalSeconds

# --- summary -----------------------------------------------------------------------------------
$password = if ($env:SEED_PASSWORD) { '$env:SEED_PASSWORD' } else { 'proofchain-demo-1 (public dev default)' }
Write-Host "`nDemo is up." -ForegroundColor Green
Write-Host "  App        http://127.0.0.1:8080        API docs  http://127.0.0.1:8000/docs"
Write-Host "  Logins     issuer@ / approver@ / admin@proofchain.local   password: $password"
Write-Host "  Demo files $demoDir\data  (upload them on the Verify page)"
foreach ($key in $timings.Keys) { Write-Host ("  {0,-26} {1,7:N1} s" -f $key, $timings[$key]) }
Write-Host ("  {0,-26} {1,7:N1} s" -f 'total', $clock.Elapsed.TotalSeconds)
if ($Network -eq 'localhost') {
    Write-Host "  Note: the backend container got REGISTRY_ADDRESS/ANCHOR_PRIVATE_KEY from this run only;"
    Write-Host "        recreating it without them (plain compose up) drops anchoring. Rerun this script instead."
}
