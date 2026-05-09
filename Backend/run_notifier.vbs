' IDS Notifier - Launcher (invisible)
' Connexion directe a PostgreSQL sur 192.168.1.2
' Avec notification email aux administrateurs
Set oWS = WScript.CreateObject("WScript.Shell")
sFile = "C:\\Users\\21366\\OneDrive\\Bureau\\Projet_finale\\NetWeb\\Backend\\notifier.py"
sCmd = "pythonw """ & sFile & """ --db --interval 5 --sound"
oWS.Run sCmd, 0, False
WScript.Sleep 2000
