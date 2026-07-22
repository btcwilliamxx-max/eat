# -*- coding: utf-8 -*-
"""
whitelist_bot_v2.py - 监听 AI白名單群, 等 bot 反馈后动态 reply (v2 2026-07-22)

工作流 (V2 vs V1 区别):
  1. 监听 MONITORED_CHAT_IDS (群, 用 entity.id 正数)
  2. 收到新消息 -> 预校验 0x 候选
     - 有 invalid (少几位) 但没 valid (40 hex) -> reply "地址不对", 不发 bot
  3. 单地址 (1 个 valid):
     - 发 /a 给 bot
     - 等 bot 反馈 (timeout 10s, 用 telethon Conversation)
     - 解析反馈: "登入白名單是否已存在: 否" -> 新加, reply "+"
                 "登入白名單是否已存在: 是" -> 已开, reply "之前已经加过了"
     - 解析失败 -> 不 reply
  4. 多地址 (>=2 个 valid):
     - 发多行 /a 给 bot
     - **不** reply (bot 对多地址反馈不区分新/旧, 按用户要求不处理)

用法:
  python whitelist_bot_v2.py              # 默认 dry-run (不实际发消息)
  python whitelist_bot_v2.py --live      # 真跑
  python whitelist_bot_v2.py --chat-id 5374712122  # 切到测试群
  python whitelist_bot_v2.py --chat-id 5374712122,5526703064  # 多群

环境:
  .env: TG_API_ID, TG_API_HASH, TG_SESSION_STRING_2 (+243 号)

安全:
  - 默认 dry-run, 跑前必须显式 --live 或设 WHITELIST_BOT_LIVE=1
  - 单地址场景会等 bot 反馈 (10s timeout), 多地址不 reply
  - 预校验: 格式不对的地址直接 reply, 不发 bot (节省 bot 配额)
  - processed.json 持久化去重
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
# Config
# ============================================================
DEFAULT_CHAT_IDS = [5526703064]  # 真实 AI白名單 群 (entity.id)
BOT_USERNAME = 'addAIloginwhitelistbot'
REPLY_NEW = '+'                  # bot 反馈"新加"时 reply
REPLY_EXISTS = '之前已经加过了'   # bot 反馈"已开过"时 reply
REPLY_INVALID = '地址不对'        # 预校验失败 reply
BOT_FEEDBACK_TIMEOUT = 10        # 等 bot 反馈 timeout (秒)

# 预校验: 0x + 任意长度 hex (找所有候选, 分类 valid/invalid)
# 完整 0x 地址 = 0x + 40 hex = 42 字符
CANDIDATE_PATTERN = re.compile(r'0x[0-9a-fA-F]+')

# 去重 + 日志 (V2 独立, 不跟 V1 共享)
PROCESSED_PATH = Path('whitelist_v2_processed.json')
LOG_PATH = Path('whitelist_v2.log')


# ============================================================
# Dry-run / parse chat ids (跟 V1 一样)
# ============================================================
DRY_RUN = ('--live' not in sys.argv) and (os.environ.get('WHITELIST_BOT_LIVE', '0') != '1')


def parse_chat_ids():
    """优先级: CLI --chat-id > env WHITELIST_BOT_CHAT_IDS > DEFAULT_CHAT_IDS"""
    for i, arg in enumerate(sys.argv):
        if arg == '--chat-id' and i + 1 < len(sys.argv):
            return [int(x.strip()) for x in sys.argv[i + 1].split(',') if x.strip()]
    env_val = os.environ.get('WHITELIST_BOT_CHAT_IDS', '')
    if env_val.strip():
        return [int(x.strip()) for x in env_val.split(',') if x.strip()]
    return list(DEFAULT_CHAT_IDS)


MONITORED_CHAT_IDS = set(parse_chat_ids())


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
# Bot 反馈解析
# ============================================================
def parse_bot_feedback(text):
    """解析 bot 反馈:
    - '登入白名單是否已存在：否' -> 新加
    - '登入白名單是否已存在：是' -> 已开过
    返回: 'new' / 'exists' / None
    """
    if not text:
        return None
    m = re.search(r'登入白名單是否已存在[：:]\s*(是|否)', text)
    if not m:
        return None
    return 'exists' if m.group(1) == '是' else 'new'


# ============================================================
# 业务逻辑
# ============================================================
async def wait_bot_response(client, bot_entity, cmd, timeout=BOT_FEEDBACK_TIMEOUT):
    """发 /a 给 bot, 用 Conversation 等 bot 反馈
    返回 bot 反馈文本 (str) 或 None (timeout/异常)
    """
    try:
        async with client.conversation(bot_entity, timeout=timeout) as conv:
            await conv.send_message(cmd)
            response = await conv.get_response()
            return response.text or ''
    except (asyncio.TimeoutError, TimeoutError):
        return None
    except Exception as e:
        log(f'  X 等 bot 反馈异常: {type(e).__name__}: {e}')
        return None


async def reply_to_csk(event, text, log_label):
    """reply 客服 + FloodWait 处理"""
    if DRY_RUN:
        log(f'  -> [DRY] reply "{text}" to msg {event.message.id}')
        return
    try:
        await event.reply(text)
        log(f'  -> replied "{text}" ({log_label})')
    except FloodWaitError as e:
        log(f'  X Flood wait {e.seconds}s on reply ({log_label}), 自动等待...')
        await asyncio.sleep(e.seconds + 1)
        await event.reply(text)
        log(f'  -> replied "{text}" (重试后)')


async def process_message(event, bot_entity, processed, client):
    chat = await event.get_chat()
    text = event.raw_text or ''
    sender = await event.get_sender()
    sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', None) or str(getattr(sender, 'id', '?'))

    # 预校验: 找所有 0x 候选 (任意长度)
    all_candidates = CANDIDATE_PATTERN.findall(text)
    if not all_candidates:
        return  # 没 0x, 静默跳过

    valid_addresses = [c for c in all_candidates if len(c) == 42]   # 0x + 40 hex
    invalid_candidates = [c for c in all_candidates if len(c) != 42]  # 少几位 / 多几位

    # 全部 invalid (没 valid) -> reply "地址不对", 不发 bot
    if invalid_candidates and not valid_addresses:
        log(f'[INVALID] msg {event.message.id} 有 {len(invalid_candidates)} 个无效地址 (缺几位/多几位)')
        for inv in invalid_candidates:
            log(f'           invalid: {inv} (hex_len={len(inv)-2})')
        await reply_to_csk(event, REPLY_INVALID, 'invalid')
        return  # 不发 bot, 不走原流程

    # 至少 1 个 valid -> 走流程
    addresses = valid_addresses

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
    log(f'       addresses: {addresses} (count={len(addresses)})')
    log(f'       mode: {"DRY-RUN" if DRY_RUN else "LIVE"}')

    # 多地址 (>=2) -> 发多行 /a -> reply "已开" (通用, 客服需要反馈)
    # (之前设计"不 reply" 但客服看不到反馈, 改 reply 通用文本)
    if len(addresses) >= 2:
        msg_text = '\n'.join(f'/a {addr}' for addr in addresses)
        if DRY_RUN:
            log(f'  -> [DRY] send multi-line ({len(addresses)} addrs) to @{BOT_USERNAME}:')
            for line in msg_text.splitlines():
                log(f'         {line}')
            log(f'  -> [DRY] reply "已开" (多地址场景, 通用)')
        else:
            try:
                await client.send_message(bot_entity, msg_text)
                log(f'  -> sent multi-line ({len(addresses)} addrs) to bot')
            except FloodWaitError as e:
                log(f'  X Flood wait {e.seconds}s, 自动等待...')
                await asyncio.sleep(e.seconds + 1)
                await client.send_message(bot_entity, msg_text)
                log(f'  -> sent (重试后)')
            # reply 通用 "已开" (多地址场景 bot 不区分新/旧)
            await reply_to_csk(event, '已开', 'multi-addr')
        return

    # 单地址 -> 发 /a (用 Conversation, 只发 1 次) -> 等 bot 反馈 -> 根据反馈 reply
    addr = addresses[0]
    cmd = f'/a {addr}'

    if DRY_RUN:
        log(f'  -> [DRY] (Conversation 内部发) "{cmd}" to @{BOT_USERNAME}')
        log(f'  -> [DRY] 等 bot 反馈 (timeout {BOT_FEEDBACK_TIMEOUT}s)')
        log(f'  -> [DRY] (假设新加) reply "{REPLY_NEW}"')
        return

    # 直接用 Conversation (wait_bot_response 内部只发 1 次, 避免重复)
    bot_text = await wait_bot_response(client, bot_entity, cmd)
    if not bot_text:
        log(f'  X bot 反馈 timeout ({BOT_FEEDBACK_TIMEOUT}s) 或无反馈')
        log(f'  (无 bot 反馈) 不 reply')
        return

    log(f'  <- bot: {bot_text[:200]!r}')

    status = parse_bot_feedback(bot_text)
    if status == 'new':
        await reply_to_csk(event, REPLY_NEW, 'new')
    elif status == 'exists':
        await reply_to_csk(event, REPLY_EXISTS, 'exists')
    else:
        log(f'  (无法解析 bot 反馈) 不 reply')


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
    print(f'  whitelist_bot (V2) - {"DRY-RUN" if DRY_RUN else "LIVE"}')
    print('=' * 60)
    print(f'  监听群:   {MONITORED_CHAT_IDS}')
    print(f'  机器人:   @{BOT_USERNAME}')
    print(f'  新加 reply: "{REPLY_NEW}"')
    print(f'  已开 reply: "{REPLY_EXISTS}"')
    print(f'  无效 reply: "{REPLY_INVALID}"')
    print(f'  bot 反馈 timeout: {BOT_FEEDBACK_TIMEOUT}s')
    print(f'  已处理:   {len(processed)} 条')
    print(f'  关闭:     Ctrl+C')
    print('=' * 60)
    if DRY_RUN:
        print()
        print('  ⚠️  DRY-RUN 模式 - 不会实际发消息, 只 print 计划动作')
        print('  确认输出对后, 用 --live 切真:')
        print('      python whitelist_bot_v2.py --live')
    print()

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start()
    me = await client.get_me()
    log(f'[OK] 登录: @{me.username or me.first_name} ({me.id})')

    bot_entity = await client.get_entity(BOT_USERNAME)
    log(f'[OK] bot: @{bot_entity.username} (id={bot_entity.id})')

    @client.on(events.NewMessage(chats=list(MONITORED_CHAT_IDS)))
    async def handler(event):
        try:
            if event.out:
                return
            await process_message(event, bot_entity, processed, client)
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
