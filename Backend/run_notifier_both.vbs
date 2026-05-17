Set oWS = WScript.CreateObject("WScript.Shell")
sFile = "C:\\Users\\ADM\\Desktop\\NetWeb\\Backend\\notifier.py"
sCmd = "pythonw """ & sFile & """ --api http://127.0.0.1:5000 --interval 5 --sound --both"
oWS.Run sCmd, 0, False
WScript.Sleep 2000
