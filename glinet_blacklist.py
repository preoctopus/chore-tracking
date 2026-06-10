#!/usr/bin/env python3
"""
GL.iNet SDK 4.0 - Add/Remove MAC from Blacklist (or Whitelist)

Can be used both as a command-line tool and as a Python library.

Uses the black_white_list module:
  - black_white_list/get_config
  - black_white_list/set_single_mac   (mode=black/white, operate=add/del, mac=XX:XX:XX:XX:XX:XX)

Login uses the documented challenge + (passlib or openssl) crypt + md5 hash flow.

Recommended:
    pip install requests passlib

passlib is strongly preferred (and matches the Python examples in the official docs)
because macOS's default `openssl passwd` (LibreSSL) can produce hashes that the
router rejects for alg=5 / alg=6 even when the password is correct.

Library usage (primary high-level API):

    from glinet_blacklist import GlinetClient   # see GL-API.md for import details

    with GlinetClient(host="192.168.8.1", password="...") as client:
        client.add_to_blacklist("aa:bb:cc:dd:ee:ff")
        print(client.get_lists())
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


def normalize_mac(mac: str) -> str:
    """Normalize MAC to uppercase with colon separators."""
    if not mac:
        raise ValueError("MAC address is required")
    m = re.sub(r'[^0-9a-fA-F]', '', mac)
    if len(m) != 12:
        raise ValueError(f"Invalid MAC address (need 12 hex chars): {mac}")
    return ':'.join(m[i:i+2].upper() for i in range(0, 12, 2))


def get_cipher_password(password: str, alg: int, salt: str, debug: bool = False) -> str:
    """
    Generate the shadow-style cipher password.

    The GL.iNet docs explicitly show using passlib with rounds=5000 for alg 5/6.
    We prefer passlib when available because it is more portable and matches
    the router's expected crypt() output better than macOS's default LibreSSL
    `openssl passwd` in some cases.
    """
    # Preferred: use passlib (exactly as shown in the official SDK4 docs)
    try:
        from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt

        if alg == 1:
            cipher = md5_crypt.using(salt=salt).hash(password)
        elif alg == 5:
            cipher = sha256_crypt.using(salt=salt, rounds=5000).hash(password)
        elif alg == 6:
            cipher = sha512_crypt.using(salt=salt, rounds=5000).hash(password)
        else:
            raise ValueError(f"Unsupported alg: {alg}")

        if debug:
            print(f"[debug] cipher generated via passlib (alg={alg}, rounds=5000 for sha*)")
        return cipher
    except ImportError:
        if debug:
            print("[debug] passlib not installed, falling back to openssl passwd")
    except Exception as e:
        if debug:
            print(f"[debug] passlib failed ({e}), falling back to openssl")

    # Fallback: openssl (what the shell examples in the docs use)
    alg_flag = f"-{alg}"
    try:
        out = subprocess.check_output(
            ["openssl", "passwd", alg_flag, "-salt", salt, password],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        if debug:
            print(f"[debug] cipher generated via openssl passwd -{alg}")
        return out
    except FileNotFoundError:
        raise RuntimeError(
            "Neither passlib nor openssl found. "
            "Install with: pip install passlib   (recommended)\n"
            "or ensure /usr/bin/openssl is available."
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"openssl passwd failed: {e.output.strip() if e.output else e}")


def make_session(verify: bool = True) -> "requests.Session":
    if requests is None:
        raise ImportError(
            "The 'requests' package is required to use this module. "
            "Install with: pip install requests passlib"
        )
    s = requests.Session()
    if not verify:
        # For self-signed certs on https
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        s.verify = False
    return s


def rpc_call(session: requests.Session, url: str, sid: Optional[str], module: str, func: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perform a JSON-RPC call. For login/challenge, sid may be None."""
    params: List[Any] = []
    if sid is not None:
        params.append(sid)
    params.append(module)
    params.append(func)
    if args is not None:
        params.append(args)

    payload = {
        "jsonrpc": "2.0",
        "method": "call" if sid is not None else func,  # challenge and login use direct method
        "params": (args if sid is None else params),
        "id": 0,
    }
    # Special case: challenge and login are NOT wrapped in "call"
    if sid is None:
        # For challenge/login the top level method is "challenge" / "login", and params is the object
        payload = {
            "jsonrpc": "2.0",
            "method": func,
            "params": args or {},
            "id": 0,
        }

    resp = session.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data and data["error"]:
        raise RuntimeError(f"RPC error: {data['error']}")

    return data


