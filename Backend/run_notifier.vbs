' IDS Notifier - Launcher invisible
Set oWS = WScript.CreateObject("WScript.Shell")
sFile = "C:\\Users\\ADM\\Desktop\\ids_1\\NetWeb\\Backend\\notifier.py"
sCmd = "pythonw """ & sFile & """ --db --interval 5 --sound"
oWS.Run sCmd, 0, False
WScript.Sleep 2000
