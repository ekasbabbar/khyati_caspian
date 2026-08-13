[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [ValidateSet("toggle", "on", "off", "status")]
    [string]$Action = "toggle",

    [string]$RemoteUser = "ubuntu",
    [string]$ServiceName = "khyati"
)

$ErrorActionPreference = "Stop"
$KeyPath = (Resolve-Path -LiteralPath $KeyPath).Path

if ($HostName -notmatch '^[A-Za-z0-9.-]+$') { throw "Invalid EC2 hostname." }
if ($RemoteUser -notmatch '^[a-z_][a-z0-9_-]*$') { throw "Invalid remote user." }
if ($ServiceName -notmatch '^[A-Za-z0-9_.@-]+$') { throw "Invalid service name." }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "OpenSSH 'ssh' is not installed or not on PATH."
}

$remote = "${RemoteUser}@${HostName}"
$remoteScript = switch ($Action) {
    "on" {
        "sudo systemctl enable --now '$ServiceName' && echo 'Khyati is ON.'"
    }
    "off" {
        "sudo systemctl disable --now '$ServiceName' && echo 'Khyati is OFF and will remain off after reboot.'"
    }
    "status" {
        "echo Active: `$(sudo systemctl is-active '$ServiceName' 2>/dev/null || true); echo Enabled: `$(sudo systemctl is-enabled '$ServiceName' 2>/dev/null || true)"
    }
    default {
        "if sudo systemctl is-active --quiet '$ServiceName'; then sudo systemctl disable --now '$ServiceName' && echo 'Khyati is OFF and will remain off after reboot.'; else sudo systemctl enable --now '$ServiceName' && echo 'Khyati is ON.'; fi"
    }
}

& ssh -i $KeyPath $remote $remoteScript
if ($LASTEXITCODE -ne 0) {
    throw "Could not change Khyati's EC2 service state."
}
