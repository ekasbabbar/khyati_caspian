[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$RemoteUser = "ubuntu",
    [string]$RemoteAppPath = "/opt/khyati/app",
    [string]$KnowledgePath,
    [string]$ServiceName = "khyati"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $KnowledgePath) {
    $KnowledgePath = Join-Path $repoRoot "knowledge"
}
$KnowledgePath = (Resolve-Path -LiteralPath $KnowledgePath).Path
$KeyPath = (Resolve-Path -LiteralPath $KeyPath).Path

if ($HostName -notmatch '^[A-Za-z0-9.-]+$') { throw "Invalid EC2 hostname." }
if ($RemoteUser -notmatch '^[a-z_][a-z0-9_-]*$') { throw "Invalid remote user." }
if ($RemoteAppPath -notmatch '^/[A-Za-z0-9._/-]+$') { throw "Invalid remote app path." }
if ($ServiceName -notmatch '^[A-Za-z0-9_.@-]+$') { throw "Invalid service name." }

if (-not (Test-Path -LiteralPath $KnowledgePath -PathType Container)) {
    throw "Knowledge directory not found: $KnowledgePath"
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "OpenSSH 'ssh' is not installed or not on PATH."
}
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "OpenSSH 'scp' is not installed or not on PATH."
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Activate the project venv or install Python."
    }
    $python = $pythonCommand.Source
}

$version = "manual-" + (Get-Date -Format "yyyyMMddHHmmss")
$manifest = Join-Path ([IO.Path]::GetTempPath()) "khyati-$version-manifest.json"
$remoteScriptPath = Join-Path ([IO.Path]::GetTempPath()) "khyati-$version-deploy.sh"
Write-Host "Validating local knowledge..." -ForegroundColor Cyan
& $python (Join-Path $repoRoot "scripts\build_knowledge_manifest.py") `
    --source $KnowledgePath `
    --version $version `
    --release-prefix "manual/$version" `
    --output $manifest
if ($LASTEXITCODE -ne 0) {
    throw "Knowledge validation failed; nothing was uploaded."
}

$remote = "${RemoteUser}@${HostName}"
$stagingRoot = "/home/$RemoteUser/khyati-knowledge-upload"
$knowledgeLeaf = Split-Path -Leaf $KnowledgePath
if ($knowledgeLeaf -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Knowledge directory name contains unsupported characters: $knowledgeLeaf"
}
$stagedKnowledge = "$stagingRoot/$knowledgeLeaf"
$liveKnowledge = "$RemoteAppPath/knowledge"
$backupKnowledge = "$RemoteAppPath/.khyati/knowledge-backup"

try {
    Write-Host "Preparing EC2 staging directory..." -ForegroundColor Cyan
    & ssh -i $KeyPath $remote "sudo rm -rf '$stagingRoot' && mkdir -p '$stagingRoot'"
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare EC2 staging directory." }

    Write-Host "Uploading knowledge to EC2..." -ForegroundColor Cyan
    & scp -i $KeyPath -r $KnowledgePath "${remote}:$stagingRoot/"
    if ($LASTEXITCODE -ne 0) { throw "SCP upload failed." }

    $remoteScript = @"
set -Eeuo pipefail
APP='$RemoteAppPath'
STAGED='$stagedKnowledge'
LIVE='$liveKnowledge'
BACKUP='$backupKnowledge'
SERVICE='$ServiceName'

test -d "`$STAGED"
sudo test -x "`$APP/.venv/bin/python"
command -v rsync >/dev/null || { echo 'Install rsync on EC2: sudo apt install -y rsync' >&2; exit 1; }
sudo systemctl cat "`$SERVICE" >/dev/null
sudo "`$APP/.venv/bin/python" "`$APP/scripts/build_knowledge_manifest.py" --source "`$STAGED" --version manual-sync --release-prefix manual/ec2 --output '$stagingRoot/manifest.json'

sudo mkdir -p "`$BACKUP" "`$LIVE"
sudo rsync -a --delete "`$LIVE/" "`$BACKUP/"
sudo rsync -a --delete "`$STAGED/" "`$LIVE/"
sudo chown -R khyati:khyati "`$LIVE" "`$BACKUP"

if ! sudo systemctl restart "`$SERVICE" || ! sleep 10 || ! sudo systemctl is-active --quiet "`$SERVICE"; then
    echo 'Khyati failed after the knowledge update; restoring the previous knowledge set.' >&2
    sudo rsync -a --delete "`$BACKUP/" "`$LIVE/"
    sudo chown -R khyati:khyati "`$LIVE"
    sudo systemctl restart "`$SERVICE"
    exit 1
fi

sudo rm -rf '$stagingRoot'
echo 'Knowledge deployed and Khyati is active.'
"@

    Write-Host "Promoting knowledge and restarting Khyati..." -ForegroundColor Cyan
    [IO.File]::WriteAllText($remoteScriptPath, $remoteScript, [Text.UTF8Encoding]::new($false))
    & scp -i $KeyPath $remoteScriptPath "${remote}:$stagingRoot/deploy.sh"
    if ($LASTEXITCODE -ne 0) { throw "Could not upload the EC2 deployment script." }
    & ssh -i $KeyPath $remote "bash '$stagingRoot/deploy.sh'"
    if ($LASTEXITCODE -ne 0) {
        throw "EC2 deployment failed. The previous knowledge set was restored when possible."
    }

    Write-Host "Saved: EC2 is running the new knowledge set." -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $manifest -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $remoteScriptPath -ErrorAction SilentlyContinue
}
