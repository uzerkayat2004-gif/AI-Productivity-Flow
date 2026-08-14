Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strPath = fso.GetParentFolderName(WScript.ScriptFullName)
strSrc = strPath & "\src"
WshShell.CurrentDirectory = strSrc

' Discover best available pythonw.exe (Silent Windows GUI Python)
strPythonw = strPath & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(strPythonw) Then
    strPythonw = "C:\Python314\pythonw.exe"
End If
If Not fso.FileExists(strPythonw) Then
    strPythonw = "pythonw.exe"
End If

' Launch Voice Flow Watchdog Supervisor silently (0 = SW_HIDE, False = Do not wait)
WshShell.Run """" & strPythonw & """ -m voice_flow.watchdog", 0, False
