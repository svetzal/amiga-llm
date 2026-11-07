#!/usr/bin/env python3
"""Send commands to a running Amiberry through its control socket.

Usage:
    amiberry_ipc.py GET_STATUS
    amiberry_ipc.py SCREENSHOT /abs/path/shot.png
    amiberry_ipc.py --wait 60 PING          # wait up to 60 s for the socket
    amiberry_ipc.py QUIT

Each command is one line of tab-separated fields. The reply starts with OK or
an error and its fields are printed one per line. Exits 0 on OK, 1 on an
error reply, 2 when no emulator answers. Standard library only.
"""

import argparse
import os
import socket
import sys
import time

DEFAULT_SOCKET = "/tmp/amiberry.sock"


def encode(fields: list[str]) -> bytes:
    """One command line: fields joined by tabs, ending in a newline."""
    return ("\t".join(fields) + "\n").encode()


def send(fields: list[str], path: str = DEFAULT_SOCKET, timeout: float = 5.0) -> list[str]:
    """Send one command and return the reply's fields."""
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(timeout)
        conn.connect(path)
        conn.sendall(encode(fields))
        reply = b""
        try:
            while not reply.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                reply += chunk
        except TimeoutError:
            pass
    return reply.decode(errors="replace").rstrip("\n").split("\t")


def wait_for(path: str, seconds: float) -> bool:
    """True once something answers PING on the socket, within `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                if send(["PING"], path, timeout=2.0)[0] == "OK":
                    return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="+", help="command name and its fields")
    parser.add_argument("--socket", default=DEFAULT_SOCKET, help="socket path")
    parser.add_argument("--wait", type=float, default=0, help="seconds to wait for the socket")
    args = parser.parse_args()

    if args.wait and not wait_for(args.socket, args.wait):
        print(f"no Amiberry answered on {args.socket} within {args.wait:g} s", file=sys.stderr)
        return 2
    try:
        reply = send(args.command, args.socket)
    except OSError as error:
        print(f"no Amiberry answered on {args.socket}: {error}", file=sys.stderr)
        return 2
    print("\n".join(reply))
    return 0 if reply[0] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
