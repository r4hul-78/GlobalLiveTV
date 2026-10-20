<#
.SYNOPSIS
    Automated Stream Health Check - Windows Task Scheduler Automation Utility
.DESCRIPTION
    Registers, configures, queries, or triggers recurring background stream health
    checks for the Global Live TV Platform using Windows Task Scheduler (schtasks.exe).
.PARAMETER Action
    The action to perform: Register, Unregister, RunNow, or Status (default).
.PARAMETER TaskName
    The name of the Windows Scheduled Task (default: GlobalLiveTV_HealthCheck).
.PARAMETER IntervalMinutes
    How often in minutes the scheduled check should repeat (default: 60).
.PARAMETER BatchSize
    How many channels to probe per automated run (default: 50).
.PARAMETER Concurrency
    Concurrent network probe threads (default: 5).
.EXAMPLE
    .\scripts\schedule_health_check.ps1 -Action Register -IntervalMinutes 60 -BatchSize 50
.EXAMPLE
    .\scripts\schedule_health_check.ps1 -Action RunNow
.EXAMPLE
    .\scripts\schedule_health_check.ps1 -Action Status
.EXAMPLE
    .\scripts\schedule_health_check.ps1 -Action Unregister
#>

[CmdletBinding()]
param (
    [ValidateSet("Register", "Unregister", "RunNow", "Status")]
    [string]$Action = "Status",

    [string]$TaskName = "GlobalLiveTV_HealthCheck",

    [int]$IntervalMinutes = 60,

    [int]$BatchSize = 50,

    [int]$Concurrency = 5
)

$ErrorActionPreference = "Stop"

# Determine project directories
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

# Locate Python executable inside virtual environment or system fallback
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $SystemPython = (Get-Command python.exe -ErrorAction SilentlyContinue)
    if ($SystemPython) {
        $PythonExe = $SystemPython.Source
    } else {
        Write-Error "Python executable could not be found. Please ensure .venv or python is on PATH."
        exit 1
    }
}

$HealthScript = Join-Path $ProjectRoot "scripts\check_health.py"
if (-not (Test-Path $HealthScript)) {
    Write-Error "Health check script not found at: $HealthScript"
    exit 1
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " Global Live TV - Windows Task Scheduler Automation" -ForegroundColor Cyan
Write-Host " Project Root: $ProjectRoot" -ForegroundColor DarkGray
Write-Host " Task Name:    $TaskName" -ForegroundColor DarkGray
Write-Host " Action:       $Action" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

switch ($Action) {
    "Register" {
        $Arguments = "`"$HealthScript`" --limit $BatchSize --concurrency $Concurrency"
        $TaskRunCommand = "`"$PythonExe`" $Arguments"

        Write-Host "Registering scheduled task '$TaskName' to repeat every $IntervalMinutes minutes..." -ForegroundColor Green
        Write-Host "Command: $TaskRunCommand" -ForegroundColor DarkGray

        # Build schtasks arguments
        $SchArgs = @(
            "/Create",
            "/TN", $TaskName,
            "/TR", $TaskRunCommand,
            "/SC", "MINUTE",
            "/MO", $IntervalMinutes,
            "/F"
        )

        & schtasks.exe $SchArgs

        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n[SUCCESS] Task '$TaskName' registered successfully." -ForegroundColor Green
            Write-Host "It will probe $BatchSize channels every $IntervalMinutes minutes in the background." -ForegroundColor White
        } else {
            Write-Error "Failed to register scheduled task. Ensure you have appropriate permissions."
        }
    }

    "Unregister" {
        Write-Host "Deleting scheduled task '$TaskName'..." -ForegroundColor Yellow
        & schtasks.exe /Delete /TN $TaskName /F
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n[SUCCESS] Task '$TaskName' deleted successfully." -ForegroundColor Green
        } else {
            Write-Warning "Task '$TaskName' was not found or could not be removed."
        }
    }

    "RunNow" {
        Write-Host "Triggering immediate on-demand execution of '$TaskName'..." -ForegroundColor Green
        & schtasks.exe /Run /TN $TaskName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n[SUCCESS] Task triggered. Check log files or JobRun records in database for status." -ForegroundColor Green
        } else {
            Write-Error "Failed to trigger task '$TaskName'."
        }
    }

    "Status" {
        Write-Host "Querying scheduled task status..." -ForegroundColor Green
        & schtasks.exe /Query /TN $TaskName /FO LIST /V
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nTask '$TaskName' is currently NOT registered." -ForegroundColor Yellow
            Write-Host "To register, run: .\scripts\schedule_health_check.ps1 -Action Register" -ForegroundColor White
        }
    }
}
