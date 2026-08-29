' ============================================================================
' sync_agent_hidden.vbs - uruchamia sync_agent_run.bat BEZ okna konsoli.
'
' Task Scheduler odpalajacy .bat zawsze mignie oknem cmd.exe - ustawienie
' "Hidden" w zadaniu tego NIE ukrywa (dotyczy okna samego zadania, nie procesu
' potomnego). Jedyny pewny sposob bez dodatkowych narzedzi: wscript.exe
' uruchamia batcha z parametrem widocznosci 0.
'
' Zadanie w Schedulerze wskazuje na TEN plik, nie na .bat:
'   wscript.exe "...\sync_agent_hidden.vbs"
'
' Ten plik jest w repo (nie ma w nim zadnych sciezek per-maszyna) - sciezki
' rozwiazuje sam .bat, po hostname.
' ============================================================================

Dim fso, shell, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' .bat lezy zawsze obok tego skryptu
batPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\sync_agent_run.bat"

If Not fso.FileExists(batPath) Then
    ' Cicho konczymy z bledem - Scheduler zapisze niezerowy kod wyniku.
    ' Bez MsgBox: to leci co minute, okienko bledu byloby gorsze od problemu.
    WScript.Quit 1
End If

' 0 = okno ukryte, True = czekaj na zakonczenie (Scheduler dostanie kod wyjscia)
WScript.Quit shell.Run("""" & batPath & """", 0, True)
