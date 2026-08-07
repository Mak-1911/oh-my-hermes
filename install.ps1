<#
    Native Windows installer for oh-my-hermes.

    This is the PowerShell counterpart of install.sh, not a rewrite of it. It
    reads the same OMH_* environment contract, performs the same ordered steps,
    resolves the package source the same way, and hands `omh setup` the same
    argument list, so the two installers stay one documented interface instead
    of two dialects.

    Requires Windows PowerShell 5.1 (shipped with Windows 10/11) or newer.

    Where it deliberately differs from install.sh, and why:

      * A virtual environment exposes Scripts\python.exe, not bin/python.
      * The command is exposed with an omh.cmd shim. A symlink needs Developer
        Mode or elevation on Windows, which an installer must not require.
      * The default venv/bin locations live under %LOCALAPPDATA%, the Windows
        equivalent of the XDG data directory install.sh defaults to.
      * OMH_ADD_TO_PATH defaults to 1. On POSIX, ~/.local/bin is a convention
        most shells already carry on PATH, so install.sh only prints a hint.
        Windows has no such convention, so a hint-only installer would leave
        every user with a command they cannot run. The change is user-scope,
        additive, announced, and reversible; set OMH_ADD_TO_PATH=0 for
        install.sh's hint-only behavior.
      * Installer step labels are English on Windows. OMH_LANG is still
        validated and still forwarded to `omh setup` as --language, so the
        localized surface that carries real content stays localized; this file
        is kept pure ASCII because Windows PowerShell 5.1 decodes a BOM-less
        script as ANSI and would mangle the localized labels.

    Deliberately NOT honored: $env:HOME. Python's ntpath.expanduser resolves ~
    from %USERPROFILE% and ignores HOME on native Windows, so honoring HOME here
    would place the venv somewhere `omh update` and `omh remove` cannot find it.

    Usage:
      irm https://raw.githubusercontent.com/rlaope/oh-my-hermes/main/install.ps1 | iex
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0

if ($PSVersionTable.PSVersion.Major -lt 5) {
    [Console]::Error.WriteLine('omh installer: Windows PowerShell 5.1 or newer is required.')
    exit 1
}

# ---------------------------------------------------------------------------
# Environment contract
# ---------------------------------------------------------------------------

function Get-OmhEnv {
    <#  Mirrors sh's ${VAR:-default}: unset and empty both fall back.  #>
    param([string]$Name, [string]$Default = '')
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($value)) { return $Default }
    return $value
}

function Test-OmhEnvSet {
    <#  Mirrors sh's ${VAR+x}: was the variable assigned at all?  #>
    param([string]$Name)
    return -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($Name))
}

$OmhRepoArchiveRoot = Get-OmhEnv 'OMH_REPO_ARCHIVE_ROOT' 'https://github.com/rlaope/oh-my-hermes/archive/refs'
$OmhChannel         = Get-OmhEnv 'OMH_CHANNEL' 'preview'
$OmhVersion         = Get-OmhEnv 'OMH_VERSION'
$OmhPackageUrl      = Get-OmhEnv 'OMH_PACKAGE_URL'
$OmhSourceRef       = Get-OmhEnv 'OMH_SOURCE_REF'
$OmhPipArgsWasSet   = Test-OmhEnvSet 'OMH_PIP_ARGS'
$OmhPipArgs         = Get-OmhEnv 'OMH_PIP_ARGS'
$OmhInstallMode     = Get-OmhEnv 'OMH_INSTALL_MODE' 'venv'
$OmhLinkCommand     = Get-OmhEnv 'OMH_LINK_COMMAND' '1'
$OmhForceLink       = Get-OmhEnv 'OMH_FORCE_LINK' '0'
$OmhAddToPath       = Get-OmhEnv 'OMH_ADD_TO_PATH' '1'
$OmhRunSetup        = Get-OmhEnv 'OMH_RUN_SETUP' '0'
$OmhAutoApply       = Get-OmhEnv 'OMH_AUTO_APPLY' '1'
$OmhRunDoctor       = Get-OmhEnv 'OMH_RUN_DOCTOR' '1'
$OmhWithPlugin      = Get-OmhEnv 'OMH_WITH_PLUGIN' '0'
$OmhWithMcp         = Get-OmhEnv 'OMH_WITH_MCP' '0'
$OmhProfilePacks    = Get-OmhEnv 'OMH_PROFILE_PACKS'
$OmhSetupProfiles   = Get-OmhEnv 'OMH_SETUP_PROFILES'
$OmhDefaultExecutor = Get-OmhEnv 'OMH_DEFAULT_EXECUTOR'
$OmhScope           = Get-OmhEnv 'OMH_SCOPE'
$OmhSetupArgs       = Get-OmhEnv 'OMH_SETUP_ARGS'

