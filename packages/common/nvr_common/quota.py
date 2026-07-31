"""Disk quota helpers shared across NVR services.

SeaweedFS / NFS mounts often report the entire cluster size instead of the
slice we want to consume. ``apply_disk_quota`` caps usage numbers to a
configured quota so retention, analytics and the UI see the intended budget.
"""

from __future__ import annotations

import os


def apply_disk_quota(
    usage_total: int,
    usage_used: int,
    usage_free: int,
    quota_bytes: int | None,
) -> tuple[int, int, int]:
    """Cap disk-usage numbers to a configured quota.

    When ``quota_bytes`` is set, treat the backend as if it only has that
    much capacity. Returns ``(effective_total, effective_used,
    effective_free)``.
    """
    if not quota_bytes or quota_bytes <= 0:
        return usage_total, usage_used, usage_free
    effective_total = min(usage_total, quota_bytes)
    effective_used = min(usage_used, effective_total)
    effective_free = min(usage_free, effective_total - effective_used)
    return effective_total, effective_used, effective_free


def directory_size_bytes(path: str) -> int:
    """Sum file sizes under ``path`` (best-effort, follows symlinks to files).

    Used for NFS / SeaweedFS mounts where ``shutil.disk_usage`` reports the
    whole cluster size and cluster-wide used/free rather than the slice used
    by this application.
    """
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                    if os.path.isfile(full):
                        total += st.st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total
