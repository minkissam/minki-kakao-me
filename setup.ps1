[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$NoBrowser,
    [int]$Port = 0,
    [string]$RedirectUri
)
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'scripts\kakao_me.py'

# Prefer a working local Python over Store aliases or an unrelated environment.
$candidates = @(
    @{ Command = 'py'; Prefix = @('-3') },
    @{ Command = 'python'; Prefix = @() }
)
foreach ($folder in @(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Directory -ErrorAction SilentlyContinue)) {
    $candidates += @{ Command = (Join-Path $folder.FullName 'python.exe'); Prefix = @() }
}
$runner = $null
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
    try {
        $probe = & $candidate.Command @($candidate.Prefix) -B -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>$null
        if ($LASTEXITCODE -eq 0 -and "$probe".Trim() -eq '1') { $runner = $candidate; break }
    } catch { continue }
}
if (-not $runner) {
    Write-Host 'Python 3.10+ is required. Official installer: https://www.python.org/downloads/windows/'
    Write-Host 'Install for this Windows user, then run setup.ps1 again.'
    Write-Host 'If winget is available: winget install --id Python.Python.3.12 --exact --scope user'
    exit 2
}
$arguments = @($runner.Prefix) + @('-B', '-X', 'utf8', $scriptPath)
if ($Check) { $arguments += 'doctor' }
else {
    $arguments += 'setup'
    if ($NoBrowser) { $arguments += '--no-browser' }
    if ($PSBoundParameters.ContainsKey('Port')) { $arguments += @('--port', "$Port") }
    if ($RedirectUri) { $arguments += @('--redirect-uri', $RedirectUri) }
}
& $runner.Command @arguments
exit $LASTEXITCODE
