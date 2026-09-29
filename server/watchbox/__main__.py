"""Run with: cd server && .venv/bin/python -m watchbox"""
import logging
import os
import socket

import uvicorn

from .app import create_app
from .config import load_settings
from .providers import make_provider


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # httpx logs full request URLs at INFO, and TheWatchAPI's token is a query parameter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings()
    provider = make_provider(settings)
    if provider:
        logging.info("Price source:         %s", provider.source)
    port = int(os.getenv("PORT", "8000"))
    logging.info("Web app:              http://localhost:%d", port)
    logging.info("ESP32 SERVER_URL:     http://%s:%d", lan_ip(), port)
    uvicorn.run(create_app(settings, provider), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
