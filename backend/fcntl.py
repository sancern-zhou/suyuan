"""Windows shim for the POSIX-only ``fcntl`` module.

DEPLOYMENT PATCH (2026-09-20): the project/jiangsu-ops branch targets Linux and
nine modules call ``fcntl.flock`` at module import or runtime time. This shim
provides the minimal flock() byte-range locking used by the backend on top of
``msvcrt.locking`` (always locks byte 0 of the file, which matches the
lock-file usage pattern in this codebase). It does not implement the rest of
fcntl. On POSIX systems this file must not shadow the stdlib module — it is
untracked on the deployment server only.
"""
import msvcrt
import os

LOCK_SH = 0x01
LOCK_EX = 0x02
LOCK_NB = 0x04
LOCK_UN = 0x08


def flock(fd, operation):
    if hasattr(fd, "fileno"):
        fd = fd.fileno()
    if operation & LOCK_UN:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    if operation & LOCK_SH:
        mode = msvcrt.LK_NBRLCK if operation & LOCK_NB else msvcrt.LK_RLCK
    else:
        mode = msvcrt.LK_NBLCK if operation & LOCK_NB else msvcrt.LK_LOCK
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, mode, 1)


def ioctl(fd, request, arg):
    raise OSError("fcntl.ioctl is not available on this Windows deployment")
