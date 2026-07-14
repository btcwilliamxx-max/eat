# -*- coding: utf-8 -*-
# scan_groups_v2.py
# 相比 v1:
#   - 强制 UTF-8 stdout (避免 GBK 污染导致群名/话题名乱码)
#   - 默认全量重写 (不再优先用旧名字, 改名字的群能拿到新名字)
#   - 自动备份旧 mapping 为 .prev.json 用于 diff
#   - 末尾输出: 新加 / 改名 / 删除 的差量统计
#   - chat_id 写入时统一剥 -100 前缀 (跟 build_index.py 的 URL 构造对齐)
#
# 用法:
#   1. 确认 .env 里有 TG_API_ID / TG_API_HASH / TG_SESSION_STRING
#   2. python scan_groups_v2.py
#   3. 等 5-15 分钟, 输出 群组映射表.json + 群组映射表.json.prev
#
# 增量跑: 加 --incremental 保留旧 topic 名 (谨慎用, 改名字的群拿不到新名字)

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path

# === 强制 UTF-8 输出 (避免 Windows PowerShell GBK 污染) ===
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import Channel, ForumTopic


OUTPUT_PATH = '群组映射表.json'
PREV_PATH = '群组映射表.json.prev'
DIFF_REPORT = '群组映射表_diff.md'


def load_session_and_api():
    """从 .env / tg_session.txt / 环境变量 加载"""
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

    if os.path.exists('tg_session.txt'):
        session_str = Path('tg_session.txt').read_text(encoding='utf-8').strip()
        api_id = int(os.environ.get('TG_API_ID', '0'))
        api_hash = os.environ.get('TG_API_HASH', '')
        if api_id and api_hash:
            return api_id, api_hash, session_str

    api_id = int(os.environ.get('TG_API_ID', '0'))
    api_hash = os.environ.get('TG_API_HASH', '')
    session_str = os.environ.get('TG_SESSION_STRING', '')
    if api_id and api_hash and session_str:
        return api_id, api_hash, session_str

    print('X  找不到 api 凭据和 session, 请先跑 first_login.py')
    sys.exit(1)


def normalize_chat_title(title):
    """群名标准化: 去前后空格"""
    if not title:
        return ''
    return title.strip()


def normalize_id(chat_id):
    """把 -100XXXXXXXXXX 转成 10 位正数 (跟 t.me/c/ URL 对齐)"""
    s = str(chat_id)
    if s.startswith('-100'):
        return s[4:]
    return s.lstrip('-')


def load_prev():
    """读旧 mapping, 用于 diff. 不存在就返空"""
    if not os.path.exists(PREV_PATH):
        return {}
    try:
        with open(PREV_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'[!] 旧映射表 {PREV_PATH} 读失败: {e}')
        return {}


