@echo off
rem Builds f1train.exe with gcc 15+ (MSYS2 ucrt64: pacman -S mingw-w64-ucrt-x86_64-gcc).
rem The game builds it automatically when gcc is on PATH; this is for building by hand.
cd /d "%~dp0"
gcc -std=gnu23 -O3 -march=native -ffast-math -o f1train.exe f1train.c -static || exit /b 1
echo f1train.exe gebaut. Streckendaten: python ..\train.py --export
