# GL.iNet Blacklist/Whitelist API

`glinet_blacklist.py` is both a command-line tool and a reusable Python library for managing MAC address blacklists and whitelists on GL.iNet routers running SDK 4.0 firmware via the `black_white_list` RPC module.

It implements the full challenge-response + crypt + hash login flow described in the official GL.iNet SDK 4.0 documentation.

## Installation

```bash
pip install requests passlib
```

- `requests` is mandatory.
- `passlib` is **strongly recommended**. It produces more reliable password hashes than macOS's default LibreSSL `openssl passwd` for `alg=5` (SHA-256) and `alg=6` (SHA-512).

## Dual CLI + Library Design

The same file can be executed directly (`python glinet_blacklist.py ...`) or imported as a library.

All low-level functions remain available for advanced use. A high-level `GlinetClient` class is provided for the most common "connect once, then add/remove/list" workflow.

## Importing as a Library

Because the filename is `glinet_blacklist.py` (using an underscore), it can be imported directly as a standard Python module:

```python
from glinet_blacklist import GlinetClient

client = GlinetClient(host="192.168.8.1", password="router-password")
client.add_to_blacklist("AA:BB:CC:DD:EE:FF")
```

## GlinetClient (Recommended High-Level API)

```python
from glinet_blacklist import GlinetClient
```

### Constructor

```python
client = GlinetClient(
    host: str = "192.168.8.1",
    username: str = "root",
    password: Optional[str] = None,
    *,
    https: bool = False,
    verify: bool = True,
    debug: bool = False,
)
```

- `host`: Router IP or hostname on the LAN.
- `username`: Usually `"root"` (some devices may use `"admin"`).
- `password`: Router admin password. If omitted, the client will automatically fall back to the `GLINET_ROUTER_PASS` environment variable (see "Password from Environment Variable" below). Can also be supplied later to `login()`.
- `https`: Use `https://` (uncommon on LAN).
- `verify`: Set to `False` to disable TLS certificate verification for self-signed certs.
- `debug`: Print detailed authentication diagnostics (challenge response, hash computation, etc.).

### Password from Environment Variable

If you do not pass a `password` to the `GlinetClient` constructor or to the `login()` method, the client will look for the password in the `GLINET_ROUTER_PASS` environment variable.

This is the recommended way to supply credentials when using the library from the webapp or other services:

```bash
export GLINET_ROUTER_PASS="your-router-admin-password"
```

```python
from glinet_blacklist import GlinetClient

# No password passed — will read from GLINET_ROUTER_PASS
client = GlinetClient(host="192.168.8.1")
lists = client.get_lists()
```

You can still override it explicitly when needed:

```python
client = GlinetClient(host="192.168.8.1", password="override-for-this-call")
# or
client.login(password="one-off-password")
```

#### Docker / docker-compose Deployment

When running via the project's `docker-compose.yml`, credentials are provided securely using Docker secrets (no manual `export` needed inside the container):

- Create `router_password.txt` from the provided template (`router_password.txt.example`) and put your router admin password in it.
- The file is mounted as a Docker secret named `router_password` attached to the `web` service.
- `docker-entrypoint.sh` (the container entrypoint) reads `/run/secrets/router_password` and exports it as `GLINET_ROUTER_PASS` before starting the Flask/Gunicorn process.
- `GlinetClient` will therefore automatically receive the password via the environment variable.

This means the webapp code can simply do:

```python
client = GlinetClient(host=os.environ.get("GLINET_HOST", "192.168.8.1"))
```

without ever handling the raw password in application code.

For production or alternative deployments you can point at a different file using the environment variable:

```bash
GLINET_ROUTER_PASSWORD_FILE=/path/to/secret.txt docker-compose up
```

### Methods

| Method                        | Description                                      |
|-------------------------------|--------------------------------------------------|
| `login(password=None)`        | Perform login. Raises `ValueError` if no password is available from the argument, the constructor, or the `GLINET_ROUTER_PASS` environment variable. |
| `get_lists()`                 | Return `{"black": [...], "white": [...], "raw": ...}` |
| `add_mac(mac, mode="black")`  | Add a MAC to the blacklist or whitelist.        |
| `remove_mac(mac, mode="black")` | Remove a MAC from the blacklist or whitelist. |
| `add_to_blacklist(mac)`       | Convenience wrapper for blacklist add.          |
| `remove_from_blacklist(mac)`  | Convenience wrapper for blacklist remove.       |
| `add_to_whitelist(mac)`       | Convenience wrapper for whitelist add.          |
| `remove_from_whitelist(mac)`  | Convenience wrapper for whitelist remove.       |
| `close()`                     | Clear local session state.                      |

The client supports the context manager protocol:

```python
with GlinetClient(host=..., password=...) as client:
    client.add_to_blacklist("11:22:33:44:55:66")
    lists = client.get_lists()
```

