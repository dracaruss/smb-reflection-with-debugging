# CVE-2025-33073 Exploit Chain - Debug & Protocol Trace

NTLM relay exploit chain with full protocol-level tracing across LDAP, DNS, SMB, and RPC. Built for authorized penetration testing to diagnose why the chain succeeds on some targets and fails on others.

## Requirements

- Kali Linux (or any Linux with the tools below)
- `nxc` (NetExec)
- `impacket-ntlmrelayx` (standard) or `ntlmrelayx.py` (forked, for signing bypass)
- `dnstool.py` (in the same directory)
- `dig`
- Python 3 with `ldap3`
- `tcpdump` (optional, for packet capture)

Run `./setup.sh` to create the venv and install dependencies.

## Usage

```bash
python3 exploit_trace.py \
  -u 'CORP\jsmith' \
  -p 'Summer2025!' \
  -d 192.168.1.50 \
  --dns-ip 10.10.10.1 \
  --dc-fqdn dc01.corp.local \
  --target srv01.corp.local \
  --target-ip 10.10.10.20 \
  -M PetitPotam
```

### Arguments

| Flag | Description |
|------|-------------|
| `-u` | Domain credentials in `DOMAIN\user` format |
| `-p` | Password |
| `-d` | Your attacker/Kali IP |
| `--dns-ip` | Domain Controller IP (used as DNS server) |
| `--dc-fqdn` | DC fully qualified domain name (e.g. `dc01.corp.local`) |
| `--dc-ip` | DC IP, alternative to `--dc-fqdn` (one is required) |
| `--target` | Relay target FQDN (where captured auth is forwarded) |
| `--target-ip` | Coercion target IP (machine you trigger the callback from) |
| `-M` | Coercion method: `PetitPotam`, `Printerbug`, or `DFSCoerce` |
| `--smb-signing` | Use forked impacket for SMB signing bypass (relays to LDAPS) |
| `--socks` | Enable SOCKS proxy in ntlmrelayx |
| `--custom-command` | Run a custom command instead of secretsdump |
| `--capture` | Run tcpdump in the background, saves to `/tmp/cve33073_capture.pcap` |
| `--no-debug` | Suppress all debug/trace output (original behavior) |

## What the Trace Shows

The script prints a color-coded protocol flow diagram at startup, then logs every step with the protocol involved:

- **[LDAP]** (cyan): DNS record addition via authenticated LDAP to the DC
- **[DNS]** (yellow): Record propagation verification via `dig`
- **[SMB]** (blue): ntlmrelayx listener status, inbound connections, relay attempts
- **[RPC]** (magenta): Coercion trigger and response (MS-EFSRPC, MS-RPRN, MS-DFSNM)
- **[RELAY]** (blue): Relay configuration, target signing check, session forwarding

A background thread monitors for inbound connections on port 445 and logs them as they arrive.

## Common Failure Points

**DNS record added but never resolves:** The LDAP update was accepted but the DC's DNS zone rejected the dynamic update. Check dnstool output.

**No inbound connection on 445 after coercion:** The coercion method is patched (PetitPotam KB5005413), the DNS record points to the wrong IP, or a firewall is blocking the callback. Try `--method Printerbug` or `--method DFSCoerce`.

**Relay rejected (signing):** The relay target has SMB signing enabled. The trace will flag this in red. Either relay to a different target or use `--smb-signing` to relay to LDAPS instead.

**Relay works but no SAM dump:** The relayed machine account is not a local admin on the relay target. Machine accounts are almost never admin on themselves (self-relay), and may not be admin on other member servers. Try relaying to a host where the coerced machine account has admin privileges.

## Packet Capture

Use `--capture` to run tcpdump in the background. After the run, open the pcap in Wireshark to see the full exchange:

```bash
wireshark /tmp/cve33073_capture.pcap
```

Filter by protocol to isolate specific stages: `smb2`, `ldap`, `dcerpc`, `dns`.
