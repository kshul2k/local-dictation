#Requires AutoHotkey v2.0

; Use this only when the same hotkey also controls OpenWhispr/WhisperFlow.
; The "~" prefix lets the keypress pass through to the dictation app.
; The "Up" suffix runs cleanup after releasing the hotkey, which fits push-to-talk.
~^!v Up::{
    projectDir := A_ScriptDir "\.."
    EnvSet("PYTHONPYCACHEPREFIX", projectDir "\cache\pycache")
    pythonExe := projectDir "\.venv\Scripts\python.exe"
    clientScript := projectDir "\src\clean_clipboard_and_paste.py"
    RunWait('"' pythonExe '" "' clientScript '" --wait-for-clipboard-change --wait-timeout 15', , "Hide")
}
