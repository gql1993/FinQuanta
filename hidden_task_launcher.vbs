Option Explicit

Dim shell, fso, scriptPath, command, i, arg

If WScript.Arguments.Count < 1 Then
  WScript.Quit 2
End If

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptPath = WScript.Arguments(0)
If fso.FileExists(scriptPath) Then
  shell.CurrentDirectory = fso.GetParentFolderName(scriptPath)
End If

command = """" & scriptPath & """"
For i = 1 To WScript.Arguments.Count - 1
  arg = WScript.Arguments(i)
  command = command & " " & """" & Replace(arg, """", "'") & """"
Next

shell.Run command, 0, False
