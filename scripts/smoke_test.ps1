# Hit all endpoints, assert 200
$base = "http://127.0.0.1:8000"
$endpoints = @(
    "/v1/health",
    "/v1/health/deep",
    "/v1/readiness"
)
# Additional endpoints can be added here once they are implemented
#    "/v1/cases",
#    "/v1/dashboard/summary",
#    "/v1/missions",
#    "/v1/alerts/log",
#    "/v1/prahari/status"

$success = $true

foreach ($ep in $endpoints) {
    try {
        $resp = Invoke-WebRequest -Uri "$base$ep" -Method GET -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            Write-Host "OK: $ep" -ForegroundColor Green
        } else {
            Write-Host "FAIL: $ep returned $($resp.StatusCode)" -ForegroundColor Red
            $success = $false
        }
    } catch {
        Write-Host "FAIL: $ep - $_" -ForegroundColor Red
        $success = $false
    }
}

if ($success) {
    Write-Host "All smoke tests passed" -ForegroundColor Green
} else {
    Write-Host "Some smoke tests failed" -ForegroundColor Red
    exit 1
}
