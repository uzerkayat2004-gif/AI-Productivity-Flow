Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strPath = fso.GetParentFolderName(WScript.ScriptFullName)
strSrc = strPath & "\src"
strVenv = strPath & "\.venv"
strSitePkgs = strVenv & "\Lib\site-packages"
WshShell.CurrentDirectory = strSrc
WshShell.Environment("PROCESS")("PYTHONPATH") = strSrc & ";" & strSitePkgs
WshShell.Environment("PROCESS")("VIRTUAL_ENV") = strVenv
WshShell.Environment("PROCESS")("__PYVENV_LAUNCHER__") = strVenv & "\Scripts\pythonw.exe"

' Find genuine GUI pythonw.exe (subsystem 2, zero console window)
strPython = ""
strPyCfg = strVenv & "\pyvenv.cfg"
If fso.FileExists(strPyCfg) Then
    On Error Resume Next
    Set cfgFile = fso.OpenTextFile(strPyCfg, 1)
    Do While Not cfgFile.AtEndOfStream
        cfgLine = cfgFile.ReadLine()
        If InStr(1, cfgLine, "home", 1) = 1 Then
            cfgParts = Split(cfgLine, "=")
            If UBound(cfgParts) >= 1 Then
                baseHome = Trim(cfgParts(1))
                basePyw = baseHome & "\pythonw.exe"
                If fso.FileExists(basePyw) Then
                    strPython = basePyw
                End If
            End If
        End If
    Loop
    cfgFile.Close
    On Error GoTo 0
End If

If strPython = "" Or Not fso.FileExists(strPython) Then
    If fso.FileExists(strVenv & "\Scripts\pythonw.exe") Then
        strPython = strVenv & "\Scripts\pythonw.exe"
    ElseIf fso.FileExists("C:\Users\Asus\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe") Then
        strPython = "C:\Users\Asus\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
    ElseIf fso.FileExists("C:\Python314\pythonw.exe") Then
        strPython = "C:\Python314\pythonw.exe"
    ElseIf fso.FileExists(strVenv & "\Scripts\python.exe") Then
        strPython = strVenv & "\Scripts\python.exe"
    Else
        strPython = "python.exe"
    End If
End If

' Launch AI Productivity Flow Desktop App silently (zero console popup)
WshShell.Run """" & strPython & """ -m voice_flow.gui.desktop_launcher", 0, False
