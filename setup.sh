#!/bin/bash
# ──────────────────────────────────────────────
# CVE-2025-33073 Exploit Chain — Setup Script
# ──────────────────────────────────────────────
# Creates a Python venv, installs dependencies,
# and verifies required system tools.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
BOLD='\033[1m'
RST='\033[0m'

echo -e "${BOLD}${CYAN}CVE-2025-33073 Exploit Chain — Setup${RST}"
echo "──────────────────────────────────────"

# ── Check Python 3 ──
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[!] python3 not found. Install it first.${RST}"
    exit 1
fi
PY_VER=$(python3 --version 2>&1)
echo -e "${GREEN}[+]${RST} ${PY_VER}"

# ── Create venv ──
if [ -d "${VENV_DIR}" ]; then
    echo -e "${YELLOW}[*]${RST} venv already exists at ${VENV_DIR}"
else
    echo -e "[*] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    echo -e "${GREEN}[+]${RST} venv created at ${VENV_DIR}"
fi

# ── Activate and install deps ──
source "${VENV_DIR}/bin/activate"

echo "[*] Upgrading pip..."
pip install --upgrade pip --quiet

# ── requirements.txt (create if missing) ──
REQ_FILE="${SCRIPT_DIR}/requirements.txt"
if [ ! -f "${REQ_FILE}" ]; then
    echo "[*] Creating requirements.txt..."
    cat > "${REQ_FILE}" <<EOF
ldap3>=2.9
dnspython>=2.3
impacket>=0.11
pycryptodomex
EOF
    echo -e "${GREEN}[+]${RST} requirements.txt created"
fi

echo "[*] Installing Python dependencies..."
pip install -r "${REQ_FILE}" --quiet
echo -e "${GREEN}[+]${RST} Python dependencies installed"

# ── Check for dnstool.py ──
if [ -f "${SCRIPT_DIR}/dnstool.py" ]; then
    echo -e "${GREEN}[+]${RST} dnstool.py found"
else
    echo -e "${YELLOW}[*]${RST} dnstool.py not found. Downloading from dirkjanm/krbrelayx..."
    if command -v curl &>/dev/null; then
        curl -sL "https://raw.githubusercontent.com/dirkjanm/krbrelayx/master/dnstool.py" \
            -o "${SCRIPT_DIR}/dnstool.py"
    elif command -v wget &>/dev/null; then
        wget -q "https://raw.githubusercontent.com/dirkjanm/krbrelayx/master/dnstool.py" \
            -O "${SCRIPT_DIR}/dnstool.py"
    else
        echo -e "${RED}[!] Neither curl nor wget found. Download dnstool.py manually.${RST}"
    fi

    if [ -f "${SCRIPT_DIR}/dnstool.py" ]; then
        echo -e "${GREEN}[+]${RST} dnstool.py downloaded"
    fi
fi

# ── Check system tools ──
echo ""
echo "Checking system tools..."
MISSING=0

check_tool() {
    if command -v "$1" &>/dev/null; then
        echo -e "  ${GREEN}✓${RST} $1 $(command -v "$1")"
    else
        echo -e "  ${RED}✗${RST} $1 — $2"
        MISSING=1
    fi
}

check_tool "nxc"                  "Install: pipx install netexec"
check_tool "impacket-ntlmrelayx"  "Install: pipx install impacket (or pip install impacket)"
check_tool "dig"                  "Install: apt install dnsutils"
check_tool "tcpdump"              "Install: apt install tcpdump (optional, for --capture)"
check_tool "ss"                   "Should be preinstalled (iproute2)"

echo ""
if [ "${MISSING}" -eq 1 ]; then
    echo -e "${YELLOW}[*]${RST} Some tools are missing. Install them before running the exploit."
else
    echo -e "${GREEN}[+]${RST} All tools found."
fi

echo ""
echo -e "${BOLD}Setup complete.${RST} Activate the venv before running:"
echo ""
echo -e "  ${CYAN}source ${VENV_DIR}/bin/activate${RST}"
echo -e "  ${CYAN}python3 exploit_trace.py --help${RST}"
echo ""
