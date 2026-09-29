"""Compute worker: run the platform's simulations on your own hardware.

    autoeng-worker --server https://your-server --code ABCD-1234   # first run: pair
    autoeng-worker --server https://your-server                    # later runs reuse the saved token

Works on a desktop, a laptop GPU, a cloud VM, or a Kaggle/Colab notebook. The
worker only makes outbound HTTPS requests, so no ports need opening. It uses the
GPU automatically when CuPy and a CUDA device are available (AUTOENG_COMPUTE=cpu
forces the CPU).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path

import httpx

from autoeng import __version__, compute
from autoeng.services.jobs import execute

log = logging.getLogger("autoeng.worker")
CONFIG = Path(os.environ.get("AUTOENG_WORKER_CONFIG", Path.home() / ".autoeng" / "worker.json"))


def device_info() -> dict:
    status = compute.status()
    return {
        "version": __version__,
        "host": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "gpu": status["gpu_device"],
        "gpu_available": status["gpu_available"],
        "cpu_count": os.cpu_count(),
    }


def _load() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass


def pair(client: httpx.Client, server: str, code: str) -> str:
    r = client.post(f"{server}/api/v1/worker/pair", json={"code": code, "device": device_info()})
    if r.status_code != 200:
        raise SystemExit(f"Pairing failed: {r.text}")
    data = r.json()
    cfg = _load()
    cfg[server] = {"token": data["token"], "worker_id": data["worker_id"], "name": data["name"]}
    _save(cfg)
    log.info("Paired as '%s'", data["name"])
    return data["token"]


def serve(server: str, token: str, poll: float, once: bool = False) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    info = device_info()
    log.info("Worker running on %s (GPU: %s). Waiting for jobs from %s", info["host"], info["gpu"] or "none", server)
    backoff = poll
    with httpx.Client(timeout=60, headers=headers) as client:
        while True:
            try:
                r = client.post(f"{server}/api/v1/worker/claim", json={"device": info})
                if r.status_code == 401:
                    raise SystemExit("Worker token rejected: the worker was removed. Pair again with a new code.")
                r.raise_for_status()
                backoff = poll
                if r.status_code == 204:
                    if once:
                        return
                    time.sleep(poll)
                    continue
                job = r.json()
                log.info("Running %s job %s", job["kind"], job["id"])
                started = time.perf_counter()
                try:
                    result = execute(job["kind"], job["payload"])
                    body = {"result": result, "device": {**(result.get("compute") or {}), "host": info["host"],
                                                         "seconds": round(time.perf_counter() - started, 3)}}
                except Exception as exc:  # noqa: BLE001 - report any failure on the job
                    log.exception("Job failed")
                    body = {"error": f"{type(exc).__name__}: {exc}", "device": {"host": info["host"]}}
                client.post(f"{server}/api/v1/worker/jobs/{job['id']}/complete", json=body).raise_for_status()
                log.info("Finished job %s in %.2f s", job["id"], time.perf_counter() - started)
                if once:
                    return
            except httpx.HTTPError as exc:
                log.warning("Server unreachable (%s); retrying in %.0f s", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run platform simulations on this machine.")
    parser.add_argument("--server", required=True, help="Platform base URL, e.g. https://api.example.com")
    parser.add_argument("--code", help="Pairing code from the web app (first run only)")
    parser.add_argument("--poll", type=float, default=2.0, help="Seconds between polls when idle")
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every idle poll
    server = args.server.rstrip("/")
    with httpx.Client(timeout=30) as client:
        token = pair(client, server, args.code) if args.code else _load().get(server, {}).get("token")
    if not token:
        sys.exit("No saved token for this server. Create a worker in the web app and pass --code.")
    serve(server, token, args.poll, args.once)


if __name__ == "__main__":
    main()
