"""
watcher.py — File watcher para data/inbox/<source>/<YYYY-MM-DD>/*.csv.

Detecta CSV nuevos depositados por los scrapers y dispara los loaders A2
(bronze -> silver -> gold) en un mismo run_id. Archiva el archivo a
data/processed/<YYYY-MM-DD>/ tras exito.

Triggers (per plan §7.2):
  - watchdog en `data/inbox/` (eventos en tiempo real).
  - Safety-net opcional: re-escaneo periodico de inbox por si watchdog se
    perdio algo (default cada 30 min).

Concurrencia (per plan §9.2):
  - Procesa un archivo a la vez (Lock global). Si llegan varios eventos
    simultaneos, se encolan FIFO.
  - Antes de procesar, espera que el archivo este "estable" (mtime y
    tamano sin cambios por 2 segundos) para no leer mientras el scraper
    aun escribe.

Path expected:
    data/inbox/<source>/<YYYY-MM-DD>/<filename>.csv
        donde <source> in {twitter, youtube, tiktok, external}.

Uso:
    # Loop infinito (watchdog + safety-net)
    uv run python -m data_pipeline.ingestion.watcher

    # Una sola pasada de scan_inbox y salir (modo cron):
    uv run python -m data_pipeline.ingestion.watcher --once

    # Procesar inbox actual y luego entrar al loop:
    uv run python -m data_pipeline.ingestion.watcher --scan-on-start
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

from data_pipeline.loaders import bronze, gold, runs, silver  # noqa: E402

log = get_logger("ingestion.watcher")


# ── Config ─────────────────────────────────────────────────────────────

DEFAULT_INBOX = _PROJECT_ROOT / "data" / "inbox"
VALID_SOURCES = {"twitter", "youtube", "tiktok", "external"}

# Pequeno regex de seguridad para que el path sea data/inbox/<source>/<date>/<file>.csv
# Acepta separadores Windows o Unix (re-normalizamos antes).
_PATH_RE = re.compile(
    rf"(?:^|/)inbox/(?P<source>{'|'.join(VALID_SOURCES)})/"
    r"(?P<date>\d{4}-\d{2}-\d{2})/(?P<name>[^/]+\.csv)$",
    re.IGNORECASE,
)

STABLE_CHECK_INTERVAL = 1.0   # segundos entre checks de mtime/tamano
STABLE_CHECKS_REQUIRED = 2    # cuantos checks consecutivos sin cambio
STABLE_TIMEOUT = 60.0         # max espera total para que se estabilice


# ── Cola de procesamiento (1 archivo a la vez) ─────────────────────────


class _Processor:
    """
    Cola FIFO de paths a procesar. Worker thread unico que ejecuta
    bronze -> silver -> gold en serie.

    Usar `submit(path, source)` desde cualquier thread; `start()` arranca
    el worker; `stop()` lo detiene tras drenar la cola.
    """

    def __init__(self):
        self._queue: deque[tuple[Path, str]] = deque()
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop_event = threading.Event()
        self._inflight: set[Path] = set()  # evitar dobles encoladas
        self._thread: threading.Thread | None = None

    def submit(self, path: Path, source: str) -> bool:
        """Encola si no esta ya. Devuelve True si se encolo."""
        with self._lock:
            if path in self._inflight:
                return False
            self._inflight.add(path)
            self._queue.append((path, source))
        self._wakeup.set()
        log.info("[watcher] queued %s (source=%s, qlen=%d)",
                 path.name, source, len(self._queue))
        return True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="watcher-processor", daemon=True,
        )
        self._thread.start()

    def stop(self, drain: bool = True, timeout: float = 30.0) -> None:
        self._stop_event.set()
        self._wakeup.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        log.info("[watcher] processor thread started")
        while not self._stop_event.is_set():
            self._wakeup.wait(timeout=1.0)
            self._wakeup.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    path, source = self._queue.popleft()
                try:
                    self._process_one(path, source)
                except Exception as exc:  # noqa: BLE001
                    log.exception("[watcher] error procesando %s: %s",
                                  path.name, exc)
                finally:
                    with self._lock:
                        self._inflight.discard(path)
        log.info("[watcher] processor thread stopped")

    def _process_one(self, path: Path, source: str) -> None:
        if not _wait_until_stable(path):
            log.warning("[watcher] %s no se estabilizo a tiempo - skip",
                        path.name)
            return
        if not path.exists():
            log.warning("[watcher] %s ya no existe (concurrency?) - skip",
                        path.name)
            return

        run_id = runs.start("ingest_inbox")
        log.info("[watcher] >>> START %s (source=%s, run=%s)",
                 path.name, source, run_id[:8])
        try:
            n_bronze = bronze.load_csv(
                str(path), source=source, run_id=run_id, archive=True,
            )
            if n_bronze == 0:
                runs.finish(run_id, status="success", rows_out=0)
                log.info("[watcher] <<< DONE %s (0 filas, dup por sha)",
                         path.name)
                return
            n_silver = silver.promote_run(run_id)
            n_gold = gold.promote_run(run_id)
            runs.finish(run_id, status="success", rows_out=n_gold)
            log.info(
                "[watcher] <<< DONE %s bronze=%d silver=%d gold=%d run=%s",
                path.name, n_bronze, n_silver, n_gold, run_id[:8],
            )
        except Exception as exc:  # noqa: BLE001
            runs.finish(run_id, status="failed", error=str(exc))
            log.exception("[watcher] !!! FAIL %s run=%s: %s",
                          path.name, run_id[:8], exc)


# ── Estabilizacion (espera que el scraper termine de escribir) ────────


def _wait_until_stable(path: Path) -> bool:
    """True si el archivo dejo de cambiar dentro de STABLE_TIMEOUT."""
    deadline = time.monotonic() + STABLE_TIMEOUT
    last: tuple[int, float] | None = None
    stable_count = 0
    while time.monotonic() < deadline:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        cur = (stat.st_size, stat.st_mtime)
        if last == cur:
            stable_count += 1
            if stable_count >= STABLE_CHECKS_REQUIRED:
                return True
        else:
            stable_count = 0
            last = cur
        time.sleep(STABLE_CHECK_INTERVAL)
    return False


# ── Path parsing ───────────────────────────────────────────────────────


def _parse_inbox_path(path: Path, inbox: Path) -> tuple[str, str] | None:
    """
    Extrae (source, name) si path encaja en data/inbox/<source>/<date>/<file>.csv.
    Devuelve None si no encaja (lo ignoramos).
    """
    try:
        rel = path.resolve().relative_to(inbox.resolve())
    except ValueError:
        return None
    parts = rel.parts
    # parts = (source, date, filename)
    if len(parts) != 3:
        return None
    source, date, name = parts
    if source.lower() not in VALID_SOURCES:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    if not name.lower().endswith(".csv"):
        return None
    return source.lower(), name


# ── Watchdog handler ───────────────────────────────────────────────────


def _make_handler(processor: _Processor, inbox: Path):
    from watchdog.events import FileSystemEventHandler  # type: ignore

    class InboxHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            self._maybe_submit(Path(event.src_path))

        def on_moved(self, event):
            # Algunos scrapers/editores usan "atomic move" desde un .tmp
            if event.is_directory:
                return
            self._maybe_submit(Path(event.dest_path))

        def _maybe_submit(self, path: Path):
            parsed = _parse_inbox_path(path, inbox)
            if parsed is None:
                return
            source, _name = parsed
            processor.submit(path, source)

    return InboxHandler()


# ── Safety-net scan ────────────────────────────────────────────────────


def _scan_and_enqueue(processor: _Processor, inbox: Path) -> int:
    """Escanea inbox completo y encola lo que no este ya en cola."""
    pending = bronze.scan_inbox(inbox)
    enqueued = 0
    for path, source in pending:
        if processor.submit(path, source):
            enqueued += 1
    if enqueued:
        log.info("[watcher] safety-net scan: %d archivos encolados", enqueued)
    return enqueued


# ── CLI / main loop ───────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="data_pipeline.ingestion.watcher",
        description=(
            "Watcher de data/inbox/. Dispara los A2 loaders cuando llega "
            "un CSV nuevo."
        ),
    )
    p.add_argument(
        "--inbox", default=str(DEFAULT_INBOX),
        help="Directorio raiz de inbox (default: data/inbox/).",
    )
    p.add_argument(
        "--scan-on-start", action="store_true",
        help="Escanear inbox al arrancar y procesar lo pendiente.",
    )
    p.add_argument(
        "--safety-net-interval", type=int, default=1800,
        help="Segundos entre re-escaneos de inbox (default 1800 = 30 min). "
             "0 = deshabilitado.",
    )
    p.add_argument(
        "--once", action="store_true",
        help="Hacer un solo scan_inbox y salir (modo cron). Ignora watchdog.",
    )
    return p


def _main_once(inbox: Path) -> int:
    """Modo --once: un scan + drain + salir."""
    processor = _Processor()
    processor.start()
    enqueued = _scan_and_enqueue(processor, inbox)
    if enqueued == 0:
        log.info("[watcher] inbox vacio, nada que hacer.")
    # Esperar a que la cola se drene
    while True:
        with processor._lock:  # noqa: SLF001
            empty = not processor._queue and not processor._inflight
        if empty:
            break
        time.sleep(0.5)
    processor.stop()
    return 0


def _main_loop(inbox: Path, scan_on_start: bool, safety_net_interval: int) -> int:
    """Modo daemon: watchdog + safety-net periodico."""
    inbox.mkdir(parents=True, exist_ok=True)

    try:
        from watchdog.observers import Observer  # type: ignore
    except ImportError:
        log.error(
            "[watcher] falta 'watchdog'. Instalar: uv add watchdog (o "
            "agregar a pyproject y uv sync)."
        )
        return 1

    processor = _Processor()
    processor.start()

    if scan_on_start:
        log.info("[watcher] scan-on-start activo")
        _scan_and_enqueue(processor, inbox)

    handler = _make_handler(processor, inbox)
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=True)
    observer.start()
    log.info("[watcher] observando %s (recursive=True)", inbox)

    # Safety-net thread
    stop_event = threading.Event()
    if safety_net_interval > 0:
        def _safety_loop():
            while not stop_event.wait(timeout=safety_net_interval):
                try:
                    _scan_and_enqueue(processor, inbox)
                except Exception as exc:  # noqa: BLE001
                    log.warning("[watcher] safety-net error: %s", exc)

        t = threading.Thread(
            target=_safety_loop, name="watcher-safety-net", daemon=True,
        )
        t.start()
        log.info("[watcher] safety-net cada %ds", safety_net_interval)

    # SIGINT/SIGTERM -> apagado limpio
    shutdown = threading.Event()

    def _handle_signal(signum, _frame):
        log.info("[watcher] senal %s recibida, apagando...", signum)
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            # Algunos entornos (Windows, threads) no permiten todos los signals
            pass

    try:
        while not shutdown.is_set():
            shutdown.wait(timeout=1.0)
    finally:
        log.info("[watcher] deteniendo observer...")
        observer.stop()
        observer.join(timeout=10)
        stop_event.set()
        processor.stop(drain=True)
        log.info("[watcher] adios.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    inbox = Path(args.inbox).resolve()
    log.info("[watcher] inbox=%s once=%s scan_on_start=%s safety_net=%ds",
             inbox, args.once, args.scan_on_start, args.safety_net_interval)
    if args.once:
        return _main_once(inbox)
    return _main_loop(inbox, args.scan_on_start, args.safety_net_interval)


if __name__ == "__main__":
    sys.exit(main())
