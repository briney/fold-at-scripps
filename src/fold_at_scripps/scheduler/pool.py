"""In-memory GPU pool owned by the single scheduler process."""

from __future__ import annotations


class GpuPool:
    """Tracks which GPU IDs are free and allocates them exclusively."""

    def __init__(self, gpu_ids: list[int]) -> None:
        self._all = list(gpu_ids)
        self._free = set(gpu_ids)

    @property
    def available(self) -> int:
        """Number of currently-free GPUs."""
        return len(self._free)

    def can_allocate(self, count: int) -> bool:
        """Whether ``count`` GPUs are currently free."""
        return count <= len(self._free)

    def try_allocate(self, count: int) -> list[int] | None:
        """Allocate ``count`` GPUs (lowest IDs first); return them, or None if too few."""
        if count > len(self._free):
            return None
        allocated = sorted(self._free)[:count]
        self._free.difference_update(allocated)
        return allocated

    def release(self, gpu_ids: list[int]) -> None:
        """Return GPUs to the free set (ignores IDs not owned by this pool)."""
        self._free.update(gpu_id for gpu_id in gpu_ids if gpu_id in self._all)
