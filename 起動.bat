@echo off
cd /d %~dp0
echo 株式投資ツールを起動中...
echo ブラウザで http://localhost:8501 を開いてください
echo (このウィンドウは閉じないでください)
echo.
C:\Users\kimura-h-0\anaconda3\envs\stock_analyzer\Scripts\streamlit.exe run app.py
pause
