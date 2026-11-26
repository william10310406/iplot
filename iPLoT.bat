@echo off
rem Everything up to ":main" must stay ASCII.
rem cmd decodes a batch file with the console code page while it reads it.
rem Switching to UTF-8 (chcp 65001) halfway through a file that was opened
rem under 950 makes cmd lose its place and run pieces of Chinese lines as
rem commands. So: switch first, run this file again in a fresh cmd that reads
rem it as UTF-8 from the start, then put the original code page back.
if "%IPLOT_UTF8%"=="1" goto :main
setlocal
set "IPLOT_OLDCP="
for /f "tokens=2 delims=:" %%c in ('chcp') do set /a "IPLOT_OLDCP=%%c" >nul 2>&1
chcp 65001 >nul
set "IPLOT_UTF8=1"
cmd /d /c call "%~f0" %*
set "IPLOT_RC=%errorlevel%"
if defined IPLOT_OLDCP chcp %IPLOT_OLDCP% >nul
exit /b %IPLOT_RC%

:main
setlocal
set "IPLOT_UTF8="
cd /d "%~dp0"

rem iPLoT launcher for Windows.
rem  1. Find a real Python >= 3.10: py -3, then python on PATH, then
rem     %LOCALAPPDATA%\Programs\Python\Python3*\python.exe (highest version).
rem     "Real" means it runs and prints its version. python.exe under
rem     WindowsApps (the Microsoft Store shortcut) is never used.
rem  2. None found: offer to install Python with winget, or explain how.
rem  3. Run main.py; pause only when it exits with an error.
rem  "iPLoT.bat --check": detect and report only (no install, no launch, no pause).
rem This file is UTF-8 without BOM, CRLF line endings (see .gitattributes).

set "MODE=run"
if /i "%~1"=="--check" set "MODE=check"

call :find_python
if defined PY goto :have_python
if "%MODE%"=="check" goto :check_missing

echo.
echo 這台電腦還沒有 Python，iPLoT 需要 Python 3.10 以上。
echo.
where winget >nul 2>&1
if errorlevel 1 goto :manual
set "ANS="
set /p "ANS=要現在自動安裝 Python 嗎？(Y/N) "
if /i not "%ANS%"=="Y" goto :manual

echo.
echo 正在用 winget 安裝 Python 3.13（python.org 的版本，內含 tkinter）…
echo.
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
set "WINGET_RC=%errorlevel%"
echo.
rem This window's PATH is not refreshed after installing, so look again by full path.
call :find_python
if defined PY goto :installed
echo 安裝沒有成功（winget 回傳碼 %WINGET_RC%），或裝好之後還是找不到 Python。
goto :manual

:installed
echo Python 安裝完成，接著啟動 iPLoT。
echo.
goto :launch

:manual
echo.
echo 請到下面這個網址下載 Python 3.10 以上的安裝檔：
echo     https://www.python.org/downloads/
echo 安裝時請勾選「tcl/tk」和「Add python.exe to PATH」。
echo 裝好之後，再雙擊一次 iPLoT.bat。
echo.
echo 按任意鍵關閉這個視窗…
pause >nul
exit /b 1

:check_missing
echo PYTHON=none
echo 找不到 Python（iPLoT 需要 Python 3.10 以上）。
where winget >nul 2>&1
if errorlevel 1 (echo WINGET=none) else (echo WINGET=found)
exit /b 1

:have_python
if not "%MODE%"=="check" goto :launch
echo PYTHON=%PY%
echo 找到 Python：%PY%（版本代碼 %PYVER%，例如 313 = 3.13）
exit /b 0

:launch
%PY% main.py %*
set "RC=%errorlevel%"
if "%RC%"=="0" exit /b 0
echo.
echo iPLoT 結束時回報錯誤（代碼 %RC%）。上面的訊息可以截圖，用「回報與討論」回報。
echo 按任意鍵關閉這個視窗…
pause >nul
exit /b %RC%


rem ---------------------------------------------------------------------------
rem :find_python sets PY (a command: py -3, or a quoted path) and PYVER
rem (major*100+minor, e.g. 313). PY stays undefined when nothing usable is found.
:find_python
set "PY="
set "PYVER=0"
where py >nul 2>&1
if not errorlevel 1 call :try py -3
if defined PY goto :eof
for /f "delims=" %%p in ('where python 2^>nul') do call :try_path "%%p"
if defined PY goto :eof
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" call :try "%%d\python.exe"
goto :eof

:try_path
rem python.exe from PATH: first usable one wins; skip the Store shortcut.
if defined PY goto :eof
set "CAND=%~1"
if not "%CAND:\WindowsApps\=%"=="%CAND%" goto :eof
call :try "%CAND%"
goto :eof

:try
rem %1 = program (quoted path or py), %2 = optional argument (-3).
rem Accept when it prints a version >= 3.10 and is newer than what we have.
rem stdin from nul so nothing can sit waiting for input.
set "V="
for /f "delims=" %%v in ('call %1 %2 -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2^>nul ^<nul') do set "V=%%v"
if not defined V goto :eof
rem (set /a does not reset errorlevel, so check the number itself; junk -> 0)
set "N=0"
set /a "N=V" >nul 2>&1
if %N% LSS 310 goto :eof
if %N% LEQ %PYVER% goto :eof
set "PYVER=%N%"
if "%~2"=="" (set PY="%~1") else (set "PY=%~1 %~2")
goto :eof