# %USERPROFILE% is the anchor Python itself uses; see the HOME note in the header.
$OmhHomeDir      = Get-OmhEnv 'USERPROFILE'
$OmhLocalAppData = Get-OmhEnv 'LOCALAPPDATA'
$OmhXdgDataHome  = Get-OmhEnv 'XDG_DATA_HOME'

if (Test-OmhEnvSet 'OMH_VENV_DIR') {
    $OmhVenvDir = Get-OmhEnv 'OMH_VENV_DIR'
} elseif ($OmhXdgDataHome) {
    $OmhVenvDir = Join-Path $OmhXdgDataHome 'omh\venv'
} elseif ($OmhLocalAppData) {
    $OmhVenvDir = Join-Path $OmhLocalAppData 'omh\venv'
} elseif ($OmhHomeDir) {
    $OmhVenvDir = Join-Path $OmhHomeDir '.local\share\omh\venv'
} else {
    $OmhVenvDir = ''
}

if (Test-OmhEnvSet 'OMH_BIN_DIR') {
    $OmhBinDir = Get-OmhEnv 'OMH_BIN_DIR'
} elseif ($OmhLocalAppData) {
    $OmhBinDir = Join-Path $OmhLocalAppData 'omh\bin'
} elseif ($OmhHomeDir) {
    $OmhBinDir = Join-Path $OmhHomeDir '.local\bin'
} else {
    $OmhBinDir = ''
}

$OmhLangRaw = Get-OmhEnv 'OMH_LANG'
if (-not $OmhLangRaw) { $OmhLangRaw = Get-OmhEnv 'OMH_LANGUAGE' }
$OmhLangWasSet = [bool]$OmhLangRaw

$OmhRuntimePython = ''
$OmhCommandHint   = ''
$OmhCommandPath   = ''
$OmhPathNote      = ''

$OmhInstallStepCount = if ($OmhInstallMode -eq 'python') { 1 } else { 2 }
$OmhExposeStep = $OmhInstallStepCount + 1
$OmhSetupStep  = $OmhExposeStep + 1
$OmhDoctorStep = $OmhSetupStep + 1
# Computed before OMH_RUN_DOCTOR is consulted, exactly as install.sh does: with
# OMH_RUN_SETUP=1 and OMH_RUN_DOCTOR=0 the labels still read /5.
$OmhTotalSteps = if ($OmhRunSetup -eq '1') { $OmhDoctorStep } else { $OmhExposeStep }

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

# Windows PowerShell 5.1 does not enable ENABLE_VIRTUAL_TERMINAL_PROCESSING on
# the legacy console, so raw ANSI would print as literal escape garbage there.
# Colorize only where VT is known good: PowerShell 7+, or Windows Terminal.
$OmhVtCapable = ($PSVersionTable.PSVersion.Major -ge 6) -or [bool](Get-OmhEnv 'WT_SESSION')
$OmhUseColor = $OmhVtCapable -and (-not (Get-OmhEnv 'NO_COLOR')) -and (-not [Console]::IsOutputRedirected)
$OmhEsc = [char]0x1B

function Write-OmhLine {
    param([string]$Text = '')
    [Console]::Out.WriteLine($Text)
}

function Get-OmhColor {
    param([string]$Code, [string]$Text)
    if ($OmhUseColor) { return "$OmhEsc[${Code}m$Text$OmhEsc[0m" }
    return $Text
}

function Write-OmhHeader {
    param([string]$Title, [string]$Subtitle = '')
    Write-OmhLine (Get-OmhColor '1;36' $Title)
    if ($Subtitle) { Write-OmhLine $Subtitle }
    Write-OmhLine
}

