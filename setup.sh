#!/bin/bash
# ──────────────────────────────────────────────
# smb_no_signing_gg — Setup Script
# ──────────────────────────────────────────────
# Installs everything needed. No manual steps.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
BOLD='\033[1m'
RST='\033[0m'

echo -e "${BOLD}${CYAN}smb_no_signing_gg — Setup${RST}"
echo "──────────────────────────────────────"

# ── Check Python 3 ──
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[!] python3 not found. Install it first.${RST}"
    exit 1
fi
PY_VER=$(python3 --version 2>&1)
echo -e "${GREEN}[+]${RST} ${PY_VER}"

# ── Install system tools automatically ──
echo ""
echo -e "${BOLD}Installing system dependencies...${RST}"

if ! command -v dig &>/dev/null; then
    echo "[*] Installing dnsutils (dig)..."
    apt install -y dnsutils > /dev/null 2>&1
    if command -v dig &>/dev/null; then
        echo -e "${GREEN}[+]${RST} dig installed"
    else
        echo -e "${RED}[!]${RST} dig install failed. Run: apt install dnsutils"
    fi
else
    echo -e "${GREEN}[+]${RST} dig already installed"
fi

if ! command -v tcpdump &>/dev/null; then
    echo "[*] Installing tcpdump..."
    apt install -y tcpdump > /dev/null 2>&1
    if command -v tcpdump &>/dev/null; then
        echo -e "${GREEN}[+]${RST} tcpdump installed"
    else
        echo -e "${YELLOW}[*]${RST} tcpdump install failed (optional, for --capture)"
    fi
else
    echo -e "${GREEN}[+]${RST} tcpdump already installed"
fi

if ! command -v impacket-ntlmrelayx &>/dev/null; then
    echo "[*] Installing impacket..."
    if command -v pipx &>/dev/null; then
        pipx install impacket > /dev/null 2>&1 && \
            echo -e "${GREEN}[+]${RST} impacket installed via pipx" || \
            echo -e "${YELLOW}[*]${RST} pipx install failed, trying pip..."
    fi
    # If pipx didn't work or isn't available, try pip
    if ! command -v impacket-ntlmrelayx &>/dev/null; then
        pip install impacket --break-system-packages > /dev/null 2>&1 && \
            echo -e "${GREEN}[+]${RST} impacket installed via pip" || \
            echo -e "${RED}[!]${RST} impacket install failed. Run: pipx install impacket"
    fi
else
    echo -e "${GREEN}[+]${RST} impacket already installed"
fi

if ! command -v nxc &>/dev/null; then
    echo "[*] Installing netexec (nxc)..."
    if command -v pipx &>/dev/null; then
        pipx install netexec > /dev/null 2>&1 && \
            echo -e "${GREEN}[+]${RST} netexec installed via pipx" || \
            echo -e "${YELLOW}[*]${RST} pipx install failed, trying pip..."
    fi
    if ! command -v nxc &>/dev/null; then
        pip install netexec --break-system-packages > /dev/null 2>&1 && \
            echo -e "${GREEN}[+]${RST} netexec installed via pip" || \
            echo -e "${RED}[!]${RST} netexec install failed. Run: pipx install netexec"
    fi
else
    echo -e "${GREEN}[+]${RST} nxc already installed"
fi

# ── Create venv ──
echo ""
if [ -d "${VENV_DIR}" ]; then
    echo -e "${YELLOW}[*]${RST} venv already exists at ${VENV_DIR}"
else
    echo "[*] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    echo -e "${GREEN}[+]${RST} venv created"
fi

# ── Activate and install Python deps ──
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip --quiet > /dev/null 2>&1

REQ_FILE="${SCRIPT_DIR}/requirements.txt"
if [ ! -f "${REQ_FILE}" ]; then
    cat > "${REQ_FILE}" <<EOF
ldap3>=2.9
dnspython>=2.3
impacket>=0.11
pycryptodomex
EOF
fi

echo "[*] Installing Python dependencies into venv..."
pip install -r "${REQ_FILE}" --quiet > /dev/null 2>&1
echo -e "${GREEN}[+]${RST} Python dependencies installed"

# ── dnstool.py ──
if [ -f "${SCRIPT_DIR}/dnstool.py" ]; then
    echo -e "${GREEN}[+]${RST} dnstool.py found"
else
    echo "[*] Downloading dnstool.py from dirkjanm/krbrelayx..."
    if command -v curl &>/dev/null; then
        curl -sL "https://raw.githubusercontent.com/dirkjanm/krbrelayx/master/dnstool.py" \
            -o "${SCRIPT_DIR}/dnstool.py"
    elif command -v wget &>/dev/null; then
        wget -q "https://raw.githubusercontent.com/dirkjanm/krbrelayx/master/dnstool.py" \
            -O "${SCRIPT_DIR}/dnstool.py"
    fi
    [ -f "${SCRIPT_DIR}/dnstool.py" ] && \
        echo -e "${GREEN}[+]${RST} dnstool.py downloaded" || \
        echo -e "${RED}[!]${RST} Download failed. Get it manually from github.com/dirkjanm/krbrelayx"
fi

# ── Final verification ──
echo ""
echo -e "${BOLD}Verifying all tools...${RST}"
ALL_GOOD=1
for tool in nxc impacket-ntlmrelayx dig tcpdump ss; do
    if command -v "$tool" &>/dev/null; then
        echo -e "  ${GREEN}✓${RST} $tool"
    else
        echo -e "  ${RED}✗${RST} $tool"
        ALL_GOOD=0
    fi
done

echo ""
if [ "${ALL_GOOD}" -eq 1 ]; then
    echo -e "${GREEN}${BOLD}Setup complete. Everything is ready.${RST}"
else
    echo -e "${YELLOW}${BOLD}Setup complete with warnings.${RST} Check the missing tools above."
fi
echo ""
echo -e "  ${CYAN}python3 smb_no_signing_gg.py --help${RST}"
echo ""
