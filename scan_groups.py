# -*- coding: utf-8 -*-
# scan_groups.py
# 用 first_login.py 拿到的 session, 扫描你加入的所有群 + 每个群的所有话题,
# 导出 群组映射表.json
#
# 用法:
#   1. 先跑 first_login.py 拿到 session string (写到 tg_session.txt 或 .env)
#   2. python scan_groups.py
#   3. 等 5-15 分钟, 输出 群组映射表.json
#
# 输出格式:
#   {
#     "泰山（幸运）": {
#       "chat_id": -1001234567890,
#       "chat_username": null,
#       "topics": [
#         {"topic_id": 1234, "name": "天泽新社区"},
#         {"topic_id": 1235, "name": "另一话题"}
#       ]
#     },
#     ...
#   }
#
# 用途:
#   - gen_announce.py 根据公告里的"群-话题"查这个表, 生成 t.me/c/.../... 链接
#   - 一次性工作, 之后每天用

import os
import sys
import json
import asyncio
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetForumTopicsRequest
from telethon.tl.types import Channel, ForumTopic


def load_session_and_api():
    """从 .env / tg_session.txt / 环境变量 加载"""
    # 优先 .env
    if os.path.exists('.env'):
        env = {}
        for line in Path('.env').read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
        api_id = int(env.get('TG_API_ID', '0'))
        api_hash = env.get('TG_API_HASH', '')
        session_str = env.get('TG_SESSION_STRING', '')
        if api_id and api_hash and session_str:
            return api_id, api_hash, session_str

    # 兜底: tg_session.txt
    if os.path.exists('tg_session.txt'):
        session_str = Path('tg_session.txt').read_text(encoding='utf-8').strip()
        # session 字符串不带 api 凭据, 需要另外填
        api_id = int(os.environ.get('TG_API_ID', '0'))
        api_hash = os.environ.get('TG_API_HASH', '')
        if api_id and api_hash:
            return api_id, api_hash, session_str

    # 兜底: 环境变量
    api_id = int(os.environ.get('TG_API_ID', '0'))
    api_hash = os.environ.get('TG_API_HASH', '')
    session_str = os.environ.get('TG_SESSION_STRING', '')
    if api_id and api_hash and session_str:
        return api_id, api_hash, session_str

    print('X  找不到 api 凭据和 session, 请先跑 first_login.py')
    sys.exit(1)


def normalize_chat_title(title):
    """群名标准化: 去前后空格, 全角/半角统一, 括号统一"""
    if not title:
        return ''
    return title.strip()


async def scan():
    api_id, api_hash, session_str = load_session_and_api()
    print(f'[OK] 加载凭据: api_id={api_id}, session {len(session_str)} 字符')
    print()

    mapping = {}
    output_path = '群组映射表.json'

    # 已存在则增量更新, 不覆盖
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            print(f'[*] 已加载现有映射表: {len(mapping)} 个群')
        except Exception as e:
            print(f'[!] 现有映射表加载失败: {e}')
            mapping = {}

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        me = await client.get_me()
        print(f'[OK] 登录: @{me.username or me.first_name} ({me.id})')
        print()

        # 1) 拉所有对话, 过滤出群组
        print('[*] 拉取所有对话...')
        dialogs = await client.get_dialogs()
        group_dialogs = [d for d in dialogs if d.is_channel or d.is_group]
        print(f'[OK] 找到 {len(group_dialogs)} 个群/频道 (总共 {len(dialogs)} 个对话)')
        print()

        # 2) 对每个群, 拉话题 (如果是 forum)
        for i, dialog in enumerate(group_dialogs, 1):
            entity = dialog.entity
            if not isinstance(entity, Channel):
                continue
            if entity.broadcast:  # 纯广播频道没话题
                continue

            title = normalize_chat_title(entity.title)
            chat_id = entity.id  # 完整 chat_id (含 -100 前缀)
            chat_username = entity.username  # 公开群有 username, 私域群 None

            # 加载已有 topics 避免重扫
            existing = mapping.get(title, {})
            existing_topics = {t['topic_id']: t for t in existing.get('topics', [])}
            existing['chat_id'] = chat_id
            existing['chat_username'] = chat_username

            try:
                # 检查是否是 forum (有话题)
                topics_result = await client(GetForumTopicsRequest(
                    channel=entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=100,
                ))
                topics = topics_result.topics
                print(f'[{i}/{len(group_dialogs)}] {title}: {len(topics)} 个话题, chat_id={chat_id}')
            except Exception:
                # 不是 forum 或无权限, 跳过话题
                existing['topics'] = []
                mapping[title] = existing
                print(f'[{i}/{len(group_dialogs)}] {title}: (非 forum), chat_id={chat_id}')
                continue

            # 3) 翻页拉所有话题
            all_topics = list(topics)
            offset_topic = topics[-1].id if topics else 0
            while len(topics) == 100:
                try:
                    topics_result = await client(GetForumTopicsRequest(
                        channel=entity,
                        offset_date=None,
                        offset_id=0,
                        offset_topic=offset_topic,
                        limit=100,
                    ))
                    topics = topics_result.topics
                    if not topics:
                        break
                    all_topics.extend(topics)
                    offset_topic = topics[-1].id
                    await asyncio.sleep(0.5)  # 限流
                except Exception as e:
                    print(f'  [!] 翻页失败: {e}')
                    break

            # 4) 合并: 新话题加进去, 旧话题保留
            new_topics = []
            for t in all_topics:
                if not isinstance(t, ForumTopic):
                    continue
                # 优先用旧名字 (可能你手动改过)
                old = existing_topics.get(t.id)
                name = old['name'] if old else (t.title.strip() if t.title else f'话题{t.id}')
                new_topics.append({'topic_id': t.id, 'name': name})

            existing['topics'] = new_topics
            mapping[title] = existing
            print(f'  -> {len(new_topics)} 个话题')

            await asyncio.sleep(0.3)  # 限流, 避免触发

            # 每 10 个群保存一次, 防止中断丢数据
            if i % 10 == 0:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=2)
                print(f'  [已保存] {output_path}')

    # 5) 最终保存
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print()
    print('=' * 60)
    print(f'  完成! 映射表: {output_path}')
    print(f'  群数: {len(mapping)}')
    total_topics = sum(len(g.get("topics", [])) for g in mapping.values())
    print(f'  话题总数: {total_topics}')
    print('=' * 60)


if __name__ == '__main__':
    asyncio.run(scan())