function Write-OmhStep {
    param([string]$Prefix, [string]$Label)
    Write-OmhLine ((Get-OmhColor '1;36' $Prefix) + ' ' + $Label)
}

function Write-OmhOk   { param([string]$Text) Write-OmhLine ('      ' + (Get-OmhColor '1;32' '[ok]') + ' ' + $Text) }
function Write-OmhNote { param([string]$Text) Write-OmhLine ('      ' + (Get-OmhColor '1;33' '[note]') + ' ' + $Text) }
function Write-OmhFail { param([string]$Text) Write-OmhLine ('      ' + (Get-OmhColor '1;31' '[failed]') + ' ' + $Text) }

function Get-OmhStepLabel {
    param([int]$Index)
    return "[$Index/$OmhTotalSteps]"
}

function Stop-OmhInstall {
    param([string[]]$Lines)
    foreach ($line in $Lines) { Write-OmhLine $line }
    exit 1
}

# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

function Get-OmhNormalizedLang {
    <#  Same accepted spellings and same rejection as install.sh.  #>
    param([string]$Raw)
    switch -Regex ($Raw.ToLowerInvariant()) {
        '^(|en|eng|english)$'       { return 'en' }
        '^(ko|kr|kor|korean)$'      { return 'ko' }
        '^(ja|jp|jpn|japanese)$'    { return 'ja' }
        '^(zh|cn|zho|chi|chinese)$' { return 'zh' }
        default {
            [Console]::Error.WriteLine("omh installer: unsupported OMH_LANG $Raw (expected en, ko, ja, or zh).")
            exit 1
        }
    }
}

$OmhLang = Get-OmhNormalizedLang $OmhLangRaw

# English-only by design; see the OMH_LANG note in the file header.
$OmhMessages = @{
    installer_title      = 'OMH installer'
    installer_subtitle   = 'Install oh-my-hermes without touching system Python packages.'
    channel              = 'Channel'
    mode                 = 'Mode'
    step_create_venv     = 'Create isolated Python environment at'
    step_install_package = 'Install OMH package'
    step_install_python  = 'Install OMH package into selected Python'
    step_expose_command  = 'Expose the omh command'
    step_setup           = 'Set up managed Hermes skills (explicit opt-in)'
    step_doctor          = 'Verify installation'
    done                 = 'done'
    installed            = 'oh-my-hermes is installed.'
    next_path            = "Next: run 'omh setup' to connect OMH to Hermes, then 'omh doctor' to verify."
    next_command_path    = "Next: run '{0} setup' to connect OMH to Hermes, then '{0} doctor' to verify, or add its directory to PATH."
}

function Get-OmhMessage {
    param([string]$Key, [string]$Arg = '')
    if (-not $OmhMessages.ContainsKey($Key)) { return $Key }
    $text = $OmhMessages[$Key]
    if ($Arg) { return ($text -f $Arg) }
    return $text
}

# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

function Invoke-OmhCapture {
    <#  Run a native command, capture merged stdout+stderr, return exit code.  #>
    param([string]$FilePath, [string[]]$Arguments = @())
    # PowerShell 7.3+ turns native stderr into a terminating error under
    # $ErrorActionPreference='Stop' when merged with 2>&1, so the merge has to
    # happen with the preference relaxed.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($null -eq $output) { $output = '' }
    if ($null -eq $code) { $code = 0 }
    return [pscustomobject]@{ ExitCode = $code; Output = [string]$output }
}

function Invoke-OmhStep {
    <#  install.sh run_step: capture output, print [ok] or [failed] plus body.  #>
    param([string]$Prefix, [string]$Label, [string]$FilePath, [string[]]$Arguments = @())
    Write-OmhStep $Prefix $Label
    $result = Invoke-OmhCapture -FilePath $FilePath -Arguments $Arguments
    if ($result.ExitCode -eq 0) {
        Write-OmhOk (Get-OmhMessage 'done')
        return
    }
    Write-OmhFail $Label
    if ($result.Output) {
        foreach ($line in ($result.Output -split "`r?`n")) {
            if ($line) { Write-OmhLine ('      ' + $line) }
        }
    }
    exit 1
}

