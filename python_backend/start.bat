@echo off
echo [TradeFlow] Installing dependencies...
pip install -r requirements.txt

echo [TradeFlow] Starting backend on http://localhost:4000
python server.py
pause
