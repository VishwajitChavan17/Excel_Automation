"""
app.ui.widgets.background_task
================================
Every plugin widget that runs a worker (Duplicate Finder, Compare, Lookup &
Copy, file loading) needs the same QThread plumbing: create a thread, move
the worker onto it, wire started/finished, and keep a reference alive so
Python doesn't garbage-collect the thread mid-run. This helper centralizes
that so plugin code just does:

    thread = start_worker(self, worker, worker.finished, self._on_done)

and doesn't need to hand-roll QThread lifecycle management five times.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread


def start_worker(owner: QObject, worker: QObject) -> QThread:
    """
    Move `worker` onto a new QThread parented to `owner`'s lifetime (the
    caller must keep the returned QThread referenced, e.g. in a list
    attribute, until it finishes -- Qt does not keep it alive for you).

    IMPORTANT: the caller must *also* keep a direct reference to `worker`
    itself (e.g. `self._active_worker = worker`) for as long as the thread
    runs. moveToThread() does not root the Python wrapper object against
    garbage collection -- if nothing but the QThread's internal C++ pointer
    references it, Python can (and, under GC pressure, will) collect the
    worker before the new thread gets a chance to invoke run(), silently
    dropping the job. This is the single most common bug in this codebase's
    worker-thread code; every plugin that calls this function stores the
    worker on `self` right next to the thread for exactly this reason.

    Assumes `worker` exposes a no-argument `run()` method and eventually
    emits some completion signal that the caller has already connected.
    This helper only wires the thread lifecycle (start / cleanup), not the
    worker's business signals.
    """
    thread = QThread(owner)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    def _cleanup() -> None:
        if thread.isRunning():
            thread.quit()
            thread.wait(2000)

    thread.finished.connect(_cleanup)
    thread.finished.connect(thread.deleteLater)

    return thread
