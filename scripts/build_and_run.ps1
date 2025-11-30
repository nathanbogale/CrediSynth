Param(
    [string]$Tag = "credisynth-qaa:local",
    [string]$EnvFile = ".env"
)

Write-Host "Building image $Tag..."
docker build -t $Tag .
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed"; exit 1 }

Write-Host "Starting container on port 5000..."
docker run --rm -p 5000:5000 --env-file $EnvFile $Tag