def login(url: str, username: str, password: str, verify: bool = True, debug: bool = False) -> str:
    """Perform the full GL.iNet SDK4 login flow. Returns sid."""
    session = make_session(verify=verify)

    # Step 1: challenge
    if debug:
        print("[debug] Sending challenge request for user:", username)
    chal = rpc_call(session, url, None, "", "challenge", {"username": username})
    result = chal.get("result") or {}
    if not result:
        raise RuntimeError(f"Challenge failed: {chal}")
    alg = int(result.get("alg", 1))
    salt = result.get("salt")
    nonce = result.get("nonce")
    # Newer firmwares return "hash-method" (e.g. "sha256") in addition to alg.
    # "alg" is for the password cipher (shadow hash), "hash-method" is for the
    # final login hash (the value sent in the "hash" field of the login request).
    hash_method = (result.get("hash-method") or result.get("hash_method") or "md5").lower()
    if not salt or not nonce:
        raise RuntimeError(f"Bad challenge response: {result}")

    if debug:
        print("[debug] Full challenge response (safe to share):")
        print(json.dumps(chal, indent=2, default=str))
        print(f"[debug] Using: alg={alg}, hash-method={hash_method}, salt={salt!r}, nonce (first 12 chars)={nonce[:12]!r}")

    # Step 2: cipher password (openssl crypt or passlib)
    cipher = get_cipher_password(password, alg, salt, debug=debug)
    if debug:
        # Show only the structure, not the secret
        print(f"[debug] cipher (shadow format, alg={alg}): ${alg}${salt}$... (len={len(cipher)})")

    # Step 3: Final login hash.
    # Older docs always used MD5 here. Newer firmware advertises "hash-method"
    # (sha256 in this case) and we must use that for the "hash" value sent to login.
    hash_input = f"{username}:{cipher}:{nonce}"
    if hash_method in ("sha256", "sha-256"):
        login_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        hash_label = "sha256"
    else:
        login_hash = hashlib.md5(hash_input.encode("utf-8")).hexdigest()
        hash_label = "md5"
    if debug:
        print(f"[debug] login hash ({hash_label} of user:cipher:nonce): {login_hash}")

    # Step 4: login
    if debug:
        print("[debug] Sending login request (username + computed hash only)")
    try:
        log = rpc_call(session, url, None, "", "login", {"username": username, "hash": login_hash})
    except RuntimeError as e:
        # Re-raise with more context for common access denied
        if "Access denied" in str(e) or "-32000" in str(e):
            raise RuntimeError(
                f"Login rejected by router with Access denied (-32000).\n"
                f"hash-method used for this attempt: {hash_method}\n"
                f"Raw error: {e}\n"
                f"(Script now respects the 'hash-method' field from the challenge response.)"
            ) from e
        raise

    result = log.get("result") or {}
    sid = result.get("sid")
    if not sid:
        raise RuntimeError(f"Login failed (no sid in result): {log}")
    if debug:
        print("[debug] Login successful, got sid (truncated):", sid[:8] + "...")
    return sid


def call_api(url: str, sid: str, module: str, func: str, args: Optional[Dict[str, Any]] = None, verify: bool = True) -> Dict[str, Any]:
    """Wrapper around rpc_call that returns the full response dict (caller extracts .get('result'))."""
    session = make_session(verify=verify)
    data = rpc_call(session, url, sid, module, func, args)
    return data


