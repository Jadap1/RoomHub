if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    throw "Activate the ESP-IDF PowerShell environment before building."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& idf.py build @args
exit $LASTEXITCODE
