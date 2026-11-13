@echo off
setlocal DisableDelayedExpansion
if not "%~2"=="" goto usage
if /i "%~1"=="--help" goto usage
"%SystemRoot%\System32\cscript.exe" //nologo "%~dp0tools\create_shortcut.vbs" "%~dp0." "%~1" "Programs"
exit /b %errorlevel%

:usage
echo Usage: Create-StartMenuShortcut.cmd [destination-directory]
exit /b 1
