Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

On Error Resume Next
WshShell.Run "pythonw.exe -m voice_flow.gui.spawn_backend", 0, False
If Err.Number <> 0 Then
    Err.Clear
    WshShell.Run """C:\Python314\pythonw.exe"" -m voice_flow.gui.spawn_backend", 0, False
End If
