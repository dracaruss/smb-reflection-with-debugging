# ──────────────────────────────────────────────
# smb_no_signing_gg — Windows Setup Script
# ──────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir = Join-Path $ScriptDir "venv"

# ═══════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════
function Write-Status($Icon, $Color, $Message) {
    Write-Host "  " -NoNewline
    Write-Host $Icon -ForegroundColor $Color -NoNewline
    Write-Host " $Message"
}

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-NtlmRelayx {
    return (Test-Command "impacket-ntlmrelayx") -or
           (Test-Command "ntlmrelayx.py") -or
           (Test-Command "ntlmrelayx")
}

# ═══════════════════════════════════════════════
# Banner
# ═══════════════════════════════════════════════
Write-Host ""
Write-Host "  smb_no_signing_gg - Windows Setup" -ForegroundColor Cyan
Write-Host "  ──────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ═══════════════════════════════════════════════
# Python check
# ═══════════════════════════════════════════════
$PythonCmd = $null
foreach ($candidate in @("python3", "python")) {
    if (Test-Command $candidate) {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3") {
            $PythonCmd = $candidate
            break
        }
    }
}

if (-not $PythonCmd) {
    Write-Status "[!]" Red "Python 3 not found. Install it from https://python.org and ensure it is on PATH."
    exit 1
}
Write-Status "[+]" Green "$(& $PythonCmd --version 2>&1)"

# ═══════════════════════════════════════════════
# System tool checks (no apt on Windows, just report)
# ═══════════════════════════════════════════════
Write-Host ""
Write-Host "  Checking system tools..." -ForegroundColor White

# dig (comes with BIND or via choco install bind-toolsonly)
if (Test-Command "dig") {
    Write-Status "[+]" Green "dig already installed"
} else {
    Write-Status "[*]" Yellow "dig not found. Install via: choco install bind-toolsonly"
    Write-Host "       Or use nslookup as a fallback for DNS verification." -ForegroundColor DarkGray
}

# Wireshark/tshark (Windows equivalent of tcpdump for --capture)
if (Test-Command "tshark") {
    Write-Status "[+]" Green "tshark (Wireshark CLI) found"
} elseif (Test-Command "dumpcap") {
    Write-Status "[+]" Green "dumpcap (Wireshark) found"
} else {
    Write-Status "[*]" Yellow "tshark/dumpcap not found. Install Wireshark for --capture support."
    Write-Host "       https://www.wireshark.org/download.html" -ForegroundColor DarkGray
}

# git
if (-not (Test-Command "git")) {
    Write-Status "[!]" Red "git not found. Install from https://git-scm.com or: winget install Git.Git"
    Write-Host "       git is required to download dnstool.py." -ForegroundColor DarkGray
}

# ═══════════════════════════════════════════════
# Create venv
# ═══════════════════════════════════════════════
Write-Host ""
if (Test-Path $VenvDir) {
    Write-Status "[*]" Yellow "venv already exists at $VenvDir"
} else {
    Write-Host "  [*] Creating virtual environment..." -ForegroundColor White
    & $PythonCmd -m venv $VenvDir
    Write-Status "[+]" Green "venv created"
}

# Activate venv
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"

if (-not (Test-Path $VenvPython)) {
    Write-Status "[!]" Red "venv python not found at $VenvPython"
    exit 1
}

# Upgrade pip inside venv
Write-Host "  [*] Upgrading pip..." -ForegroundColor White
& $VenvPython -m pip install --upgrade pip --quiet 2>$null
Write-Status "[+]" Green "pip upgraded"

# ═══════════════════════════════════════════════
# Requirements
# ═══════════════════════════════════════════════
$ReqFile = Join-Path $ScriptDir "requirements.txt"
if (-not (Test-Path $ReqFile)) {
    @"
ldap3>=2.9
dnspython>=2.3
impacket>=0.11
pycryptodomex
"@ | Set-Content -Path $ReqFile -Encoding UTF8
}

Write-Host "  [*] Installing Python dependencies into venv..." -ForegroundColor White
& $VenvPip install -r $ReqFile --quiet 2>$null
Write-Status "[+]" Green "Python dependencies installed"

# ═══════════════════════════════════════════════
# impacket / ntlmrelayx (install into venv if missing globally)
# ═══════════════════════════════════════════════
Write-Host ""
$VenvNtlmRelayx = Join-Path $VenvDir "Scripts\ntlmrelayx.exe"
$VenvNtlmRelayx2 = Join-Path $VenvDir "Scripts\impacket-ntlmrelayx.exe"

if ((Test-NtlmRelayx) -or (Test-Path $VenvNtlmRelayx) -or (Test-Path $VenvNtlmRelayx2)) {
    Write-Status "[+]" Green "impacket (ntlmrelayx) available"
} else {
    Write-Host "  [*] Installing impacket into venv..." -ForegroundColor White
    & $VenvPip install impacket --quiet 2>$null
    if ((Test-Path $VenvNtlmRelayx) -or (Test-Path $VenvNtlmRelayx2)) {
        Write-Status "[+]" Green "impacket installed into venv"
    } else {
        Write-Status "[!]" Red "impacket install may have failed. Run manually: .\venv\Scripts\pip install impacket"
    }
}

