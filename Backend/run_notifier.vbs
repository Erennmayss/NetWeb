' IDS Notifier - launcher invisible
Set oWS = WScript.CreateObject("WScript.Shell")
sCmd = "pythonw ""C:\Users\ADM\Desktop\ids_1\NetWeb\Backend\notifier.py"" --interval 5"
oWS.Run sCmd, 0, False
