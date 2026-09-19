# Start local infrastructure (MongoDB, MinIO, Hardhat node)
$root = Split-Path -Parent $PSScriptRoot
docker compose -f "$root\infra\docker-compose.yml" up -d