Login is performed lazily on the first call that needs a session id (or explicitly via `client.login()`).

### Complete Example

```python
from glinet_blacklist import GlinetClient

router = GlinetClient(
    host="192.168.8.1",
    username="root",
    password="your-router-admin-password",
    debug=False,
)

try:
    lists = router.get_lists()
    print("Currently blacklisted:", lists["black"])

    result = router.add_to_blacklist("AA:BB:CC:DD:EE:FF")
    print("Add result:", result)

    # Refresh
    lists = router.get_lists()
    print("Updated blacklist:", lists["black"])

finally:
    router.close()
```

### Error Handling

- `ValueError`: Bad MAC address or no password available (after checking constructor argument, `login()` argument, and the `GLINET_ROUTER_PASS` environment variable).
- `RuntimeError`: RPC errors returned by the router (including authentication failures).
- `requests.exceptions.RequestException`: Network / HTTP errors.
- `ImportError`: `requests` (or `passlib` in certain fallback paths) is not installed.

When `debug=True`, the client (via the underlying functions) prints detailed information about the challenge, cipher generation, and login hash computation. This is extremely useful when diagnosing "Access denied" errors.

Common causes of login rejection even with the correct password:
- macOS `openssl passwd` producing incompatible hashes for alg 5/6 → install `passlib`.
- Router web UI using username `admin` instead of `root`.
- "Local Access" / security settings on the router blocking RPC access.

## Lower-Level Module API

The following functions are also exported and can be used directly if you need more control:

- `normalize_mac(mac: str) -> str`
- `login(url, username, password, verify=True, debug=False) -> sid`
- `get_config(url, sid, verify=True, debug=False)`
- `set_single_mac(url, sid, mode, operate, mac, verify=True, debug=False)`
- `get_current_lists(url, sid, verify=True, debug=False) -> {"black": [...], "white": [...], "raw": ...}`
- `call_api(...)`, `rpc_call(...)` for raw JSON-RPC access.

Most application code should prefer `GlinetClient`.

## Usage from the ChoreTracker Webapp (Planned)

When wiring this into the Flask application:

1. Store router credentials securely. The library will automatically read the router password from the `GLINET_ROUTER_PASS` environment variable if none is supplied in code. **Never** hard-code passwords.
2. In containerized deployments (the default `docker-compose` setup), the password is injected via Docker secrets:
   - Place the password in `router_password.txt` (gitignored).
   - `docker-compose.yml` mounts it as the `router_password` secret for the `web` service.
   - `docker-entrypoint.sh` promotes the secret file into the `GLINET_ROUTER_PASS` environment variable before the application starts.
3. Create a `GlinetClient` instance per request or use a short-lived cached client (the sid can be reused for multiple calls within a reasonable window).
4. On chore completion (or on a scheduled job), call `client.remove_from_blacklist(child_device_mac)`.
5. On chore becoming incomplete / parent action, call `client.add_to_blacklist(...)`.
6. Consider exposing a "Router Devices" management UI for parents to associate MAC addresses with children.

### Webapp Example (Container-Aware)

```python
# Inside a parent-only route or background task
from glinet_blacklist import GlinetClient
import os

def get_router_client():
    # In the Dockerized deployment, GLINET_ROUTER_PASS is automatically
    # provided via Docker secret + docker-entrypoint.sh.
    # You only need to supply host (and optionally verify) settings.
    return GlinetClient(
        host=os.environ.get("GLINET_HOST", "192.168.8.1"),
        verify=os.environ.get("GLINET_VERIFY", "true").lower() != "false",
    )

def enforce_chore_policy(child_mac: str, chores_complete: bool):
    with get_router_client() as client:
        if chores_complete:
            client.remove_from_blacklist(child_mac)
        else:
            client.add_to_blacklist(child_mac)
```

### Local / Non-Container Development

When running the webapp outside Docker (e.g. via `./run_dev.sh` + local Flask), simply export the variable in your shell or `.env` file:

```bash
export GLINET_ROUTER_PASS="your-router-admin-password"
# or
GLINET_ROUTER_PASS="..." python -m flask run
```

The `GlinetClient` will pick it up automatically when no password is passed to the constructor.

## Thread Safety

`GlinetClient` is **not** thread-safe. Create one client per thread or use external locking if sharing across threads.

## See Also

- `GL.iNet SDK4.0 API-DOCS.pdf` (official router RPC documentation)
- `README.md` – high-level project overview, CLI examples, and Docker deployment notes
- `docker-compose.yml` + `docker-entrypoint.sh` – how `GLINET_ROUTER_PASS` is injected via Docker secret in the web container
- `router_password.txt.example` – template for the router admin password (copy to `router_password.txt`)
- `glinet_blacklist.py --help`

## License / Attribution

This client is part of the ChoreTracker project. It is not affiliated with or endorsed by GL.iNet.