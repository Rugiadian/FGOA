' FGOA Silent Runner (No Terminal/Console Window)
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"

If fso.FileExists(pythonwExe) Then
    WshShell.Run """" & pythonwExe & """ """ & appDir & "\main.py""", 0, False
Else
    WshShell.Run "pythonw.exe """ & appDir & "\main.py""", 0, False
End If
