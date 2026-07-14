# -*- coding: utf-8 -*-
# serve_watchdog.py
# 长期解决方案: Python http.server 跑久了 selector 会卡死,
# 这个 watchdog 每 30 秒 ping 一次, 卡了就杀重启, 永远不需手动修
#
# 用法: 双击 run_serve.bat, 它会起 watchdog + server, server 卡了自动重启
# 关闭: 关掉黑窗口 / Ctrl+C

import os
import sys
import time
import signal
import socket
import subprocess
import urllib.request
from pathlib import Path

PORT = 8765
SCRIPT_DIR = Path(__file__).parent.resolve()
SERVE_PY = SCRIPT_DIR / 'serve.py'
HEALTH_URL = f'http://127.0.0.1:{PORT}/index.html'
HEALTH_INTERVAL = 30  # 秒
RESTART_COOLDOWN = 5   # 重启后冷却多少秒再 ping (避免端口还没释放就误判)


def is_port_listening(port):
    """检查端口是否在 listen"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(('127.0.0.1', port))
            return True
        except OSError:
            return False


def health_check():
    """HTTP ping, 2 秒超时"""
    try:
        r = urllib.request.urlopen(HEALTH_URL, timeout=2)
        return r.status == 200
    except Exception:
        return False


def kill_old_serve():
    """杀掉所有 serve.py 进程"""
    try:
        # 找 python 进程, 命令行含 serve.py 的全杀
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='python.exe'",
             'get', 'processid,commandline', '/format:csv'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if 'serve.py' in line and str(SCRIPT_DIR).replace('\\', '\\\\') in line:
                # 提取 PID (第一列)
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[-1])
                        print(f'  [watchdog] 杀旧 serve.py pid={pid}')
                        subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                       capture_output=True)
                    except (ValueError, subprocess.SubprocessError):
                        pass
    except Exception as e:
        print(f'  [watchdog] kill_old_serve 出错: {e}')

    # 兜底: netstat 找 8765 占用进程杀了
    time.sleep(1)
    try:
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f':{PORT}' in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    print(f'  [watchdog] 杀 8765 占用 pid={pid}')
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                   capture_output=True)
    except Exception as e:
        print(f'  [watchdog] netstat 出错: {e}')


def start_serve():
    """后台启动 serve.py, 任何占着 8765 的进程先杀掉"""
    # 先杀占 8765 端口的进程 (可能别的项目残留)
    try:
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f':{PORT}' in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                    print(f'  [watchdog] 端口被占, 杀 pid={pid}')
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                   capture_output=True)
        time.sleep(1)
    except Exception as e:
        print(f'  [watchdog] 清理端口出错: {e}')

    log_out = SCRIPT_DIR / 'serve_out.log'
    log_err = SCRIPT_DIR / 'serve_err.log'
    print(f'  [watchdog] 启动 serve.py (端口 {PORT})')
    return subprocess.Popen(
        ['python', '-X', 'utf8', str(SERVE_PY), str(PORT)],
        stdout=open(log_out, 'w', encoding='utf-8'),
        stderr=open(log_err, 'w', encoding='utf-8'),
        creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        close_fds=True,
    )


def main():
    print('=' * 50)
    print(f'  serve_watchdog - 端口 {PORT}')
    print(f'  健康检查: 每 {HEALTH_INTERVAL}s ping 一次')
    print(f'  关闭: 关掉这个窗口 / Ctrl+C')
    print('=' * 50)

    # 防止多实例: 加锁文件
    lock_path = SCRIPT_DIR / '.watchdog.lock'
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text().strip())
            # 如果那个进程还在, 退出
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, existing_pid)
            if h:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(h)
                if exit_code.value == STILL_ACTIVE:
                    print(f'  [watchdog] 已有 watchdog 在跑 (pid={existing_pid}), 退出')
                    return 0
        except Exception:
            pass
    # 写锁
    lock_path.write_text(str(os.getpid()), encoding='utf-8')
    import atexit
    def cleanup():
        try:
            if lock_path.exists():
                current = int(lock_path.read_text().strip())
                if current == os.getpid():
                    lock_path.unlink()
        except Exception:
            pass
    atexit.register(cleanup)

    # 起一个 server
    proc = start_serve()

    # 等它起来
    for i in range(20):
        if is_port_listening(PORT):
            print(f'  [watchdog] server 已起')
            break
        time.sleep(0.5)
    else:
        print(f'  [watchdog] server 启动超时, 退出')
        proc.kill()
        return 1

    last_check = time.time()

    try:
        while True:
            time.sleep(5)
            now = time.time()
            if now - last_check < HEALTH_INTERVAL:
                continue
            last_check = now

            ok = health_check()
            alive = proc.poll() is None  # 进程是否还活着

            if ok and alive:
                print(f'  [{time.strftime("%H:%M:%S")}] ✓ 健康')
                continue

            if not alive:
                print(f'  [{time.strftime("%H:%M:%S")}] X server 进程死了')
            else:
                print(f'  [{time.strftime("%H:%M:%S")}] X server 卡死 (进程在, 但不响应)')

            # 重启
            print(f'  [{time.strftime("%H:%M:%S")}] 杀掉旧的')
            try:
                proc.kill()
            except Exception:
                pass
            kill_old_serve()

            time.sleep(RESTART_COOLDOWN)
            proc = start_serve()

            # 等它起
            for i in range(20):
                if is_port_listening(PORT):
                    print(f'  [{time.strftime("%H:%M:%S")}] ✓ 重启成功')
                    break
                time.sleep(0.5)

    except KeyboardInterrupt:
        print('\n  [watchdog] Ctrl+C, 关闭')
        try:
            proc.kill()
        except Exception:
            pass
        return 0


if __name__ == '__main__':
    sys.exit(main())