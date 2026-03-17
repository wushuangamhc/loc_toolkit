@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    exit /b 1
)

where codex >nul 2>nul
if errorlevel 1 (
    echo Warning: codex was not found in PATH. You can still use a configured codex.exec_path in loc-toolkit.json.
)

set /p PROJECT_ROOT=Localization root path:
set /p TARGET_LANG=Target language (zh/en/ru):
set /p MODE=Mode (full/incremental/file):
set /p WRITEBACK=Write translated VDF files? (y/n):
set REPORT_DIR=
set /p SAVE_REPORTS=Save report files? (y/n):
if /I "%SAVE_REPORTS%"=="y" (
    set /p REPORT_DIR=Report output directory (blank=reports):
    if "%REPORT_DIR%"=="" set REPORT_DIR=reports
)
set /p GENERATE_TM=Generate TM? (y/n):
set /p GENERATE_GLOSSARY=Generate glossary? (y/n):
set REPORT_ARGS=
if /I "%WRITEBACK%"=="y" set REPORT_ARGS=%REPORT_ARGS% --writeback
if not "%REPORT_DIR%"=="" set REPORT_ARGS=%REPORT_ARGS% --report-dir "%REPORT_DIR%"
if /I "%GENERATE_TM%"=="y" set REPORT_ARGS=%REPORT_ARGS% --generate-tm
if /I "%GENERATE_GLOSSARY%"=="y" set REPORT_ARGS=%REPORT_ARGS% --generate-glossary

if /I "%MODE%"=="full" (
    python -m loc_toolkit.cli translate full --project-root "%PROJECT_ROOT%" --target-lang %TARGET_LANG% %REPORT_ARGS%
    set EXITCODE=%errorlevel%
    pause
    exit /b %EXITCODE%
)

if /I "%MODE%"=="incremental" (
    set /p BASELINE=Baseline manifest path:
    python -m loc_toolkit.cli translate incremental --project-root "%PROJECT_ROOT%" --target-lang %TARGET_LANG% --baseline-manifest "%BASELINE%" %REPORT_ARGS%
    set EXITCODE=%errorlevel%
    pause
    exit /b %EXITCODE%
)

if /I "%MODE%"=="file" (
    set /p SOURCE_FILE=Source file path:
    python -m loc_toolkit.cli translate file --project-root "%PROJECT_ROOT%" --target-lang %TARGET_LANG% --source-file "%SOURCE_FILE%" %REPORT_ARGS%
    set EXITCODE=%errorlevel%
    pause
    exit /b %EXITCODE%
)

echo Unsupported mode: %MODE%
pause
exit /b 1
