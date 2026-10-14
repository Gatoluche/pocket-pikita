Option Explicit

Dim shell, files, projectDir, pythonPath, mainPath

Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
projectDir = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = projectDir
pythonPath = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & _
    "\Programs\Python\Python310\pythonw.exe"
mainPath = files.BuildPath(projectDir, "main.py")

If Not files.FileExists(pythonPath) Then
    MsgBox "Pocket Pikita could not find Python 3.10 at:" & vbCrLf & _
        pythonPath, vbExclamation, "Pocket Pikita"
    WScript.Quit 1
End If

' Launch the same project entry point as the console launcher, without a console.
shell.Run """" & pythonPath & """ """ & mainPath & """", 0, False
