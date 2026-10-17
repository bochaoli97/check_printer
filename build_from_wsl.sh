#!/usr/bin/env bash
# Build the Windows exe from WSL with one command:
#   1. copy the source to %USERPROFILE%\CheckPrinterBuild on Windows
#   2. run build_exe.bat with the Windows Python
# Why not build inside WSL? PyInstaller cannot cross-compile: building on Linux produces
# a Linux program, so a .exe has to be built with the Windows version of Python.
# config.json (your account number) is never copied; the exe asks for your details on first run.
set -euo pipefail
cd "$(dirname "$0")"

WIN_PROFILE=$(cd /mnt/c && cmd.exe /c "echo %USERPROFILE%" | tr -d '\r')
BUILD_DIR="$(wslpath "$WIN_PROFILE")/CheckPrinterBuild"
mkdir -p "$BUILD_DIR"
cp app.py make_check.py icon.ico config.example.json requirements.txt build_exe.bat "$BUILD_DIR/"
rm -rf "$BUILD_DIR/fonts"
cp -r fonts "$BUILD_DIR/fonts"
echo "Source copied to $WIN_PROFILE\\CheckPrinterBuild"

cd "$BUILD_DIR"
cmd.exe /c build_exe.bat nopause

if [ -f "$BUILD_DIR/dist/CheckPrinter/CheckPrinter.exe" ]; then
    echo
    echo "Build complete: $WIN_PROFILE\\CheckPrinterBuild\\dist\\CheckPrinter\\CheckPrinter.exe"
    explorer.exe "$(wslpath -w "$BUILD_DIR/dist/CheckPrinter")" || true
fi
