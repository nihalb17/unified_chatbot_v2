<#
.SYNOPSIS
  Fire the same HTTP triggers as Phase 6 GitHub Actions (for local testing).

.DESCRIPTION
  Starts Phase 1 and/or Phase 2 backends locally, then run this script to POST
  to /api/reviews/refresh and/or /api/faqs/factsheets/refresh.

  Examples:
    .\scripts\test-scheduler-local.ps1 -Once
    .\scripts\test-scheduler-local.ps1 -IntervalSeconds 300 -Target Both
    .\scripts\test-scheduler-local.ps1 -Phase1Url https://staging-phase1.example.com -Once -Target Reviews
#>
param(
    [string] $Phase1Url = "http://127.0.0.1:8000",
    [string] $Phase2Url = "http://127.0.0.1:8001",
    [ValidateSet("Reviews", "Factsheets", "Both")]
    [string] $Target = "Both",
    [int] $IntervalSeconds = 300,
    [switch] $Once
)

function Invoke-Refresh {
    param([string] $Url, [string] $Label)
    $u = $Url.TrimEnd("/")
    Write-Host "[$Label] POST $u ..."
    try {
        $r = Invoke-WebRequest -Method POST -Uri $u -UseBasicParsing -TimeoutSec 120
        Write-Host "[$Label] OK $($r.StatusCode)" -ForegroundColor Green
        Write-Host $r.Content
    }
    catch {
        Write-Host "[$Label] FAILED: $_" -ForegroundColor Red
        throw
    }
}

function Run-Round {
    if ($Target -eq "Reviews" -or $Target -eq "Both") {
        Invoke-Refresh -Url "$Phase1Url/api/reviews/refresh" -Label "Phase1 reviews"
    }
    if ($Target -eq "Factsheets" -or $Target -eq "Both") {
        Invoke-Refresh -Url "$Phase2Url/api/faqs/factsheets/refresh" -Label "Phase2 factsheets"
    }
}

if ($Once) {
    Run-Round
    exit 0
}

Write-Host "Loop every $IntervalSeconds s. Ctrl+C to stop. (Use -Once for a single round.)" -ForegroundColor Cyan
while ($true) {
    Run-Round
    Start-Sleep -Seconds $IntervalSeconds
}
