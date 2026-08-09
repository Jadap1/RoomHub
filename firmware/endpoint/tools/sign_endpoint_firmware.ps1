param(
    [Parameter(Mandatory = $true)]
    [string]$KeyPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
if (-not $env:IDF_PATH) {
    throw "Activate the ESP-IDF PowerShell environment before signing."
}
$resolvedKey = (Resolve-Path -LiteralPath $KeyPath).Path
$inputImage = Join-Path $PSScriptRoot "..\build\roomhub_endpoint.bin"
if (-not (Test-Path -LiteralPath $inputImage)) {
    throw "Build the endpoint firmware before signing."
}
python (Join-Path $env:IDF_PATH "components\esptool_py\esptool\espsecure.py") `
    sign_data --version 2 --keyfile $resolvedKey --output $OutputPath $inputImage
if ($LASTEXITCODE -ne 0) {
    throw "Firmware signing failed."
}
