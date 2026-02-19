@echo off
setlocal enabledelayedexpansion

REM Ralph Wiggum Loop - Windows adaptation for Copilot SDK detective agent
REM Usage: ralph.bat [max_iterations] [seed_session_id]
REM
REM Each iteration:
REM   1. Runs the agent with --seed-from (if available)
REM   2. Agent works on the challenge
REM   3. On exit, the latest session becomes the seed for next iteration
REM   4. Repeats until max_iterations or completion

set MAX_ITERATIONS=%1
if "%MAX_ITERATIONS%"=="" set MAX_ITERATIONS=5

set SEED_SESSION=%2
set CHALLENGE_URL=https://detective.kusto.io/inbox

echo ===============================================================
echo   Ralph Wiggum Loop - Detective Agent
echo   Max iterations: %MAX_ITERATIONS%
echo   Challenge: %CHALLENGE_URL%
echo ===============================================================

for /L %%i in (1,1,%MAX_ITERATIONS%) do (
    echo.
    echo ===============================================================
    echo   Iteration %%i of %MAX_ITERATIONS%
    echo ===============================================================

    REM Build the command
    if "!SEED_SESSION!"=="" (
        echo   Starting fresh (no seed)
        python -m detective.main --follow "%CHALLENGE_URL%"
    ) else (
        echo   Seeding from: !SEED_SESSION!
        python -m detective.main --follow --seed-from !SEED_SESSION! "%CHALLENGE_URL%"
    )

    REM Find the latest session (becomes seed for next iteration)
    for /f "delims=" %%d in ('dir /b /ad /o-n sessions\session_* 2^>nul ^| findstr /r "^session_"') do (
        set SEED_SESSION=%%d
        goto :found_%%i
    )
    :found_%%i

    echo   Session: !SEED_SESSION!

    REM Check if the session completed successfully
    findstr /c:"completed" "sessions\!SEED_SESSION!\session_state.json" >nul 2>&1
    if !errorlevel! equ 0 (
        echo.
        echo ===============================================================
        echo   Ralph completed the challenge at iteration %%i!
        echo ===============================================================
        goto :done
    )

    echo   Session ended. Continuing to next iteration...
    timeout /t 3 /nobreak >nul 2>&1
)

echo.
echo ===============================================================
echo   Ralph reached max iterations (%MAX_ITERATIONS%) without solving.
echo   Latest session: %SEED_SESSION%
echo ===============================================================

:done
endlocal
