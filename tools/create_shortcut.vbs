Option Explicit

Dim shell, files, project, destination, pythonPath, settingsPath, iconPath, shortcutPath, shortcut, required
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
project = files.GetAbsolutePathName(WScript.Arguments(0))
destination = WScript.Arguments(1)
If destination = "" Then
    If WScript.Arguments.Count > 2 Then
        destination = shell.SpecialFolders(WScript.Arguments(2))
    Else
        destination = shell.SpecialFolders("Desktop")
    End If
End If
destination = files.GetAbsolutePathName(destination)
pythonPath = files.BuildPath(project, ".venv\Scripts\pythonw.exe")
settingsPath = files.BuildPath(project, "settings.py")
iconPath = files.BuildPath(project, "assets\app-icon.ico")

For Each required In Array(pythonPath, settingsPath, iconPath)
    If Not files.FileExists(required) Then Fail "Required file does not exist: " & required
Next
If Not files.FolderExists(destination) Then Fail "Destination directory does not exist: " & destination

shortcutPath = files.BuildPath(destination, "AMD HUD.lnk")
Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = pythonPath
shortcut.Arguments = Chr(34) & settingsPath & Chr(34)
shortcut.WorkingDirectory = project
shortcut.IconLocation = iconPath & ",0"
shortcut.Description = "Configure AMD HUD appearance and behavior"
shortcut.Save
WScript.Echo "Updated shortcut: " & shortcutPath

Sub Fail(message)
    WScript.StdErr.WriteLine message
    WScript.Quit 1
End Sub