def get_config(url: str, sid: str, verify: bool = True, debug: bool = False) -> Dict[str, Any]:
    data = call_api(url, sid, "black_white_list", "get_config", verify=verify)
    if debug:
        print("[debug] black_white_list/get_config raw response:")
        print(json.dumps(data, indent=2, default=str))
    return data.get("result", data)


def set_single_mac(url: str, sid: str, mode: str, operate: str, mac: str, verify: bool = True, debug: bool = False) -> Dict[str, Any]:
    args = {"mode": mode, "operate": operate, "mac": mac}
    data = call_api(url, sid, "black_white_list", "set_single_mac", args, verify=verify)
    if debug:
        print("[debug] black_white_list/set_single_mac raw response:")
        print(json.dumps(data, indent=2, default=str))
    return data.get("result", data)


def get_current_lists(url: str, sid: str, verify: bool = True, debug: bool = False) -> Dict[str, List[str]]:
    """Return {'black': [...], 'white': [...]} best effort from get_config result."""
    cfg = get_config(url, sid, verify=verify, debug=debug)
    # Common shapes seen in similar firmwares / inferred:
    # { "black": [...], "white": [...] }
    # or { "mode": "black", "mac": [...] } (current mode only)
    # or nested under other keys.
    black: List[str] = []
    white: List[str] = []

    if isinstance(cfg, dict):
        if "black" in cfg and isinstance(cfg["black"], list):
            black = [normalize_mac(m) for m in cfg["black"] if m]
        if "white" in cfg and isinstance(cfg["white"], list):
            white = [normalize_mac(m) for m in cfg["white"] if m]
        # Some responses may put lists under "mac" when mode present
        if not black and not white and "mac" in cfg and isinstance(cfg.get("mac"), list):
            mode = cfg.get("mode", "black")
            if mode == "black":
                black = [normalize_mac(m) for m in cfg["mac"] if m]
            else:
                white = [normalize_mac(m) for m in cfg["mac"] if m]
    return {"black": black, "white": white, "raw": cfg}


