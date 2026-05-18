' IDS Notifier - Launcher invisible
Set oWS = WScript.CreateObject("WScript.Shell")
sFile = "C:\\Users\\21366\\OneDrive\\Bureau\\NETWEB\\NetWeb\\Backend\\notifier.py"
sCmd = "pythonw """ & sFile & """ --db --interval 5 --sound"
oWS.Run sCmd, 0, False
WScript.Sleep 2000
