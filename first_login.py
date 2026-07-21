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
# 多号支持 (v3 2026-07-22):
#   python first_login.py --field TG_SESSION_STRING_2 --phone +243975053618
#   会把 session 写到 .env 的 TG_SESSION_STRING_2 字段 (不冲掉 TG_SESSION_STRING)
#
# 安全提示:
#   - session string 等同于密码, 别人拿到能登你账号
#   - 推代码时不要提交 tg_session.txt 或 .env

import os
import sys
import re
import argparse
import traceback
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession

# ============== 填这里 ==============
API_ID = 36920517         # ← 改成你的 (int, e.g. 12345678)
API_HASH = 'f68f2474698af652d1aae0042e625164'      # ← 改成你的 (str, e.g. 'a1b2c3d4e5f6...')
# =====================================

if not API_ID or not API_HASH:
    print('X 请先填 API_ID 和 API_HASH (在本文件顶部)')
    sys.exit(1)


def write_env_field(env_path, field_name, value):
    """读 .env, 替换或追加 field_name=value, 写回 (不丢其他字段)"""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    pattern = re.compile(rf'^{re.escape(field_name)}=')
    replaced = False
    new_lines = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f'{field_name}={value}\n')
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f'{field_name}={value}\n')
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    return replaced


def ensure_env_api_creds(env_path, api_id, api_hash):
    """确保 .env 有 TG_API_ID / TG_API_HASH, 没有就追加 (不冲掉其他字段)"""
    text = ''
    if os.path.exists(env_path):
        text = Path(env_path).read_text(encoding='utf-8')
    if 'TG_API_ID=' not in text:
        write_env_field(env_path, 'TG_API_ID', str(api_id))
    if 'TG_API_HASH=' not in text:
        write_env_field(env_path, 'TG_API_HASH', api_hash)


def main():
    parser = argparse.ArgumentParser(description='Telegram first login (Telethon)')
    parser.add_argument('--field', default='TG_SESSION_STRING',
                        help='.env 里 session 字段名 (默认 TG_SESSION_STRING; 加号用 TG_SESSION_STRING_2)')
    parser.add_argument('--phone', default=None,
                        help='预填手机号 (含国际区号, e.g. +8613812345678 或 +243975053618)')
    parser.add_argument('--no-write', action='store_true',
                        help='不写文件, 只 print session string')
    args = parser.parse_args()

    print('=' * 60)
    print('  Telegram 登录 (Telethon)')
    print('=' * 60)
    print()
    print(f'API_ID:    {API_ID}')
    print(f'API_HASH:  {API_HASH[:6]}...{API_HASH[-4:]}')
    print(f'字段:      {args.field} (写到 .env)')
    if args.phone:
        print(f'预填手机:  {args.phone}')
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
        # 预填手机号: StringSession 不支持预填, 我们在 client 启动前 hint
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
    print(f'你的 session string ({len(session_str)} 字符, 复制下面整行包含外层引号):')
    print()
    print(session_str)
    print()

    if args.no_write:
        print('[--no-write] 跳过写文件, session 只打印到屏幕')
        return

    # tg_session.txt: 按 field 命名 (避免覆盖主号 session)
    suffix = '' if args.field == 'TG_SESSION_STRING' else '_' + args.field.replace('TG_SESSION_STRING', '').lstrip('_')
    tg_session_path = f'tg_session{suffix}.txt'
    try:
        with open(tg_session_path, 'w', encoding='utf-8') as f:
            f.write(session_str)
        print(f'  OK 已写入 {tg_session_path}')
    except Exception as e:
        print(f'  X 写 {tg_session_path} 失败: {e}')

    # .env: 追加/替换指定 field, 不冲掉其他字段
    try:
        # 先确保 API 凭据在 (不覆盖)
        ensure_env_api_creds('.env', API_ID, API_HASH)
        # 再写/替换 session field
        replaced = write_env_field('.env', args.field, session_str)
        if replaced:
            print(f'  OK 已更新 .env 的 {args.field} (替换原值)')
        else:
            print(f'  OK 已追加 .env 的 {args.field}')
    except Exception as e:
        print(f'  X 写 .env 失败: {e}')

    print()
    print('下一步:')
    if args.field == 'TG_SESSION_STRING':
        print('  python scan_groups_v2.py (扫主号群)')
    else:
        print(f'  python scan_groups_v2.py --account {args.field.replace("TG_SESSION_STRING", "").lstrip("_") or "2"} (扫这个号)')
    print()


if __name__ == '__main__':
    main()
