"""Runtime guard: no network. Called before anything else at runtime."""
from __future__ import annotations

import os
import socket


class NetworkBlocked(RuntimeError):
    pass


def _refuse(*_args, **_kwargs):
    raise NetworkBlocked("Linaw makes no network calls at runtime")


def enforce_offline() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    socket.socket.connect = _refuse
    socket.socket.connect_ex = _refuse
    socket.create_connection = _refuse
    socket.getaddrinfo = _refuse
