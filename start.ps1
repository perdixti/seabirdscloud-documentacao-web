param([string]$Python = "python", [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente. Use Python 3.12 ou 3.13.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências.' }
Write-Host "Abra http://127.0.0.1:$Port no navegador. Ctrl+C encerra o servidor."
& '.\.venv\Scripts\python.exe' -m seabirds --port $Port
