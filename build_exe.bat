@echo off
setlocal
cd /d "%~dp0"
echo === Check Printer: build Windows exe ===

rem --- find Windows Python (the python.org installer provides the "py" launcher) ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython
%PY% -c "import tkinter" >nul 2>nul || goto :nopython

rem --- separate virtual environment just for building ---
if not exist ".venv-win\Scripts\python.exe" (
    echo Creating virtual environment .venv-win ...
    %PY% -m venv .venv-win || goto :fail
)
echo Installing PyInstaller and requirements.txt ...
".venv-win\Scripts\python.exe" -m pip install --upgrade --quiet pip pyinstaller -r requirements.txt || goto :fail

rem --- build as a folder (--onedir): starts faster than a single-file exe, which has to unpack
rem     itself to %TEMP% on every launch, and is flagged by antivirus far less often ---
rem reportlab loads its standard font metrics by name and Pillow (for signature PNGs) lazily, so
rem both are named explicitly. The MICR font is NOT bundled into the exe: its license asks for it to
rem ship alongside the program, so fonts\ is copied next to CheckPrinter.exe instead.
echo Building ...
".venv-win\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --distpath build\dist --workpath build\work --specpath build ^
    --name CheckPrinter --icon "%cd%\icon.ico" --add-data "%cd%\icon.ico;." ^
    --collect-submodules reportlab.pdfbase --collect-data reportlab ^
    --hidden-import PIL.Image --hidden-import PIL.PngImagePlugin ^
    app.py || goto :fail
xcopy fonts "build\dist\CheckPrinter\fonts\" /E /I /Y /Q >nul || goto :fail
copy /Y config.example.json "build\dist\CheckPrinter\" >nul || goto :fail

rem PyInstaller wipes its output folder on every build, and the app keeps config.json, checks\ and
rem perhaps a signature image next to the exe, so build into build\dist first and then copy into
rem dist\CheckPrinter: mirror only the program's own folders and never delete loose files there.
echo Updating dist\CheckPrinter (your config.json, checks and signature are kept) ...
robocopy "build\dist\CheckPrinter" "dist\CheckPrinter" /E /XD _internal fonts /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
for %%D in (_internal fonts) do (
    robocopy "build\dist\CheckPrinter\%%D" "dist\CheckPrinter\%%D" /MIR /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 goto :fail
)

echo.
echo Done: %cd%\dist\CheckPrinter\CheckPrinter.exe
echo Copy the whole CheckPrinter folder wherever you like; run CheckPrinter.exe inside it.
goto :end

:nopython
echo [ERROR] Windows Python with tkinter was not found.
echo         Install Python from https://www.python.org/downloads/windows/
echo         and tick "Add python.exe to PATH" in the installer.
goto :end

:fail
echo.
echo [ERROR] Build failed, see the messages above.

:end
if /i not "%~1"=="nopause" pause
endlocal
