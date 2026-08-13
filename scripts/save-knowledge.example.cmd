@echo off
setlocal

REM Copy this file to the repository root as save-knowledge.local.cmd.
REM Replace the key path and EC2 hostname. The .local.cmd file is gitignored.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_knowledge_ec2.ps1" ^
  -KeyPath "C:\path\to\your-key.pem" ^
  -HostName "ec2-x-x-x-x.region.compute.amazonaws.com"

if errorlevel 1 (
  echo.
  echo Knowledge deployment failed. Review the error above.
) else (
  echo.
  echo Knowledge deployment completed successfully.
)

pause
