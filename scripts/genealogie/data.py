import json
import threading
from .config import DATA_FILE

# Module-level lock ensures only one thread reads/writes famille.json at a time.
_lock = threading.Lock()


def load_data():
    """Return the full famille.json as a Python dict."""
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    """Overwrite famille.json with the given dict (pretty-printed, UTF-8)."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
        _lock.acquire()
        self._data = load_data()
        return self._data

    def __exit__(self, exc_type, *_):
        if exc_type is None:   # only persist if the block completed without error
            save_data(self._data)
        _lock.release()
