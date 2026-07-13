@echo off
setlocal
REM ============================================================================
REM weekly_prep.cmd — unattended Monday-morning Portland Events pipeline prep.
REM
REM Runs: scrape all sources -> push to the Inbox sheet (cleared first) ->
REM       --stage prep (Categorize + Dedup tabs) -> --stage review (Review tab)
REM so the Review tab is ready on Ian's phone with no commands to run. The
REM only remaining manual steps are the y/n pass and:
REM       python portland_events_add.py --stage commit --yes
REM
REM Registered in Task Scheduler as "PortlandEvents Weekly Prep" (Mon 6:00 AM).
REM   Inspect:  schtasks /Query /TN "PortlandEvents Weekly Prep" /V
REM   Remove:   schtasks /Delete /TN "PortlandEvents Weekly Prep" /F
REM   Run now:  schtasks /Run /TN "PortlandEvents Weekly Prep"
REM
REM NOTE: the push uses --clear (the Inbox is wiped and rewritten each week;
REM already-committed events are re-detected as duplicates by prep). If an IG
REM batch has been PUSHED to the Inbox but not yet committed when this fires,
REM those rows are cleared — re-run the IG write afterwards.
REM
REM Logs: scripts\logs\weekly_prep_<date>.log (gitignored).
REM ============================================================================

set SCRIPTS=%~dp0
set LOGDIR=%SCRIPTS%logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%i
set LOG=%LOGDIR%\weekly_prep_%STAMP%.log

REM Fail loudly in the log if the OAuth token needs a browser re-consent,
REM instead of hanging the scheduled task on an invisible prompt.
set GOOGLE_AUTH_NONINTERACTIVE=1

echo === weekly_prep start %DATE% %TIME% === > "%LOG%"

echo [1/3] Scraping all sources and pushing to the Inbox sheet... >> "%LOG%"
cd /d "%SCRIPTS%event-scrapers"
python run_all.py --push-to-sheets --clear >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

echo [2/3] Writing Categorize + Dedup tabs (--stage prep)... >> "%LOG%"
cd /d "%SCRIPTS%add-to-calendar"
python portland_events_add.py --stage prep >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

echo [3/3] Writing the Review tab (--stage review)... >> "%LOG%"
python portland_events_add.py --stage review >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

echo === weekly_prep OK %DATE% %TIME% === >> "%LOG%"
exit /b 0

:fail
echo === weekly_prep FAILED %DATE% %TIME% -- see above === >> "%LOG%"
exit /b 1
