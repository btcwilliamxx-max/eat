# -*- coding: utf-8 -*-
# serve.py
# 起一个本地 http server, 让 build_index.py 跑完用 http:// 协议打开 index.html
# 解决 navigator.clipboard.write() 在 file:// 下被浏览器禁用的问题
#
# 用法:
#   python serve.py [port]
#   默认端口 8765, 浏览器打开 http://localhost:8765/index.html
#
# 关闭: Ctrl+C

import sys
import os
import socket
import threading
import http.server
import socketserver
import webbrowser
from pathlib import Path


DEFAULT_PORT = 8765
ROOT = Path(__file__).parent.resolve()


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True


def find_free_port(start):
    """从 start 开始找一个空端口"""
    for p in range(start, start + 20):
        if not is_port_in_use(p):
            return p
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # 简化日志
        sys.stderr.write(f'  [{self.log_date_time_string()}] {fmt % args}\n')


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f'X 端口参数无效: {sys.argv[1]}')
            sys.exit(1)

    if is_port_in_use(port):
        # 端口被占, 说明已经有一个 server 在跑
        print(f'[*] 端口 {port} 已被占用, 假设 server 已启动')
        print(f'[*] 浏览器访问 http://localhost:{port}/index.html')
        # 不自动开 tab, 避免双击 build_index 时开 2 个 tab
        return 0

    print(f'  根目录: {ROOT}')
    print(f'  端口:   {port}')
    print(f'  打开:   http://localhost:{port}/index.html')
    print(f'  Ctrl+C 关闭')
    print()

    with socketserver.TCPServer(('0.0.0.0', port), Handler) as httpd:
        # 不自动开 tab, 由 build_index.py 调用时统一开
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n关闭 server')
            httpd.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
