"""Reentrant locks scoped to live device/recipient work, not retained forever."""

import threading
import weakref


class _Entry:
    def __init__(self, lock=None):
        self.lock = lock if lock is not None else threading.RLock()

    def acquire(self, *args, **kwargs):
        return self.lock.acquire(*args, **kwargs)

    def release(self):
        self.lock.release()


class DeviceLocks:
    def __init__(self):
        self._guard = threading.Lock()
        self._locks = weakref.WeakValueDictionary()

    def get(self, key, preferred=None):
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = _Entry(preferred)
                self._locks[key] = lock
            return lock

    def snapshot(self, kinds=("send", "wire")):
        with self._guard:
            return [lock for key, lock in self._locks.items() if key[0] in kinds]
