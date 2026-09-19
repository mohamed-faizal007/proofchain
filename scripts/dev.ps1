# Start local infrastructure (MongoDB, MinIO). Use -Chain to also start the Hardhat node.
param([switch]$Chain)
$root = Split-Path -Parent $PSScriptRoot
$compose = "$root\infra\docker-compose.yml"
if ($Chain) {
    docker compose -f $compose --profile chain up -d --wait mongo minio hardhat
} else {
    docker compose -f $compose up -d --wait mongo minio
}
docker compose -f $compose up minio-init