def write_diff_report(prev, new):
    """对比新旧映射, 写出 diff 报告 (markdown)"""
    # 索引: 用 chat_id 配对 (chat_id 稳定, 群名会变)
    prev_by_id = {normalize_id(v.get('chat_id', '')): (k, v) for k, v in prev.items() if v.get('chat_id') is not None}
    new_by_id = {normalize_id(v.get('chat_id', '')): (k, v) for k, v in new.items() if v.get('chat_id') is not None}

    prev_ids = set(prev_by_id.keys())
    new_ids = set(new_by_id.keys())

    added_ids = new_ids - prev_ids
    removed_ids = prev_ids - new_ids
    common_ids = prev_ids & new_ids

    renamed = []  # (chat_id, old_title, new_title)
    for cid in common_ids:
        old_title, _ = prev_by_id[cid]
        new_title, _ = new_by_id[cid]
        if old_title != new_title:
            renamed.append((cid, old_title, new_title))

    # topic 改名字
    topic_renamed = []
    for cid in common_ids:
        _, old_g = prev_by_id[cid]
        _, new_g = new_by_id[cid]
        old_topics = {t['topic_id']: t['name'] for t in old_g.get('topics', [])}
        new_topics = {t['topic_id']: t['name'] for t in new_g.get('topics', [])}
        for tid, oname in old_topics.items():
            if tid in new_topics and new_topics[tid] != oname:
                topic_renamed.append((cid, old_g.get('chat_id'), tid, oname, new_topics[tid]))

    # topic 新增
    topic_added = []
    for cid in common_ids:
        _, old_g = prev_by_id[cid]
        _, new_g = new_by_id[cid]
        old_tids = {t['topic_id'] for t in old_g.get('topics', [])}
        for t in new_g.get('topics', []):
            if t['topic_id'] not in old_tids:
                topic_added.append((cid, old_g.get('chat_id'), t['topic_id'], t['name']))

    # topic 删了
    topic_removed = []
    for cid in common_ids:
        _, old_g = prev_by_id[cid]
        _, new_g = new_by_id[cid]
        new_tids = {t['topic_id'] for t in new_g.get('topics', [])}
        for t in old_g.get('topics', []):
            if t['topic_id'] not in new_tids:
                topic_removed.append((cid, old_g.get('chat_id'), t['topic_id'], t['name']))

    lines = []
    lines.append('# 群组映射表 差量报告\n')
    lines.append(f'- 新群数: **{len(added_ids)}**')
    lines.append(f'- 删除群数: **{len(removed_ids)}**')
    lines.append(f'- 改群名数: **{len(renamed)}**')
    lines.append(f'- 新增 topic 数: **{len(topic_added)}**')
    lines.append(f'- 删 topic 数: **{len(topic_removed)}**')
    lines.append(f'- 改 topic 名数: **{len(topic_renamed)}**')
    lines.append('')

    if added_ids:
        lines.append('## 新加的群')
        for cid in sorted(added_ids):
            title, info = new_by_id[cid]
            tcount = len(info.get('topics', []))
            lines.append(f'- `{title}` (chat_id={info.get("chat_id")}, topics={tcount})')
        lines.append('')

    if removed_ids:
        lines.append('## 消失的群 (你可能退群/被踢)')
        for cid in sorted(removed_ids):
            title, info = prev_by_id[cid]
            tcount = len(info.get('topics', []))
            lines.append(f'- `{title}` (chat_id={info.get("chat_id")}, 旧 topics={tcount})')
        lines.append('')

    if renamed:
        lines.append('## 改了群名')
        for cid, old, new in sorted(renamed, key=lambda x: x[0]):
            lines.append(f'- `{old}` → `{new}`  (chat_id={cid})')
        lines.append('')

    if topic_added:
        lines.append('## 新增 topic')
        lines.append('| chat_id | topic_id | 名称 |')
        lines.append('| --- | --- | --- |')
        for cid, full_id, tid, name in topic_added:
            lines.append(f'| {full_id} | {tid} | {name} |')
        lines.append('')

    if topic_removed:
        lines.append('## 删除 topic')
        lines.append('| chat_id | topic_id | 名称 |')
        lines.append('| --- | --- | --- |')
        for cid, full_id, tid, name in topic_removed:
            lines.append(f'| {full_id} | {tid} | {name} |')
        lines.append('')

    if topic_renamed:
        lines.append('## 改 topic 名')
        lines.append('| chat_id | topic_id | 旧名 → 新名 |')
        lines.append('| --- | --- | --- |')
        for cid, full_id, tid, oname, nname in topic_renamed:
            lines.append(f'| {full_id} | {tid} | {oname} → {nname} |')
        lines.append('')

    if not (added_ids or removed_ids or renamed or topic_added or topic_removed or topic_renamed):
        lines.append('_无变化, 群组结构稳定_')
        lines.append('')

    with open(DIFF_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[OK] 差量报告: {DIFF_REPORT}')


async def scan(incremental=False):
    api_id, api_hash, session_str = load_session_and_api()
    print(f'[OK] 加载凭据: api_id={api_id}, session {len(session_str)} 字符')
    print(f'[*] 模式: {"增量" if incremental else "全量重写"}')
    print()

    new_mapping = {}

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        me = await client.get_me()
        print(f'[OK] 登录: @{me.username or me.first_name} ({me.id})')
        print()

        # 1) 拉所有对话
        print('[*] 拉取所有对话...')
        dialogs = await client.get_dialogs()
        group_dialogs = [d for d in dialogs if d.is_channel or d.is_group]
        print(f'[OK] 找到 {len(group_dialogs)} 个群/频道 (总共 {len(dialogs)} 个对话)')
        print()

        # 2) 对每个群, 拉话题
        for i, dialog in enumerate(group_dialogs, 1):
            entity = dialog.entity
            if not isinstance(entity, Channel):
                continue
            if entity.broadcast:  # 纯广播频道没话题
                continue

            title = normalize_chat_title(entity.title)
            full_chat_id = entity.id
            link_chat_id = normalize_id(full_chat_id)  # 10 位正数
            chat_username = entity.username

            existing = {'chat_id': full_chat_id, 'chat_username': chat_username, 'topics': []}

            # 不是 forum 群
            if not getattr(entity, 'forum', False):
                new_mapping[title] = existing
                print(f'[{i}/{len(group_dialogs)}] {title}: (非 forum) chat_id={full_chat_id} -> t.me/c/{link_chat_id}')
                continue

            # 拉论坛话题
            try:
                topics_result = await client(GetForumTopicsRequest(
                    peer=entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=100,
                ))
                topics = topics_result.topics
            except Exception as e:
                new_mapping[title] = existing
                print(f'[{i}/{len(group_dialogs)}] {title}: (拉话题失败: {type(e).__name__}) chat_id={full_chat_id}')
                continue

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
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f'  [!] 翻页失败: {e}')
                    break

            # 全量模式: 全部用新名字
            new_topics = []
            for t in all_topics:
                if not isinstance(t, ForumTopic):
                    continue
                name = (t.title.strip() if t.title else f'话题{t.id}')
                new_topics.append({'topic_id': t.id, 'name': name})

            existing['topics'] = new_topics
            new_mapping[title] = existing
            print(f'[{i}/{len(group_dialogs)}] {title}: {len(new_topics)} 个话题, chat_id={full_chat_id} -> t.me/c/{link_chat_id}')

            await asyncio.sleep(0.3)

            # 每 10 个群保存一次, 防中断
            if i % 10 == 0:
                with open(OUTPUT_PATH + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(new_mapping, f, ensure_ascii=False, indent=2)
                print(f'  [已保存临时] {OUTPUT_PATH}.tmp')

    # 备份旧版, 写新版
    if os.path.exists(OUTPUT_PATH):
        try:
            # 先把旧版读一份到内存, 写一份到 .prev
            with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
                old = json.load(f)
            with open(PREV_PATH, 'w', encoding='utf-8') as f:
                json.dump(old, f, ensure_ascii=False, indent=2)
            print(f'[*] 旧映射表备份: {PREV_PATH}')
        except Exception as e:
            print(f'[!] 备份旧映射表失败: {e}')

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(new_mapping, f, ensure_ascii=False, indent=2)
    print(f'[OK] 新映射表: {OUTPUT_PATH}')

    # 差量报告
    prev = load_prev()
    if prev:
        write_diff_report(prev, new_mapping)
    else:
        print('[*] 没有旧映射表可比对, 跳过 diff')

    print()
    print('=' * 60)
    print(f'  完成!')
    print(f'  群数: {len(new_mapping)}')
    total_topics = sum(len(g.get("topics", [])) for g in new_mapping.values())
    print(f'  话题总数: {total_topics}')
    print('=' * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--incremental', action='store_true', help='增量模式: 保留旧 topic 名 (谨慎用)')
    args = parser.parse_args()
    asyncio.run(scan(incremental=args.incremental))
