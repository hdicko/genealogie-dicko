import json
# Note 1: threading is part of Python's standard library and provides
# POSIX-thread-based concurrency. A single Lock is sufficient here because
# the HTTP server runs one handler thread per request.
import threading
import os
import tempfile
from .config import DATA_FILE

# Note 2: A module-level lock (not instance-level) ensures mutual exclusion
# across ALL handler instances spawned by the HTTP server. Because the lock
# is bound to the module object, every import of this module shares the same
# lock instance regardless of how many threads are running.
# Module-level lock ensures only one thread reads/writes famille.json at a time.
_lock = threading.Lock()


def load_data():
    """Return the full famille.json as a Python dict."""
    # Note 3: json.load() reads from a file object, which is more memory-efficient
    # than json.loads(file.read()) for large files because it streams the JSON.
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    """Atomically overwrite famille.json with the given dict (pretty-printed, UTF-8).

    Writes to a temporary file in the same directory and then replaces the
    canonical file with os.replace() to ensure the update is atomic.
    """
    dirpath = os.path.dirname(str(DATA_FILE))
    # Use tempfile in the same directory to ensure atomic rename works across
    # filesystems when possible.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dirpath, delete=False) as tf:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.flush()
        os.fsync(tf.fileno())
        tmpname = tf.name
    # Use os.replace for atomic rename (overwrites target if present)
    os.replace(tmpname, str(DATA_FILE))


class DataTransaction:
    """Atomic read-modify-write wrapper for famille.json.

    Usage:
        with DataTransaction() as data:
            data["personnes"]["I1"]["nom"] = "New Name"
        # data is saved automatically on __exit__ (only if no exception).

    The threading lock is held for the entire block, so concurrent HTTP
    requests from the browser cannot corrupt the file.
    """

    def __enter__(self):
        # Note 5: Acquiring the lock here (not in __init__) ensures the lock
        # is held for exactly the duration of the 'with' block -- no longer.
        _lock.acquire()
        self._data = load_data()
        return self._data

    def __exit__(self, exc_type, *_):
        # Note 6: exc_type is None when the 'with' block exits without raising.
        # Only persisting on success prevents half-applied edits from being saved,
        # which would leave the JSON file in an inconsistent state.
        if exc_type is None:   # only persist if the block completed without error
            save_data(self._data)
        # Note 7: _lock.release() is called unconditionally (in both success and
        # error paths) so the lock is never left permanently held after an exception.
        _lock.release()
