' TestSAPConnection.vbs
' This is a script to verify if using SAPGUI is possible, while we won't have access to the SAP, the operator's credentials allows them to access SAP and should give us a way to extract data.

Option Explicit

Dim SapGuiAuto, Application, Connection, Session
Dim UserName, SystemName

On Error Resume Next

' Need to log in to SAP, Otherwise it will fail, depending on what the window is called, might have to change the getobject, but it is probably SAPGUI or SAP, have to confirm with Deepak or thoravi
Set SapGuiAuto = GetObject("SAPGUI")
If Err.Number <> 0 Then
    MsgBox "Could not find SAP GUI. Please open SAP and log in first.", vbCritical, "SAP Not Found"
    WScript.Quit
End If

' this will check if SAP scripting is available, if not we will have to go for a different way to access the daily prod plan
Set Application = SapGuiAuto.GetScriptingEngine
If Err.Number <> 0 Then
    MsgBox "Scripting is disabled on this machine.", vbCritical, "Scripting Disabled"
    WScript.Quit
End If

' this is if the getobject works but operator is not logged on
If Application.Children.Count = 0 Then
    MsgBox "No active connection found. Please log in to SAP.", vbExclamation, "No Connection"
    WScript.Quit
End If

Set Connection = Application.Children(0)
Set Session = Connection.Children(0)

' Extract Read-Only Data to show on the success message
UserName = Session.Info.User
SystemName = Session.Info.SystemName

' Success Message - if everything else went okay, this will give us a success message
MsgBox "SUCCESS! SAP GUI Scripting is ENABLED." & vbCrLf & vbCrLf & _
       "Connected to System: " & SystemName & vbCrLf & _
       "Logged in User: " & UserName & vbCrLf & vbCrLf & _
       "SAPGUI should be viable option for data extraction.", vbInformation, "Test Passed"