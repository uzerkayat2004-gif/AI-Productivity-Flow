Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath & "\src"
WshShell.Run """C:\Python314\python.exe"" -m voice_flow.main", 1, False
