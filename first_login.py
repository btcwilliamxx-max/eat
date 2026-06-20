# -*- coding: utf-8 -*-
# first_login.py
# 第一次登录 Telegram, 生成 session string (以后用 scan_groups.py 不用再登录)
#
# 用法:
#   1. 在 https://my.telegram.org 申请 api_id / api_hash
#   2. 把下面两个值填进去
#   3. python first_login.py
#   4. 输手机号 (+86138...) -> 验证码 -> (如果开了 2FA) 二次验证密码
#   5. 打印出 session string, 保存到 tg_session.txt / .env
#
# 安全提示:
#   - session string 等同于密码, 别人拿到能登你账号
#   - 推代码时不要提交 tg_session.txt 或 .env

import os
import sys
import traceback
from telethon import TelegramClient
from telethon.sessions import StringSession

# ============== 填这里 ==============
API_ID = 36920517         # ← 改成你的 (int, e.g. 12345678)
API_HASH = 'f68f2474698af652d1aae0042e625164'      # ← 改成你的 (str, e.g. 'a1b2c3d4e5f6...')
# =====================================

if not API_ID or not API_HASH:
    print('X 请先填 API_ID 和 API_HASH (在本文件顶部)')
    sys.exit(1)


def main():
    print('=' * 60)
    print('  第一次登录 Telegram (Telethon)')
    print('=' * 60)
    print()
    print(f'API_ID:    {API_ID}')
    print(f'API_HASH:  {API_HASH[:6]}...{API_HASH[-4:]}')
    print()
    print('会问你:')
    print('  - Phone:    你的手机号 (含国际区号, e.g. +8613812345678)')
    print('  - Code:     Telegram 客户端收到的验证码')
    print('  - Password: 如果你开了两步验证 (2FA), 输密码; 没开直接回车')
    print()

    # 用 with 块登录交互, 拿到 session 后 **先断开**, 再 print
    # 避免 disconnect 异常导致 print 闪退
    # 注意: 新版 telethon 的 get_me 是异步的, 但我们不需要它, session 已经存好
    session_str = None
    try:
        with TelegramClient(StringSession(), API_ID, API_HASH) as client:
            # telethon 登录成功后会自动打印 "Signed in successfully as ..."
            # 这里只拿 session string, 不调 get_me
            session_str = client.session.save()
    except Exception as e:
        print(f'X 登录失败: {e}')
        traceback.print_exc()
        sys.exit(1)

    # with 块已退出, 资源已释放. 下面安全 print 和写文件
    print()
    print('=' * 60)
    print('  登录成功! (telethon 已在上方打印账号名)')
    print('=' * 60)
    print()
    print('你的 session string (复制下面整行, 包含外层引号):')
    print()
    print(session_str)
    print()
    print('保存方式 (任选一种):')
    print()
    print('  方式 A: 环境变量 (推荐, 不进文件)')
    print('    PowerShell:  $env:TG_SESSION_STRING = "' + session_str[:30] + '..."')
    print()
    print('  方式 B: 写到 tg_session.txt (跟脚本同目录)')
    try:
        with open('tg_session.txt', 'w', encoding='utf-8') as f:
            f.write(session_str)
        print(f'  OK 已写入 tg_session.txt ({len(session_str)} 字符)')
    except Exception as e:
        print(f'  X 写 tg_session.txt 失败: {e}')

    print()
    print('  方式 C: 写到 .env (跟脚本同目录)')
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(f'TG_API_ID={API_ID}\n')
            f.write(f'TG_API_HASH={API_HASH}\n')
            f.write(f'TG_SESSION_STRING={session_str}\n')
        print('  OK 已写入 .env')
    except Exception as e:
        print(f'  X 写 .env 失败: {e}')

    print()
    print('下一步: python scan_groups.py')
    print()


if __name__ == '__main__':
    main()
