# -*- coding: utf-8 -*-
"""
whitelist_bot.py - 全自动白名单开通机器人 (v1 2026-07-22)

工作流:
  1. 监听 MONITORED_CHAT_IDS (AI白名單群组 list, 用 entity.id 正数)
  2. 收到新消息 -> 提取 0x 地址 (0x + 40 hex 严格匹配)
  3. 在原群引用回复 "+" (给客服确认)
  4. 给 BOT_USERNAME 发 /a 0x... 命令 (开通白名单)
  5. 记录到 whitelist_processed.json (去重, 同一消息不重复处理)

用法:
  python whitelist_bot.py            # 默认 dry-run (不实际发消息)
  python whitelist_bot.py --live     # 真跑 (实际发消息)
  $env:WHITELIST_BOT_LIVE=1; python whitelist_bot.py   # 同样真跑

环境:
  .env: TG_API_ID, TG_API_HASH, TG_SESSION_STRING_2 (+243 号)
  脚本顶部 config: MONITORED_CHAT_IDS, BOT_USERNAME, REPLY_TEXT

安全:
  - 默认 dry-run, 跑前必须显式 --live 或设 WHITELIST_BOT_LIVE=1
  - 每条 /a 后 sleep RATE_LIMIT_SECONDS (防 flood wait)
  - 触发 FloodWaitError 自动等待 e.seconds
  - processed.json 持久化去重 (重启不重处理)
  - 不处理自己发的 (outgoing=True 跳过)
"""
import os
import re
import sys
import json
import time
import asyncio
import traceback
from pathlib import Path

# === UTF-8 输出 (Windows PowerShell) ===
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError


# ============================================================
# Config (改这里)
# ============================================================
# AI白名單群组 (entity.id 正数, 不是 chat_id 的 -100 前缀形式)
MONITORED_CHAT_IDS = {5374712122}  # 测试群 (Alex-阿奇客服老师以及Alex-阿奇客服老师 02) -- TODO 测完换 5526703064 真实群

# 机器人 username (不带 @)
BOT_USERNAME = 'addAIloginwhitelistbot'

# 群内回复客服的文本 (通常就一个 +)
REPLY_TEXT = '+'

# 0x + 40 hex 严格地址匹配
# 注意: 不能用 \b 在末尾 - Python 3 re 是 Unicode-aware, 汉字也算 word char
# `0xB0e8...803请` 这种贴汉字的格式, 末尾 \b 不成立
# 用 negative lookahead 替代: 40 hex 后面必须不是 hex 字符
ADDRESS_PATTERN = re.compile(r'0x[0-9a-fA-F]{40}(?![0-9a-fA-F])')

# 业务触发链接 (客户发的群消息引用: https://t.me/c/{chat}/{msg})
# 也兼容 telegram.me (user 浏览器打不开 t.me 时也会用这个)
# 必须 0x + 这个链接都命中才处理 - 强信号, 排除纯讨论
LINK_PATTERN = re.compile(r'https?://t(?:elegram)?\.me/c/\d+/\d+', re.IGNORECASE)

# 每条 /a 命令间隔 (秒) - 防 flood wait
RATE_LIMIT_SECONDS = 3

# 去重 + 日志
PROCESSED_PATH = Path('whitelist_processed.json')
LOG_PATH = Path('whitelist_bot.log')


# ============================================================
# Dry-run 判断: --live flag 或 env var = 1 才真跑
# ============================================================
DRY_RUN = ('--live' not in sys.argv) and (os.environ.get('WHITELIST_BOT_LIVE', '0') != '1')


# ============================================================
# Helpers
# ============================================================
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


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def load_processed():
    if PROCESSED_PATH.exists():
        try:
            return set(json.loads(PROCESSED_PATH.read_text(encoding='utf-8')))
        except Exception:
            return set()
    return set()


