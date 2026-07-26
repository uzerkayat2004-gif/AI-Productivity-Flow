Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
WshShell.Run "cmd /c ""C:\Python314\python.exe"" -m voice_flow.main > scratch\launch_crash.log 2>&1", 0, False
