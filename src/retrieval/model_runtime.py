"""One local weight owner per pipeline; sequential use, not a concurrent request server."""
import gc
import sys


class SequentialModelRuntime:
    def __init__(self):
        self.owner = None
        self.events = []

    def acquire(self, owner):
        if self.owner is owner:
            return
        self.release()
        self.owner = owner
        try:
            owner._load_weights()
        except Exception:
            owner._unload_weights()
            self.owner = None
            raise
        self.events.append({'event': 'loaded', 'owner': type(owner).__name__})

    def release(self):
        if self.owner is None:
            return
        old, self.owner = self.owner, None
        old._unload_weights()
        self.events.append({'event': 'released', 'owner': type(old).__name__})
        del old
        gc.collect()
        # Do not import torch for TF-IDF/API-only tools.
        torch = sys.modules.get('torch')
        if torch is not None:
            cuda = getattr(torch, 'cuda', None)
            if cuda is not None and cuda.is_available():
                cuda.empty_cache()
            mps = getattr(torch, 'mps', None)
            backend = getattr(getattr(torch, 'backends', None), 'mps', None)
            if mps is not None and backend is not None and backend.is_available():
                mps.empty_cache()
