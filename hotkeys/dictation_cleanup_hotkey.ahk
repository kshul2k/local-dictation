#Requires AutoHotkey v2.0

^!v::{
    projectDir := A_ScriptDir "\.."
    EnvSet("PYTHONPYCACHEPREFIX", projectDir "\cache\pycache")
    pythonExe := projectDir "\.venv\Scripts\python.exe"
    clientScript := projectDir "\src\clean_clipboard_and_paste.py"
    RunWait('"' pythonExe '" "' clientScript '"', , "Hide")
}
