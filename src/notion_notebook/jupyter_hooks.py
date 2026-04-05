"""IPython integration and filesystem watching for notebook saves."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

_WATCHED_NOTEBOOK_PATHS: set[str] = set()


class JupyterHooks:
    """Resolve the active notebook path from IPython and register save hooks."""

    @staticmethod
    def register_save_hook(callback: Callable[..., None]) -> None:
        """Register ``callback`` with IPython ``pre_save_hook`` when available.

        Parameters
        ----------
        callback
            Callable invoked as ``callback()`` before the notebook is written.

        Notes
        -----
        No-ops when not running inside IPython or when hooks are unavailable.
        IPython's :class:`~IPython.core.events.EventManager` only exposes
        execution events (for example ``pre_run_cell``), not notebook file
        saves; ``pre_save_hook`` is not a registered event name and is skipped
        without error. Sync after save still uses :class:`NotebookWatcher` when
        configured.
        """
        try:
            from IPython import get_ipython
        except ImportError:
            return
        ip = get_ipython()
        if ip is None:
            return

        def _hook(*_a: Any, **_k: Any) -> None:
            callback()

        ev = getattr(ip, "events", None)
        if ev is not None and hasattr(ev, "register"):
            try:
                ev.register("pre_save_hook", _hook)
            except (AttributeError, KeyError, TypeError):
                pass

    @staticmethod
    def get_notebook_path() -> str | None:
        """Return the absolute path to the current ``.ipynb`` when discoverable.

        Returns
        -------
        str or None
            Path string, or ``None`` when the runtime is not a Jupyter notebook.

        Notes
        -----
        Tries ``ipynbname``, then VS Code / Cursor ``__vsc_ipynb_file__`` in
        ``__main__``, then ``NOTION_NOTEBOOK_PATH`` for tests or manual override.
        """
        try:
            import ipynbname

            p = ipynbname.path()
            return str(p.resolve())
        except Exception:
            pass
        import os
        import sys

        envp = os.environ.get("NOTION_NOTEBOOK_PATH")
        if envp:
            return str(Path(envp).resolve())
        main = getattr(sys.modules.get("__main__"), "__dict__", None)
        if isinstance(main, dict):
            vsc = main.get("__vsc_ipynb_file__")
            if isinstance(vsc, str) and vsc.endswith(".ipynb"):
                return str(Path(vsc).resolve())
        return None

    @staticmethod
    def get_notebook_name() -> str | None:
        """Return the notebook filename including ``.ipynb`` when path is known.

        Returns
        -------
        str or None
        """
        p = JupyterHooks.get_notebook_path()
        if not p:
            return None
        return Path(p).name


class _WatchHandler(FileSystemEventHandler):
    def __init__(
        self,
        target: Path,
        callback: Callable[[], None],
        debounce_seconds: float,
    ) -> None:
        super().__init__()
        self._target = target.resolve()
        self._callback = callback
        self._debounce = debounce_seconds
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        p = Path(str(event.src_path)).resolve()
        if p != self._target:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        try:
            self._callback()
        except Exception:
            pass


class NotebookWatcher:
    """Watch a single ``.ipynb`` path and invoke a debounced callback on writes."""

    def __init__(
        self,
        notebook_path: str,
        callback: Callable[[], None],
        debounce_seconds: float = 2.0,
    ) -> None:
        """Configure a recursive watch on the notebook's parent directory.

        Parameters
        ----------
        notebook_path
            Absolute or relative path to the notebook file.
        callback
            Invoked after ``debounce_seconds`` quiet period following a save.
        debounce_seconds
            Delay to coalesce rapid writes.
        """
        self._path = Path(notebook_path).expanduser().resolve()
        self._callback = callback
        self._debounce = debounce_seconds
        self._observer: Any = None
        self._handler: _WatchHandler | None = None

    def start(self) -> None:
        """Start the background observer thread."""
        if self._observer is not None:
            return
        key = str(self._path)
        if key in _WATCHED_NOTEBOOK_PATHS:
            return
        parent = self._path.parent
        self._handler = _WatchHandler(self._path, self._callback, self._debounce)
        self._observer = Observer()
        self._observer.schedule(self._handler, str(parent), recursive=False)
        self._observer.start()
        _WATCHED_NOTEBOOK_PATHS.add(key)
        time.sleep(0.05)

    def stop(self) -> None:
        """Stop watching and join the observer thread."""
        if self._observer is None:
            return
        _WATCHED_NOTEBOOK_PATHS.discard(str(self._path))
        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._observer = None
        self._handler = None
