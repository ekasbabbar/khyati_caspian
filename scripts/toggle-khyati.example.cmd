@echo off
setlocal

REM Copy this file to the repository root as toggle-khyati.local.cmd.
REM Replace the key path and EC2 hostname. The .local.cmd file is gitignored.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\control_khyati_ec2.ps1" ^
  -KeyPath "C:\path\to\your-key.pem" ^
  -HostName "ec2-x-x-x-x.region.compute.amazonaws.com" ^
  -Action toggle

if errorlevel 1 echo Failed to change Khyati's state.
echo.
pause

