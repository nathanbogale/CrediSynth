Param(
    [string]$BaseUrl = "http://127.0.0.1:4000",
    [string]$Sample = "sample_request.json"
)

Write-Host "Checking health at $BaseUrl/health..."
$health = Invoke-RestMethod -Method GET -Uri "$BaseUrl/health"
Write-Host "Health:" ($health | ConvertTo-Json)

Write-Host "Posting sample request to $BaseUrl/v1/analyze..."
$body = Get-Content $Sample -Raw
$resp = Invoke-RestMethod -Method POST -Uri "$BaseUrl/v1/analyze" -ContentType 'application/json' -Body $body
Write-Output ($resp | ConvertTo-Json -Depth 6)