# ═══════════════════════════════════════════════
# netexec (nxc)
# ═══════════════════════════════════════════════
$VenvNxc = Join-Path $VenvDir "Scripts\nxc.exe"

if ((Test-Command "nxc") -or (Test-Path $VenvNxc)) {
    Write-Status "[+]" Green "netexec (nxc) available"
} else {
    Write-Host "  [*] Installing netexec into venv..." -ForegroundColor White
    & $VenvPip install netexec --quiet 2>$null
    if (Test-Path $VenvNxc) {
        Write-Status "[+]" Green "netexec installed into venv"
    } else {
        Write-Status "[!]" Red "netexec install may have failed. Run manually: .\venv\Scripts\pip install netexec"
    }
}

# ═══════════════════════════════════════════════
# dnstool.py (clone krbrelayx for lib/ imports)
# ═══════════════════════════════════════════════
Write-Host ""
$DnsTool = Join-Path $ScriptDir "dnstool.py"
$LibDir  = Join-Path $ScriptDir "lib"

if ((Test-Path $DnsTool) -and (Test-Path $LibDir)) {
    Write-Status "[+]" Green "dnstool.py and lib/ found"
} else {
    Write-Host "  [*] Cloning krbrelayx repo (dnstool.py needs lib/ directory)..." -ForegroundColor White

    # Clean up any broken standalone dnstool.py
    if (Test-Path $DnsTool) { Remove-Item $DnsTool -Force }

    if (Test-Command "git") {
        $KrbrelaxyDir = Join-Path $ScriptDir "krbrelayx"
        git clone --depth 1 https://github.com/dirkjanm/krbrelayx.git $KrbrelaxyDir 2>$null

        if (Test-Path $KrbrelaxyDir) {
            Copy-Item (Join-Path $KrbrelaxyDir "dnstool.py") -Destination $ScriptDir
            Copy-Item (Join-Path $KrbrelaxyDir "lib") -Destination $ScriptDir -Recurse
            Remove-Item $KrbrelaxyDir -Recurse -Force
            Write-Status "[+]" Green "dnstool.py and lib/ installed from krbrelayx"
        } else {
            Write-Status "[!]" Red "Git clone failed. Clone manually: git clone https://github.com/dirkjanm/krbrelayx.git"
        }
    } else {
        Write-Status "[!]" Red "git not found. Install git and re-run, or clone krbrelayx manually."
    }
}

# ═══════════════════════════════════════════════
# Final verification
# ═══════════════════════════════════════════════
Write-Host ""
Write-Host "  Verifying all tools..." -ForegroundColor White
$AllGood = $true

# Check global or venv availability for each tool
$checks = @(
    @{ Name = "nxc";   Venv = (Join-Path $VenvDir "Scripts\nxc.exe") },
    @{ Name = "dig";   Venv = $null },
    @{ Name = "tshark"; Venv = $null }
)

foreach ($check in $checks) {
    $found = (Test-Command $check.Name) -or ($check.Venv -and (Test-Path $check.Venv))
    if ($found) {
        Write-Status ([char]0x2713) Green $check.Name
    } else {
        Write-Status ([char]0x2717) Red "$($check.Name) (optional)"
        # Don't fail on optional tools
    }
}

# ntlmrelayx (multiple binary names)
$relayFound = $false
foreach ($bin in @("impacket-ntlmrelayx", "ntlmrelayx.py", "ntlmrelayx")) {
    if (Test-Command $bin) {
        Write-Status ([char]0x2713) Green "ntlmrelayx ($bin, global)"
        $relayFound = $true
        break
    }
}
if (-not $relayFound) {
    foreach ($bin in @("impacket-ntlmrelayx.exe", "ntlmrelayx.exe")) {
        $venvBin = Join-Path $VenvDir "Scripts\$bin"
        if (Test-Path $venvBin) {
            Write-Status ([char]0x2713) Green "ntlmrelayx ($bin, venv)"
            $relayFound = $true
            break
        }
    }
}
if (-not $relayFound) {
    Write-Status ([char]0x2717) Red "ntlmrelayx"
    $AllGood = $false
}

# dnstool.py
if (Test-Path $DnsTool) {
    Write-Status ([char]0x2713) Green "dnstool.py"
} else {
    Write-Status ([char]0x2717) Red "dnstool.py"
    $AllGood = $false
}

# ═══════════════════════════════════════════════
# Done
# ═══════════════════════════════════════════════
Write-Host ""
if ($AllGood) {
    Write-Host "  Setup complete. Everything is ready." -ForegroundColor Green
} else {
    Write-Host "  Setup complete with warnings." -ForegroundColor Yellow
    Write-Host "  Check the missing tools above." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Activate the venv first:" -ForegroundColor DarkGray
Write-Host "    .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Then run:" -ForegroundColor DarkGray
Write-Host "    python smb_no_signing_gg.py --help" -ForegroundColor Cyan
Write-Host ""
