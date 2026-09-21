@echo off
rem Project Butler: скан + локальный визуал http://127.0.0.1:17373
cd /d %~dp0
py -3.12 -m butler ui
pause
