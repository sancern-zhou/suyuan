"""
Helper for running LibreOffice (soffice) in environments where AF_UNIX
sockets may be blocked (e.g., sandboxed VMs).  Detects the restriction
at runtime and applies an LD_PRELOAD shim if needed.

Usage:
    from app.tools.office.soffice import run_soffice, get_soffice_env

    # Option 1 – run soffice directly
    result = run_soffice(["--headless", "--convert-to", "pdf", "input.docx"])

    # Option 2 – get env dict for your own subprocess calls
    env = get_soffice_env()
    subprocess.run(["soffice", ...], env=env)
"""

import os
import socket
import subprocess
import tempfile
import shutil
from pathlib import Path


def _find_soffice_executable() -> str:
    """
    查找 LibreOffice 可执行文件

    Returns:
        soffice 命令或完整路径
    """
    # 首先检查 PATH 中是否有 soffice
    soffice_cmd = shutil.which("soffice")
    if soffice_cmd:
        return soffice_cmd

    # Windows 特定路径
    if os.name == "nt":
        possible_paths = [
            # 常见 LibreOffice 安装路径
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            # LibreOfficePortable 路径
            r"C:\PortableApps\LibreOfficePortable\App\libreoffice\program\soffice.exe",
        ]

        # 检查 Program Files 下的 LibreOffice 版本目录
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

        # 搜索 LibreOffice 目录
        for base_path in [program_files, program_files_x86]:
            try:
                libreoffice_path = Path(base_path) / "LibreOffice"
                if libreoffice_path.exists():
                    # 查找 program/soffice.exe
                    for root in libreoffice_path.rglob("soffice.exe"):
                        if "program" in str(root).lower():
                            return str(root)
            except Exception:
                continue

        # 检查预定义路径
        for path in possible_paths:
            if Path(path).exists():
                return path

    # Linux/macOS 特定路径
    else:
        possible_paths = [
            "/usr/bin/soffice",
            "/usr/local/bin/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/opt/libreoffice/program/soffice",
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

    # 如果都找不到，返回默认命令名（可能失败）
    return "soffice"


# 缓存找到的 soffice 路径
_soffice_path = None


def get_soffice_path() -> str:
    """获取 soffice 可执行文件路径"""
    global _soffice_path
    if _soffice_path is None:
        _soffice_path = _find_soffice_executable()
    return _soffice_path


def get_soffice_env() -> dict:
    env = os.environ.copy()
    env["SAL_USE_VCLPLUGIN"] = "svp"

    if _needs_shim():
        shim = _ensure_shim()
        env["LD_PRELOAD"] = str(shim)

    return env


def run_soffice(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    env = get_soffice_env()
    soffice = get_soffice_path()

    # 默认捕获输出，除非明确指定不捕获
    if 'stdout' not in kwargs and 'capture_output' not in kwargs:
        kwargs['capture_output'] = True
    if 'text' not in kwargs and 'encoding' not in kwargs and 'universal_newlines' not in kwargs:
        kwargs['text'] = True

    return subprocess.run([soffice] + args, env=env, **kwargs)



_SHIM_SO = Path(tempfile.gettempdir()) / "lo_socket_shim.so"


def _needs_shim() -> bool:
    # Windows 不支持 AF_UNIX，直接返回 False（不需要 shim）
    if not hasattr(socket, 'AF_UNIX'):
        return False

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.close()
        return False
    except OSError:
        return True


def _ensure_shim() -> Path:
    if _SHIM_SO.exists():
        return _SHIM_SO

    src = Path(tempfile.gettempdir()) / "lo_socket_shim.c"
    src.write_text(_SHIM_SOURCE)
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-o", str(_SHIM_SO), str(src), "-ldl"],
        check=True,
        capture_output=True,
    )
    src.unlink()
    return _SHIM_SO



_SHIM_SOURCE = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static int (*real_socket)(int, int, int);
static int (*real_socketpair)(int, int, int, int[2]);
static int (*real_listen)(int, int);
static int (*real_accept)(int, struct sockaddr *, socklen_t *);
static int (*real_close)(int);
static int (*real_read)(int, void *, size_t);

/* Per-FD bookkeeping (FDs >= 1024 are passed through unshimmed). */
static int is_shimmed[1024];
static int peer_of[1024];
static int wake_r[1024];            /* accept() blocks reading this */
static int wake_w[1024];            /* close()  writes to this      */
static int listener_fd = -1;        /* FD that received listen()    */

__attribute__((constructor))
static void init(void) {
    real_socket     = dlsym(RTLD_NEXT, "socket");
    real_socketpair = dlsym(RTLD_NEXT, "socketpair");
    real_listen     = dlsym(RTLD_NEXT, "listen");
    real_accept     = dlsym(RTLD_NEXT, "accept");
    real_close      = dlsym(RTLD_NEXT, "close");
    real_read       = dlsym(RTLD_NEXT, "read");
    for (int i = 0; i < 1024; i++) {
        peer_of[i] = -1;
        wake_r[i]  = -1;
        wake_w[i]  = -1;
    }
}

/* ---- socket ---------------------------------------------------------- */
int socket(int domain, int type, int protocol) {
    if (domain == AF_UNIX) {
        int fd = real_socket(domain, type, protocol);
        if (fd >= 0) return fd;
        /* socket(AF_UNIX) blocked – fall back to socketpair(). */
        int sv[2];
        if (real_socketpair(domain, type, protocol, sv) == 0) {
            if (sv[0] >= 0 && sv[0] < 1024) {
                is_shimmed[sv[0]] = 1;
                peer_of[sv[0]]    = sv[1];
                int wp[2];
                if (pipe(wp) == 0) {
                    wake_r[sv[0]] = wp[0];
                    wake_w[sv[0]] = wp[1];
                }
            }
            return sv[0];
        }
        errno = EPERM;
        return -1;
    }
    return real_socket(domain, type, protocol);
}

/* ---- listen ---------------------------------------------------------- */
int listen(int sockfd, int backlog) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        listener_fd = sockfd;
        return 0;
    }
    return real_listen(sockfd, backlog);
}

/* ---- accept ---------------------------------------------------------- */
int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        /* Block until close() writes to the wake pipe. */
        if (wake_r[sockfd] >= 0) {
            char buf;
            real_read(wake_r[sockfd], &buf, 1);
        }
        errno = ECONNABORTED;
        return -1;
    }
    return real_accept(sockfd, addr, addrlen);
}

/* ---- close ----------------------------------------------------------- */
int close(int fd) {
    if (fd >= 0 && fd < 1024 && is_shimmed[fd]) {
        int was_listener = (fd == listener_fd);
        is_shimmed[fd] = 0;

        if (wake_w[fd] >= 0) {              /* unblock accept() */
            char c = 0;
            write(wake_w[fd], &c, 1);
            real_close(wake_w[fd]);
            wake_w[fd] = -1;
        }
        if (wake_r[fd] >= 0) { real_close(wake_r[fd]); wake_r[fd]  = -1; }
        if (peer_of[fd] >= 0) { real_close(peer_of[fd]); peer_of[fd] = -1; }

        if (was_listener)
            _exit(0);                        /* conversion done – exit */
    }
    return real_close(fd);
}
"""



if __name__ == "__main__":
    import sys
    result = run_soffice(sys.argv[1:])
    sys.exit(result.returncode)
