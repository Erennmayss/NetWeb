' IDS Notifier - Stopper
Set oWS = WScript.CreateObject("WScript.Shell")
oWS.Run "taskkill /F /IM pythonw.exe", 0, False
WScript.Sleep 1000
