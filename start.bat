@echo off
echo Stopping existing server...
taskkill /F /FI "WINDOWTITLE eq uvicorn*" /IM python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo Starting MusicToGP server...
start "" /B "D:\Projects\MusicToGP\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 > "D:\Projects\MusicToGP\uvicorn_out.txt" 2> "D:\Projects\MusicToGP\uvicorn_err.txt"

echo Waiting for server to start...
timeout /t 3 /nobreak >nul

echo Opening browser...
start http://127.0.0.1:8000

exit