function Invoke-OmhCli {
    <#  install.sh run_omh: always the interpreter, never the exposed shim.  #>
    param([string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $OmhRuntimePython -m omh.cli @Arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { exit $code }
}

function Split-OmhArgString {
    <#  install.sh leans on shell word splitting for the operator escape hatches.  #>
    param([string]$Value)
    if (-not $Value) { return @() }
    return @($Value -split '\s+' | Where-Object { $_ })
}

# ---------------------------------------------------------------------------
# Interpreter resolution
# ---------------------------------------------------------------------------

function Resolve-OmhPython {
    <#
        Return a usable Python 3.11+ command, or exit with guidance.

        The version probe is not caution carried over from install.sh, which has
        none: on Windows, `python` and `python3` routinely resolve to the
        Microsoft Store App Execution Alias stub. That stub is on PATH, runs,
        installs nothing, and exits non-zero -- without this probe the failure
        surfaces several steps later as an unreadable pip error.
    #>
    $explicit = Get-OmhEnv 'OMH_PYTHON'
    if ($explicit) { $candidates = @($explicit) } else { $candidates = @('py', 'python', 'python3') }

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        # Single quotes inside the snippet on purpose: Windows PowerShell 5.1
        # mangles embedded double quotes when building a native command line.
        $probe = Invoke-OmhCapture -FilePath $candidate -Arguments @('-c', 'import sys; print(''%d.%d'' % sys.version_info[:2])')
        if ($probe.ExitCode -ne 0) { continue }
        if ($probe.Output.Trim() -notmatch '(\d+)\.(\d+)') { continue }
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) { return $candidate }
        Stop-OmhInstall @(
            "omh installer: '$candidate' is Python $major.$minor, but oh-my-hermes requires Python 3.11 or newer.",
            'Set OMH_PYTHON to a Python 3.11+ executable and retry.'
        )
    }

    $attempted = $candidates -join ', '
    Stop-OmhInstall @(
        "omh installer: no usable Python was found (tried: $attempted).",
        'Install Python 3.11+ from https://www.python.org/downloads/windows/ or the Microsoft Store,',
        'then set OMH_PYTHON to that executable and retry.'
    )
}

# ---------------------------------------------------------------------------
# Command exposure
# ---------------------------------------------------------------------------

# Same probe source install.sh feeds to Python, so both installers agree on
# where a scripts directory can hide.
$OmhProbeSource = @'
import os
import shutil
import site
import sys
import sysconfig

found = shutil.which("omh")
if found:
    print(found)
    raise SystemExit(0)

names = ["omh.exe"] if os.name == "nt" else ["omh"]
schemes = [sysconfig.get_default_scheme()]
schemes.append("nt_user" if os.name == "nt" else "posix_user")

dirs = []
for directory in sys.argv[1:]:
    if directory and directory not in dirs:
        dirs.append(directory)

for scheme in schemes:
    try:
        path = sysconfig.get_path("scripts", scheme)
    except Exception:
        path = ""
    if path and path not in dirs:
        dirs.append(path)

user_base = getattr(site, "USER_BASE", "")
if user_base:
    user_bin = os.path.join(user_base, "Scripts" if os.name == "nt" else "bin")
    if user_bin not in dirs:
        dirs.append(user_bin)

for directory in dirs:
    for name in names:
        candidate = os.path.join(directory, name)
        if os.path.exists(candidate):
            print(candidate)
            raise SystemExit(0)
'@