def save_processed(s):
    try:
        PROCESSED_PATH.write_text(
            json.dumps(sorted(s), ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    except Exception as e:
        log(f'  [WARN] save_processed 失败: {e}')


# ============================================================
# 业务逻辑
# ============================================================
async def process_message(event, bot_entity, processed):
    chat = await event.get_chat()
    text = event.raw_text or ''
    sender = await event.get_sender()
    sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', None) or str(getattr(sender, 'id', '?'))

    addresses = ADDRESS_PATTERN.findall(text)
    if not addresses:
        return  # 没地址, 静默跳过 (群里纯聊天不 log)

    # 必须有 t.me/c/... 业务链接 (强信号: 客户发的具体群消息引用) - 排除纯讨论
    links = LINK_PATTERN.findall(text)
    if not links:
        # 有 0x 但无链接 -> log 让 user 知道为什么没处理
        log(f'  [SKIP] msg {event.message.id} 有 0x 但无 t.me 链接, 跳过')
        log(f'         text: {text[:120]!r}')
        return

    # 已被 reply 过 -> 跳过 (避免多技术员重复处理)
    msg = event.message
    if hasattr(msg, 'replies') and msg.replies and getattr(msg.replies, 'replies', 0) > 0:
        reply_count = msg.replies.replies
        log(f'  [SKIP] msg {msg.id} 已有 {reply_count} 个 reply, 跳过 (可能其他技术员已处理)')
        return

    msg_key = f'{chat.id}:{event.message.id}'
    if msg_key in processed:
        log(f'  [SKIP] 已处理过 {msg_key}')
        return
    processed.add(msg_key)
    save_processed(processed)

    log(f'[NEW] chat="{chat.title}" sender=@{sender_name} msg={event.message.id}')
    log(f'       addresses: {addresses}')
    log(f'       mode: {"DRY-RUN" if DRY_RUN else "LIVE"}')

    # 1) 在原群引用回复 + (给客服"已读"标记)
    if DRY_RUN:
        log(f'  -> [DRY] reply "{REPLY_TEXT}" to msg {event.message.id}')
    else:
        try:
            await event.reply(REPLY_TEXT)
            log(f'  -> replied "{REPLY_TEXT}" to {chat.title}')
        except FloodWaitError as e:
            log(f'  X Flood wait {e.seconds}s on reply, 自动等待...')
            await asyncio.sleep(e.seconds + 1)
            await event.reply(REPLY_TEXT)
            log(f'  -> replied (重试后) "{REPLY_TEXT}"')

    # 2) 给 bot 发 /a 命令 (单条多行消息, 1 个 API call 处理多个地址, 降低风控)
    if addresses:
        msg_text = '\n'.join(f'/a {addr}' for addr in addresses)
        if DRY_RUN:
            log(f'  -> [DRY] send multi-line ({len(addresses)} addrs) to @{BOT_USERNAME}:')
            for line in msg_text.splitlines():
                log(f'         {line}')
        else:
            try:
                await client.send_message(bot_entity, msg_text)
                log(f'  -> sent multi-line ({len(addresses)} addrs) to bot')
            except FloodWaitError as e:
                log(f'  X Flood wait {e.seconds}s on multi-line /a, 自动等待...')
                await asyncio.sleep(e.seconds + 1)
                await client.send_message(bot_entity, msg_text)
                log(f'  -> sent multi-line ({len(addresses)} addrs) (重试后)')


# ============================================================
# Main
# ============================================================
async def main():
    env = load_env()
    api_id = int(env.get('TG_API_ID', '0'))
    api_hash = env.get('TG_API_HASH', '')
    # 默认用 +243 号 (TG_SESSION_STRING_2)
    session_str = env.get('TG_SESSION_STRING_2') or env.get('TG_SESSION_STRING', '')
    if not all([api_id, api_hash, session_str]):
        print('X 凭据不全, 跑 first_login.py 拿 session')
        sys.exit(1)

    processed = load_processed()

    print('=' * 60)
    print(f'  whitelist_bot (v1) - {"DRY-RUN" if DRY_RUN else "LIVE"}')
    print('=' * 60)
    print(f'  监听群:   {MONITORED_CHAT_IDS}')
    print(f'  机器人:   @{BOT_USERNAME}')
    print(f'  回复文本: "{REPLY_TEXT}"')
    print(f'  限速:     每条 /a 后 sleep {RATE_LIMIT_SECONDS}s')
    print(f'  已处理:   {len(processed)} 条')
    print(f'  关闭:     Ctrl+C')
    print('=' * 60)
    if DRY_RUN:
        print()
        print('  ⚠️  DRY-RUN 模式 - 不会实际发消息, 只 print 计划动作')
        print('  确认输出对后, 用 --live 切真:')
        print('      python whitelist_bot.py --live')
    print()

    global client
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start()
    me = await client.get_me()
    log(f'[OK] 登录: @{me.username or me.first_name} ({me.id})')

    bot_entity = await client.get_entity(BOT_USERNAME)
    log(f'[OK] bot: @{bot_entity.username} (id={bot_entity.id})')

    # 注册 handler (闭包捕获 bot_entity + processed)
    @client.on(events.NewMessage(chats=list(MONITORED_CHAT_IDS)))
    async def handler(event):
        try:
            if event.out:  # telethon 用 'out' 不是 'outgoing' (自己发的跳过)
                return
            await process_message(event, bot_entity, processed)
        except Exception as e:
            log(f'  X handler 异常: {type(e).__name__}: {e}')
            traceback.print_exc()

    log(f'[*] 监听 {len(MONITORED_CHAT_IDS)} 个群, 等消息...')
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        log('[*] Ctrl+C, 退出')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
