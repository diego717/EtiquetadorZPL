Attribute VB_Name = "ClientAssetsPrepare"
Option Explicit

Private Const SHOW_TEST_MESSAGE As Boolean = False

' Modulo base para ser llamado desde la API local:
' corel_macro.module_name = "ClientAssetsPrepare"
' corel_macro.entrypoint = "PrepareClientAsset"
'
' La idea es mover aqui la logica mas sensible a Corel 24, drivers y perfiles reales.
' Si esta macro no logra aplicar nada util, conviene que lance error para que la API
' pueda usar el fallback actual via COM.

Public Sub PrepareTarjetasPlasticas()
    PrepareClientAsset "tarjetas_plasticas"
End Sub

Public Sub PrepareTarjetasLaminarTintaA()
    PrepareClientAsset "tarjetas_laminar_tinta_a"
End Sub

Public Sub PrepareTarjetasLaminarTintaB()
    PrepareClientAsset "tarjetas_laminar_tinta_b"
End Sub

Public Sub PrepareClientAsset(ByVal profileId As String)
    Dim normalizedProfile As String
    Dim doc As Object
    Dim appliedCount As Long

    normalizedProfile = LCase$(Trim$(profileId))
    Set doc = ActiveDocument

    If SHOW_TEST_MESSAGE Then
        MsgBox "Macro OK: " & profileId, vbInformation, "ClientAssetsPrepare"
    End If

    If doc Is Nothing Then
        Err.Raise vbObjectError + 1000, "ClientAssetsPrepare", "No hay documento activo en CorelDRAW."
    End If

    doc.Activate

    Select Case normalizedProfile
        Case "tarjetas_plasticas"
            appliedCount = ApplyProfileValues(doc, _
                "", _
                "", _
                "landscape", _
                "")

        Case "tarjetas_laminar_tinta_a"
            appliedCount = ApplyProfileValues(doc, _
                "EPSON L1250 Series A", _
                "A4", _
                "portrait", _
                "")

        Case "tarjetas_laminar_tinta_b"
            appliedCount = ApplyProfileValues(doc, _
                "EPSON L1250 Series B", _
                "A4", _
                "portrait", _
                "")

        Case Else
            Err.Raise vbObjectError + 1001, "ClientAssetsPrepare", "Perfil no soportado: " & profileId
    End Select

    If appliedCount <= 0 Then
        Err.Raise vbObjectError + 1002, "ClientAssetsPrepare", _
            "La macro se ejecuto, pero no pudo aplicar ningun ajuste. Revisar nombres de propiedades o drivers."
    End If
End Sub

Private Function ApplyProfileValues( _
    ByVal doc As Object, _
    ByVal printerName As String, _
    ByVal paperName As String, _
    ByVal orientation As String, _
    ByVal printProfileName As String) As Long

    Dim appliedCount As Long

    appliedCount = appliedCount + TryApplySetting(doc, "PrinterName", printerName)
    appliedCount = appliedCount + TryApplySetting(doc, "PaperName", paperName)
    appliedCount = appliedCount + TryApplySetting(doc, "Orientation", orientation)
    appliedCount = appliedCount + TryApplySetting(doc, "PrintProfileName", printProfileName)

    ApplyProfileValues = appliedCount
End Function

Private Function TryApplySetting(ByVal doc As Object, ByVal propertyName As String, ByVal rawValue As String) As Long
    Dim valueToApply As String

    valueToApply = Trim$(rawValue)
    If Len(valueToApply) = 0 Then
        Exit Function
    End If

    If TrySetNestedProperty(doc, "PrintSettings", propertyName, valueToApply) Then
        TryApplySetting = 1
        Exit Function
    End If

    If TrySetNestedProperty(Application, "PrintSettings", propertyName, valueToApply) Then
        TryApplySetting = 1
        Exit Function
    End If
End Function

Private Function TrySetNestedProperty(ByVal hostObject As Object, ByVal nestedName As String, ByVal propertyName As String, ByVal valueToApply As String) As Boolean
    Dim nestedObject As Object

    On Error Resume Next
    Set nestedObject = CallByName(hostObject, nestedName, VbGet)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If

    CallByName nestedObject, propertyName, VbLet, valueToApply
    If Err.Number = 0 Then
        TrySetNestedProperty = True
    Else
        Err.Clear
    End If
    On Error GoTo 0
End Function
