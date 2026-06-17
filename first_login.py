# -*- coding: utf-8 -*-
# first_login.py
# 第一次登录 Telegram,生成 session string (以后用 scan_groups.py 不用再登录)
#
# 用法:
#   1. 在 https://my.telegram.org 申请 api_id / api_hash
#   2. 把下面两个值填进去
#   3. python first_login.py
#   4. 输手机号 (+86138...) -> 验证码 -> (如果开了 2FA) 二次验证密码
#   5. 打印出 session string, 保存到 TG_SESSION_STRING 环境变量或 tg_session.txt
#
# 安全提示:
#   - session string 等同于密码, 别人拿到能登你账号
#   - 推代码时不要提交 tg_session.txt 或 .env

import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

# ============== 填这里 ==============
API_ID = 0         # ← 改成你的 (int, e.g. 12345678)
API_HASH = ''      # ← 改成你的 (str, e.g. 'a1b2c3d4e5f6...')
# =====================================

if not API_ID or not API_HASH:
    print('X 请先填 API_ID 和 API_HASH (在本文件顶部)')
    print('  1. 浏览器打开 https://my.telegram.org')
    print('  2. 登录 -> API development tools')
    print('  3. Create application (App title 随便, Short name 英文)')
    print('  4. 拿到 api_id (数字) 和 api_hash (32字符hex) 填到本文件')
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

    with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        me = client.get_me()
        print()
        print('=' * 60)
        print(f'  登录成功! 你好 @{me.username or me.first_name}')
        print('=' * 60)
        print()
        session_str = client.session.save()
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
        with open('tg_session.txt', 'w', encoding='utf-8') as f:
            f.write(session_str)
        print(f'  已自动写入 tg_session.txt ({len(session_str)} 字符)')
        print()
        print('  方式 C: 写到 .env (跟脚本同目录)')
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(f'TG_API_ID={API_ID}\n')
            f.write(f'TG_API_HASH={API_HASH}\n')
            f.write(f'TG_SESSION_STRING={session_str}\n')
        print('  已自动写入 .env')
        print()
        print('下一步: python scan_groups.py')


if __name__ == '__main__':
    main()
