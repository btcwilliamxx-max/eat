# -*- coding: utf-8 -*-
"""
find_chat_id.py - 列出 +243 号所有 dialog, 帮 user 找真实群 chat_id

用法:
  python find_chat_id.py                  # 列出所有 group/supergroup/channel
  python find_chat_id.py 白名单            # 只列含"白名单"关键字的群
  python find_chat_id.py AI                # 只列含"AI"关键字的群
  python find_chat_id.py 白名單            # 繁体也支持

输出格式:
  chat_id (剥 -100 前缀) | type | username | 群名

注意:
  - 用 +243 号 (TG_SESSION_STRING_2) 扫
  - 不会发任何消息, 纯 read-only
  - 不会写任何文件
"""
import os
import sys
import asyncio
from pathlib import Path

# UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User


def load_env():
    env = {}
    if os.path.exists('.env'):
        for line in Path('.env').read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def normalize_chat_id(raw_id):
    """把 -100XXXXXXXXXX 剥成 10 位正数 (跟 whitelist_bot.py / t.me/c/ 对齐)"""
    s = str(raw_id)
    if s.startswith('-100'):
        return int(s[4:])
    return int(s)


async def main():
    env = load_env()
    api_id = int(env.get('TG_API_ID', '0'))
    api_hash = env.get('TG_API_HASH', '')
    # 默认用 +243 号
    session_str = env.get('TG_SESSION_STRING_2') or env.get('TG_SESSION_STRING', '')
    if not all([api_id, api_hash, session_str]):
        print('X 凭据不全, 跑 first_login.py')
        sys.exit(1)

    # 关键字过滤 (可选)
    filter_kw = sys.argv[1] if len(sys.argv) > 1 else None

    print('=' * 80)
    print(f'  find_chat_id - 列 +243 号所有 dialog')
    if filter_kw:
        print(f'  关键字过滤: "{filter_kw}"')
    print('=' * 80)

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        me = await client.get_me()
        print(f'登录: @{me.username or me.first_name} (id={me.id})')
        print('拉 dialogs (可能几秒)...\n')

        dialogs = await client.get_dialogs()
        groups = []
        for d in dialogs:
            entity = d.entity
            if isinstance(entity, Channel):
                if entity.broadcast:  # 纯广播频道 (没群功能)
                    continue
                cid = normalize_chat_id(entity.id)
                ctype = 'supergroup'  # Channel + non-broadcast = megagroup/supergroup
                uname = f'@{entity.username}' if entity.username else ''
            elif isinstance(entity, Chat):
                cid = entity.id
                ctype = 'group'
                uname = ''
            else:
                # 私聊 (User) - 跳过
                continue
            title = getattr(entity, 'title', None) or '?'
            if filter_kw and filter_kw not in title:
                continue
            groups.append((cid, ctype, uname, title))

        print(f'找到 {len(groups)} 个群 (总 dialogs: {len(dialogs)})\n')

        if not groups:
            if filter_kw:
                print(f'(没有群名包含 "{filter_kw}", 不带关键字再跑一次看全部)')
            return

        # 按 chat_id 升序
        groups.sort(key=lambda x: x[0])
        print(f'{"chat_id":<14} {"type":<11} {"username":<22} 名称')
        print('-' * 80)
        for cid, ctype, uname, title in groups:
            print(f'{cid:<14} {ctype:<11} {uname:<22} {title}')

        print()
        print('=' * 80)
        print('  使用方法:')
        print('  - 找到 "AI白名單" 那个群, 把 chat_id 给我')
        print('  - 我会替换 whitelist_bot.py 的 MONITORED_CHAT_IDS')
        print('  - 如果群名不在这里, 说明 +243 号还没加入那个群')
        print('=' * 80)


if __name__ == '__main__':
    asyncio.run(main())