function Find-OmhCommand {
    if ($OmhCommandHint -and (Test-Path -LiteralPath $OmhCommandHint)) { return $OmhCommandHint }
    $onPath = Get-Command 'omh' -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    # A temp file rather than `python -c`: Windows PowerShell 5.1 mangles
    # multi-line arguments passed to native executables.
    $probeFile = Join-Path ([System.IO.Path]::GetTempPath()) ('omh-probe-' + [guid]::NewGuid().ToString('N') + '.py')
    try {
        [System.IO.File]::WriteAllText($probeFile, $OmhProbeSource)
        $scriptsDir = if ($OmhVenvDir) { Join-Path $OmhVenvDir 'Scripts' } else { '' }
        $result = Invoke-OmhCapture -FilePath $OmhRuntimePython -Arguments @($probeFile, $OmhBinDir, $scriptsDir)
        if ($result.ExitCode -eq 0) { return $result.Output.Trim() }
        return ''
    } finally {
        Remove-Item -LiteralPath $probeFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-OmhShimBody {
    param([string]$Source)
    return "@echo off`r`n`"$Source`" %*`r`n"
}

function New-OmhCommandShim {
    <#
        install.sh's link_omh_command, with a .cmd shim in place of a symlink.
        Creating a symlink on Windows needs Developer Mode or elevation, so an
        installer that used one would fail for most users.
    #>
    if ($OmhLinkCommand -ne '1') { return }
    if (-not $OmhBinDir) {
        Write-OmhLine 'omh installer: OMH_BIN_DIR is not set, so no omh command shim was created.'
        return
    }
    $source = Join-Path $OmhVenvDir 'Scripts\omh.exe'
    if (-not (Test-Path -LiteralPath $source)) { return }

    New-Item -ItemType Directory -Force -Path $OmhBinDir | Out-Null
    $target = Join-Path $OmhBinDir 'omh.cmd'
    $body = Get-OmhShimBody -Source $source

    if (Test-Path -LiteralPath $target) {
        $existing = [System.IO.File]::ReadAllText($target)
        if ($existing -eq $body) {
            $script:OmhCommandHint = $target
            return
        }
        if ($OmhForceLink -eq '1') {
            [System.IO.File]::WriteAllText($target, $body)
            $script:OmhCommandHint = $target
            return
        }
        Write-OmhLine "omh installer: $target already exists, so it was not replaced."
        Write-OmhLine "Set OMH_FORCE_LINK=1 to replace it, or use: $source"
        $script:OmhCommandHint = $source
        return
    }

    [System.IO.File]::WriteAllText($target, $body)
    $script:OmhCommandHint = $target
}

function Add-OmhBinDirToPath {
    <#
        Append the bin directory to the user-scope PATH when it is missing.

        User scope only: the machine PATH needs elevation and would change other
        accounts. The process PATH is updated too, so `omh` resolves in the very
        shell that ran the installer without reopening it.
    #>
    if ($OmhAddToPath -ne '1') { return }
    if (-not $OmhBinDir) { return }
    if (-not (Test-Path -LiteralPath $OmhBinDir)) { return }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($null -eq $userPath) { $userPath = '' }
    $normalized = $OmhBinDir.TrimEnd('\')
    foreach ($entry in ($userPath -split ';' | Where-Object { $_ })) {
        if ($entry.TrimEnd('\') -ieq $normalized) {
            $script:OmhPathNote = 'already-present'
            return
        }
    }

    $updated = if ($userPath) { $userPath.TrimEnd(';') + ';' + $OmhBinDir } else { $OmhBinDir }
    try {
        [Environment]::SetEnvironmentVariable('Path', $updated, 'User')
    } catch {
        $script:OmhPathNote = 'failed'
        return
    }
    $env:PATH = $env:PATH.TrimEnd(';') + ';' + $OmhBinDir
    $script:OmhPathNote = 'added'
}

# ---------------------------------------------------------------------------
# Install modes
# ---------------------------------------------------------------------------

function Get-OmhPipArguments {
    param([string[]]$Extra = @())
    return @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '--no-cache-dir', '--force-reinstall') +
        $Extra + @('--upgrade', $OmhPackageUrl)
}

function Install-OmhIntoVenv {
    if (-not $OmhVenvDir) {
        Stop-OmhInstall @(
            'omh installer: USERPROFILE, LOCALAPPDATA, or XDG_DATA_HOME is required for default venv install.',
            'Set OMH_VENV_DIR to an explicit directory and retry.'
        )
    }
    $createLabel = (Get-OmhMessage 'step_create_venv') + ' ' + $OmhVenvDir
    Invoke-OmhStep -Prefix (Get-OmhStepLabel 1) -Label $createLabel -FilePath $OmhRuntimePython -Arguments @('-m', 'venv', $OmhVenvDir)

    $script:OmhRuntimePython = Join-Path $OmhVenvDir 'Scripts\python.exe'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    Invoke-OmhStep -Prefix (Get-OmhStepLabel 2) -Label (Get-OmhMessage 'step_install_package') `
        -FilePath $OmhRuntimePython -Arguments (Get-OmhPipArguments -Extra (Split-OmhArgString $OmhPipArgs))

    $script:OmhCommandHint = Join-Path $OmhVenvDir 'Scripts\omh.exe'
    New-OmhCommandShim
    Add-OmhBinDirToPath
}

function Install-OmhIntoPython {
    $extra = Split-OmhArgString $OmhPipArgs
    if (-not $OmhPipArgsWasSet) { $extra = @('--user') }
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    Invoke-OmhStep -Prefix (Get-OmhStepLabel 1) -Label (Get-OmhMessage 'step_install_python') `
        -FilePath $OmhRuntimePython -Arguments (Get-OmhPipArguments -Extra $extra)
}

# ---------------------------------------------------------------------------
# Package source resolution
# ---------------------------------------------------------------------------

function Get-OmhNormalizedTag {
    param([string]$Version)
    if ($Version.StartsWith('v')) { return $Version }
    return "v$Version"
}

$OmhRuntimePython = Resolve-OmhPython

if (-not $OmhPackageUrl) {
    switch ($OmhChannel) {
        'preview' {
            $OmhPackageUrl = "$OmhRepoArchiveRoot/heads/main.zip"
            if (-not $OmhSourceRef) { $OmhSourceRef = 'main' }
        }
        'stable' {
            if (-not $OmhVersion) {
                Stop-OmhInstall @('omh installer: OMH_CHANNEL=stable requires OMH_VERSION, for example OMH_VERSION=1.0.1.')
            }
            $OmhTag = Get-OmhNormalizedTag $OmhVersion
            $OmhPackageUrl = "$OmhRepoArchiveRoot/tags/$OmhTag.zip"
            if (-not $OmhSourceRef) { $OmhSourceRef = $OmhTag }
        }
        'local' {
            Stop-OmhInstall @('omh installer: OMH_CHANNEL=local requires OMH_PACKAGE_URL to point at a local archive or path accepted by pip.')
        }
        default {
            Stop-OmhInstall @("omh installer: unsupported OMH_CHANNEL '$OmhChannel' (expected preview, stable, or local).")
        }
    }
} elseif (-not $OmhSourceRef) {
    switch ($OmhChannel) {
        'local'   { $OmhSourceRef = 'local' }
        'stable'  { $OmhSourceRef = if ($OmhVersion) { Get-OmhNormalizedTag $OmhVersion } else { 'custom-url' } }
        'preview' { $OmhSourceRef = 'main' }
        default   { $OmhSourceRef = 'custom-url' }
    }
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

Write-OmhHeader (Get-OmhMessage 'installer_title') (Get-OmhMessage 'installer_subtitle')
Write-OmhNote ((Get-OmhMessage 'channel') + ': ' + $OmhChannel)
Write-OmhNote "Source ref: $OmhSourceRef"
Write-OmhNote ((Get-OmhMessage 'mode') + ': ' + $OmhInstallMode)

switch ($OmhInstallMode) {
    'venv'   { Install-OmhIntoVenv }
    'python' { Install-OmhIntoPython }
    default  {
        Stop-OmhInstall @("omh installer: unsupported OMH_INSTALL_MODE '$OmhInstallMode' (expected venv or python).")
    }
}

$OmhCommandPath = Find-OmhCommand
if ($OmhCommandPath) {
    Write-OmhStep (Get-OmhStepLabel $OmhExposeStep) (Get-OmhMessage 'step_expose_command')
    Write-OmhOk $OmhCommandPath
    if ($OmhPathNote -eq 'added') {
        Write-OmhNote "Added '$OmhBinDir' to your user PATH."
        Write-OmhNote 'Other shells see it after they are reopened. Set OMH_ADD_TO_PATH=0 to skip this next time.'
    } elseif ($OmhPathNote -eq 'failed') {
        Write-OmhNote "Could not update the user PATH. Add '$OmhBinDir' to it manually."
    }
    if (-not (Get-Command 'omh' -ErrorAction SilentlyContinue)) {
        $OmhCommandDir = Split-Path -Parent $OmhCommandPath
        Write-OmhNote "'$OmhCommandDir' is not on PATH for this shell."
        Write-OmhNote "Add it with: `$env:PATH = `"$OmhCommandDir;`$env:PATH`""
        Write-OmhNote "Until then, use: $OmhCommandPath setup"
    }
} else {
    Write-OmhLine 'omh installer: installed the package, but could not locate the omh command.'
    Write-OmhLine "Use '$OmhRuntimePython -m omh.cli setup' as a fallback and check the selected Python scripts directory."
}

if ($OmhRunSetup -eq '1') {
    $OmhSetupArgv = @('setup', '--channel', $OmhChannel, '--package-url', $OmhPackageUrl, '--source-ref', $OmhSourceRef, '--command-package-updated')

    if ($OmhLangWasSet) { $OmhSetupArgv += @('--language', $OmhLang) }
    if ($OmhChannel -eq 'local' -and (Test-Path -LiteralPath $OmhPackageUrl -PathType Container)) {
        $OmhSetupArgv += @('--source', $OmhPackageUrl)
    }
    if ($OmhAutoApply -eq '0')  { $OmhSetupArgv += '--skip-apply' }
    if ($OmhVersion)            { $OmhSetupArgv += @('--version', $OmhVersion) }
    if ($OmhWithPlugin -eq '1') { $OmhSetupArgv += '--with-plugin' }
    if ($OmhWithMcp -eq '1')    { $OmhSetupArgv += '--with-mcp' }
    if ($OmhScope)              { $OmhSetupArgv += @('--scope', $OmhScope) }
    foreach ($OmhProfilePack in ($OmhProfilePacks -split ',' | Where-Object { $_ })) {
        $OmhSetupArgv += @('--profile-pack', $OmhProfilePack)
    }
    foreach ($OmhSetupProfile in ($OmhSetupProfiles -split ',' | Where-Object { $_ })) {
        $OmhSetupArgv += @('--profile', $OmhSetupProfile)
    }
    if ($OmhDefaultExecutor) { $OmhSetupArgv += @('--default-executor', $OmhDefaultExecutor) }
    $OmhSetupArgv += (Split-OmhArgString $OmhSetupArgs)

    Write-OmhStep (Get-OmhStepLabel $OmhSetupStep) (Get-OmhMessage 'step_setup')
    Invoke-OmhCli $OmhSetupArgv

    if ($OmhRunDoctor -eq '0') {
        Write-OmhNote 'Skipped doctor check because OMH_RUN_DOCTOR=0.'
    } else {
        Write-OmhStep (Get-OmhStepLabel $OmhDoctorStep) (Get-OmhMessage 'step_doctor')
        if ($OmhScope) { Invoke-OmhCli @('--scope', $OmhScope, 'doctor') } else { Invoke-OmhCli @('doctor') }
    }
} elseif ($OmhAutoApply -eq '0' -or $OmhWithPlugin -eq '1' -or $OmhWithMcp -eq '1' -or $OmhScope -or
          $OmhProfilePacks -or $OmhSetupProfiles -or $OmhDefaultExecutor -or $OmhSetupArgs -or $OmhRunDoctor -eq '0') {
    Write-OmhNote 'Setup options were not applied because install.ps1 installs the command only by default.'
    Write-OmhNote "Run 'omh setup' with those choices explicitly, or set OMH_RUN_SETUP=1 for advanced one-shot bootstrap."
}

Write-OmhLine
Write-OmhLine (Get-OmhColor '1;36' (Get-OmhMessage 'installed'))
if (Get-Command 'omh' -ErrorAction SilentlyContinue) {
    Write-OmhLine (Get-OmhMessage 'next_path')
} elseif ($OmhCommandPath) {
    Write-OmhLine (Get-OmhMessage 'next_command_path' $OmhCommandPath)
} else {
    Write-OmhLine "Next: run '$OmhRuntimePython -m omh.cli setup' to connect OMH to Hermes, then '$OmhRuntimePython -m omh.cli doctor' to verify."
}