class GlinetClient:
    """
    High-level client for GL.iNet SDK 4.0 MAC blacklist/whitelist management.

    This class provides a convenient, stateful API for use when importing
    the module as a library from another Python application.

    Password resolution order (for both constructor and login()):
      1. Explicitly passed value
      2. Value stored from the constructor
      3. Environment variable GLINET_ROUTER_PASS

    Example:
        from glinet_blacklist import GlinetClient

        # Password from constructor
        with GlinetClient(host="192.168.8.1", password="secret") as client:
            client.add_to_blacklist("AA:BB:CC:DD:EE:FF")
            print(client.get_lists())

        # Or rely on environment variable
        # export GLINET_ROUTER_PASS="your-password"
        client = GlinetClient(host="192.168.8.1")
        client.add_to_blacklist("11:22:33:44:55:66")
    """

    def __init__(
        self,
        host: str = "192.168.8.1",
        username: str = "root",
        password: Optional[str] = None,
        *,
        https: bool = False,
        verify: bool = True,
        debug: bool = False,
    ) -> None:
        """
        Create a client instance.

        The actual login is performed lazily on the first operation that
        requires a session id, or you can call login() explicitly.

        Args:
            host: Router LAN IP or hostname (default: 192.168.8.1)
            username: Router username (default: "root")
            password: Router password. If omitted here and not passed to login(),
                      the client will fall back to the GLINET_ROUTER_PASS
                      environment variable.
            https: Use https:// instead of http:// (rare)
            verify: Verify TLS certificates (set False for self-signed certs)
            debug: Enable verbose debug output from the underlying auth flow
        """
        self.host = host
        self.username = username
        if password is None:
            password = os.environ.get("GLINET_ROUTER_PASS")
        self._password: Optional[str] = password
        self.https = https
        self.verify = verify
        self.debug = debug
        self._sid: Optional[str] = None

    @property
    def url(self) -> str:
        scheme = "https" if self.https else "http"
        return f"{scheme}://{self.host}/rpc"

    def login(self, password: Optional[str] = None) -> str:
        """
        Perform the GL.iNet challenge + login flow and store the session id.

        Password resolution order:
          1. The `password` argument to this call
          2. The password provided to the constructor (if any)
          3. The GLINET_ROUTER_PASS environment variable

        If no password is available after the above steps, a ValueError is raised.
        (Interactive password prompting is only done in CLI mode.)
        """
        if password is not None:
            self._password = password
        if not self._password:
            self._password = os.environ.get("GLINET_ROUTER_PASS")
        if not self._password:
            raise ValueError(
                "Password is required. Provide it in the GlinetClient constructor, "
                "call client.login(password=...), or set the GLINET_ROUTER_PASS "
                "environment variable."
            )
        self._sid = login(
            self.url,
            self.username,
            self._password,
            verify=self.verify,
            debug=self.debug,
        )
        return self._sid

    @property
    def sid(self) -> str:
        """Return the current session id, logging in if necessary."""
        if not self._sid:
            self.login()
        return self._sid  # type: ignore[return-value]

    def get_lists(self) -> Dict[str, List[str]]:
        """Return the current black and white lists."""
        return get_current_lists(
            self.url, self.sid, verify=self.verify, debug=self.debug
        )

    def add_mac(self, mac: str, mode: str = "black") -> Dict[str, Any]:
        """
        Add a MAC address to the specified list.

        Args:
            mac: MAC address (any common format)
            mode: "black" or "white"
        """
        mac = normalize_mac(mac)
        return set_single_mac(
            self.url, self.sid, mode, "add", mac, verify=self.verify, debug=self.debug
        )

    def remove_mac(self, mac: str, mode: str = "black") -> Dict[str, Any]:
        """
        Remove a MAC address from the specified list.

        Args:
            mac: MAC address (any common format)
            mode: "black" or "white"
        """
        mac = normalize_mac(mac)
        return set_single_mac(
            self.url, self.sid, mode, "del", mac, verify=self.verify, debug=self.debug
        )

    # Convenience methods -------------------------------------------------

    def add_to_blacklist(self, mac: str) -> Dict[str, Any]:
        """Add MAC to the blacklist."""
        return self.add_mac(mac, mode="black")

    def remove_from_blacklist(self, mac: str) -> Dict[str, Any]:
        """Remove MAC from the blacklist."""
        return self.remove_mac(mac, mode="black")

    def add_to_whitelist(self, mac: str) -> Dict[str, Any]:
        """Add MAC to the whitelist."""
        return self.add_mac(mac, mode="white")

    def remove_from_whitelist(self, mac: str) -> Dict[str, Any]:
        """Remove MAC from the whitelist."""
        return self.remove_mac(mac, mode="white")

    # Context manager support --------------------------------------------

    def __enter__(self) -> "GlinetClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        """Clear local session state (does not invalidate the server-side sid)."""
        self._sid = None


def main():
    parser = argparse.ArgumentParser(
        description="Add or remove a MAC address from GL.iNet router's MAC blacklist (black_white_list)."
    )
    parser.add_argument("--host", default="192.168.8.1", help="Router LAN IP or hostname (default: 192.168.8.1)")
    parser.add_argument("--user", "-u", default="root", help="Username (default: root)")
    parser.add_argument("--pass", "-p", dest="password", help="Password (will prompt if omitted)")
    parser.add_argument("--mac", "-m", help="MAC address to add/remove (prompts if omitted)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true", help="Add the MAC to the blacklist")
    group.add_argument("--remove", "--del", "-d", dest="remove", action="store_true", help="Remove the MAC from the blacklist")
    parser.add_argument("--mode", choices=["black", "white"], default="black", help="black or white list (default: black)")
    parser.add_argument("--list", "-l", action="store_true", help="Only fetch and print current black/white lists, then exit")
    parser.add_argument("--https", action="store_true", help="Use https:// instead of http:// (rare)")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification (for self-signed)")
    parser.add_argument("--debug", "-v", action="store_true", help="Print detailed authentication diagnostics (challenge response, hash computation, etc.)")

    args = parser.parse_args()

    scheme = "https" if args.https else "http"
    url = f"{scheme}://{args.host}/rpc"
    verify_ssl = not args.insecure

    # Gather credentials
    username = args.user or "root"
    password = args.password
    if not password:
        password = getpass.getpass(f"Password for {username}@{args.host}: ")

    # Gather action + mac
    if args.list:
        action = None
        mac = None
    else:
        if args.add:
            action = "add"
        elif args.remove:
            action = "remove"
        else:
            # interactive prompt
            choice = input("Action? [a]dd / [r]emove : ").strip().lower()
            if choice.startswith("a"):
                action = "add"
            elif choice.startswith("r"):
                action = "remove"
            else:
                print("Invalid choice, must be add or remove.")
                sys.exit(1)

        mac = args.mac
        if not mac:
            mac = input("MAC address (e.g. aa:bb:cc:dd:ee:ff): ").strip()
        mac = normalize_mac(mac)

    # Login
    print(f"Connecting to {url} as {username} ...")
    try:
        sid = login(url, username, password, verify=verify_ssl, debug=args.debug)
        if not args.debug:
            print("Login successful.")
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        if "Access denied" in str(e) or "-32000" in str(e):
            print(
                "\nCommon causes for 'Access denied' during login (even with correct password):\n"
                "  • macOS 'openssl passwd' (LibreSSL) sometimes produces a different hash than\n"
                "    the router's internal crypt() for alg=5 (SHA256) or alg=6 (SHA512).\n"
                "  • The web UI on this device uses username 'admin' instead of 'root'.\n"
                "  • 'Local Access' / Security settings on the router block RPC/API access.\n"
                "  • Password has leading/trailing spaces or special characters.\n\n"
                "Strongly recommended fix:\n"
                "  pip install passlib\n\n"
                "Then re-run the command. The script will prefer passlib (as shown in the\n"
                "official GL.iNet SDK4 docs) which is much more reliable across platforms.\n\n"
                "Also re-run with --debug (or -v) and paste the output so we can see the alg\n"
                "the router is using and which method the script chose for the cipher.\n",
                file=sys.stderr,
            )
        sys.exit(2)

    # Optional: just list
    if args.list:
        try:
            lists = get_current_lists(url, sid, verify=verify_ssl, debug=args.debug)
            print("\nCurrent lists (from black_white_list/get_config):")
            print(json.dumps(lists, indent=2, default=str))
        except Exception as e:
            print(f"Failed to get lists: {e}", file=sys.stderr)
            # still try raw
            try:
                raw = get_config(url, sid, verify=verify_ssl, debug=args.debug)
                print("Raw get_config result:")
                print(json.dumps(raw, indent=2, default=str))
            except Exception as e2:
                print(f"Raw also failed: {e2}", file=sys.stderr)
        return

    # Perform add/remove using set_single_mac
    operate = "add" if action == "add" else "del"
    print(f"{action.capitalize()}ing {mac} to {args.mode} list ...")

    try:
        res = set_single_mac(url, sid, args.mode, operate, mac, verify=verify_ssl, debug=args.debug)
        print("Result:", json.dumps(res, indent=2, default=str))
        if isinstance(res, dict):
            ec = res.get("err_code")
            em = res.get("err_msg")
            if ec not in (None, 0, "0"):
                print(f"WARNING: router returned err_code={ec} err_msg={em}", file=sys.stderr)
    except Exception as e:
        print(f"Operation failed: {e}", file=sys.stderr)
        sys.exit(3)

    # Show updated lists for confirmation
    print("\nFetching updated lists...")
    try:
        lists = get_current_lists(url, sid, verify=verify_ssl, debug=args.debug)
        print(json.dumps({"black": lists["black"], "white": lists["white"]}, indent=2))
    except Exception as e:
        print(f"(Could not fetch updated lists: {e})")


if __name__ == "__main__":
    main()
