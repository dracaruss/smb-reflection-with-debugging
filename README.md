# smb_no_signing_gg

NTLM relay exploit chain with full protocol-level tracing across LDAP, DNS, SMB, and RPC. Built for authorized penetration testing to diagnose why the chain succeeds on some targets and fails on others.

## Setup

```bash
chmod +x setup.sh
./setup.sh
source venv/bin/activate
```

The setup script creates a Python venv, installs dependencies (ldap3, impacket, dnspython), downloads dnstool.py if missing, and checks that system tools (nxc, impacket-ntlmrelayx, dig, tcpdump) are available.

## Usage

```bash
python3 smb_no_signing_gg.py -u 'CORP\jsmith' -p 'Summer2025!' -d 192.168.1.50 --dns-ip 10.10.10.1 --dc-fqdn dc01.corp.local --relay-target srv01.corp.local --coerce-target 10.10.10.20 -M PetitPotam
```

### Arguments

| Flag | Description |
|------|-------------|
| `-u` | Domain credentials in `DOMAIN\user` format |
| `-p` | Password |
| `-d` | Your attacker/Kali IP |
| `--dns-ip` | Domain Controller IP (used as DNS server) |
| `--dc-fqdn` | DC fully qualified domain name (e.g. `dc01.corp.local`) |
| `--dc-ip` | DC IP, alternative to `--dc-fqdn` (one of the two is required) |
| `--relay-target` | FQDN of the machine the captured NTLM auth is forwarded TO for secretsdump |
| `--coerce-target` | IP of the machine you trigger to authenticate back to you |
| `-M` | Coercion method: `PetitPotam`, `Printerbug`, or `DFSCoerce` |
| `--smb-signing-is-on` | Switches from SMB relay to LDAPS relay using forked impacket with MIC removal (CVE-2019-1040). Use this when the relay target has SMB signing enforced. From LDAPS you can set up RBCD or shadow credentials instead of secretsdump. Leave it off for normal SMB relay. Works when the DC has LDAP signing not required and channel binding not required (the defaults). |
| `--socks` | Holds the relayed session open as a SOCKS proxy on port 1080 instead of auto-running secretsdump. Route other tools through it with proxychains for manual exploration. |
| `--capture` | Runs tcpdump in the background, saves to `/tmp/cve33073_capture.pcap`. Open in Wireshark after the run and filter by `smb2`, `ldap`, `dcerpc`, or `dns` to isolate specific stages. |
| `--no-debug` | Suppress all debug/trace output |

## What the Trace Shows

The script prints a color-coded protocol flow diagram at startup, then logs every step tagged by protocol:

- **[LDAP]** (cyan): DNS record addition via authenticated LDAP to the DC
- **[DNS]** (yellow): Record propagation verification via dig
- **[SMB]** (blue): ntlmrelayx listener status, inbound connections, relay attempts
- **[RPC]** (magenta): Coercion trigger and response (MS-EFSRPC, MS-RPRN, MS-DFSNM)
- **[RELAY]** (blue): Relay configuration, target signing check, session forwarding

A background thread monitors for inbound connections on port 445 and highlights them in green when a callback arrives.

## Two Modes

**Default (flag omitted):** SMB to SMB relay. The coerced machine authenticates to your port 445, and ntlmrelayx forwards that auth straight to the relay target's port 445. If the machine account has local admin on the relay target and signing is off, you get a SAM dump.

**`--smb-signing-is-on`:** SMB to LDAPS relay. The coerced machine still authenticates to your port 445 over SMB, but ntlmrelayx cross-protocol relays it to the DC's LDAPS on port 636. It strips the MIC from the NTLM Type 3 message (CVE-2019-1040) so the DC accepts the relayed auth. From LDAPS you modify AD objects (RBCD, shadow credentials) to compromise the target indirectly. This works when the DC has LDAP signing and channel binding at their defaults (not required).

Without the flag, the captured NTLM auth arriving on your port 445 gets forwarded straight to the relay target's port 445 (SMB to SMB). ntlmrelayx authenticates as the machine account on the relay target and runs secretsdump. This only works when SMB signing is off on that relay target.

With the flag, the SMB to SMB path is skipped (signing enforced), and instead ntlmrelayx takes the NTLM auth that arrived over SMB and cross-protocol relays it to the DC's LDAPS on port 636. The MIC in the NTLM Type 3 message is designed to prevent exactly this kind of cross-protocol relay, which is why it uses decoder-it's forked impacket to strip it. Once the LDAPS session is established as the machine account, you can modify AD objects (set up RBCD, add shadow credentials) to compromise the target indirectly rather than dumping SAM directly.

## Common Failure Points

**DNS record added but never resolves:** The LDAP update was accepted but the DC's DNS zone rejected the dynamic update. Check dnstool output in the trace.

**No inbound connection on 445 after coercion:** The coercion method is patched (PetitPotam KB5005413), the DNS record points to the wrong IP, or a firewall is blocking the callback. Try `-M Printerbug` or `-M DFSCoerce`.

**Relay rejected (signing):** The relay target has SMB signing enabled. The trace flags this in red. Either pick a different relay target or use `--smb-signing-is-on` to relay to LDAPS instead.

**Relay works but no SAM dump:** The relayed machine account is not a local admin on the relay target. Machine accounts are almost never admin on themselves (self-relay). Try relaying to a host where the coerced machine account has admin privileges.

**LDAPS relay fails:** The DC has LDAP signing required or channel binding required. The trace will show the LDAPS connection being rejected. Check with `nxc ldap <DC> -M ldap-checker`.
