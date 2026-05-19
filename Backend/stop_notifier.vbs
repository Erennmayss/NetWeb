' IDS Notifier - stop current notifier.py instances only
Set oWS = WScript.CreateObject("WScript.Shell")
oWS.Run "powershell -NoProfile -ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process -Filter 'name = ''pythonw.exe'' or name = ''python.exe''' ^| Where-Object { $_.CommandLine -like '*notifier.py*' } ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }""", 0, True
