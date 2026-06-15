# -*- coding: utf-8 -*-
# rename_screenshots.py
# 扫描 G:/餐补/screenshots/_inbox/ 下的截图,用 AI 视觉读出 (地址, 金额, 时间),
# 重命名为 <HHMMSS>_<地址前8位>_<金额>.jpg 移到 G:/餐补/screenshots/by_date/<日期>/
#
# 用法:
#     python rename_screenshots.py                            # 默认路径
#     python rename_screenshots.py --shot-dir "G:/餐补/screenshots"
#     python rename_screenshots.py --batch-size 5              # 一批 5 张(图片越大越慢,默认 3)
import os
import re
import sys
import json
import shutil
import argparse
import subprocess
import datetime


# ============================================================
# 1. AI 视觉读一张截图
# ============================================================
EXTRACT_PROMPT = """你是 OCR 提取机器。只读截图内容,然后输出严格的 JSON。

这是一个 TP 钱包的交易详情截图。从截图中提取以下字段(如果有的话):

- from_addr_short: 发款方地址的前 10 个字符(含 0x)。截图中显示为 0x...开头的 42 字符 hex,取前 10 个(含 0x)。
- to_addr_short:   收款方地址的前 10 个字符(含 0x)。
- amount_number:   转账金额数字部分(去掉负号和币种),例如 8.92。
- amount_currency: 币种,例如 ARK / USDT / BNB。
- tx_time:         交易时间,严格按截图里的原文(形如 2026-06-12 17:58:53)。

如果某项找不到,该字段填 null。

输出格式严格要求(这是你的全部输出,不要任何其他文字):
{"from_addr_short":"...","to_addr_short":"...","amount_number":"...","amount_currency":"...","tx_time":"..."}

不要输出 Markdown 代码块 ```。不要输出解释。直接以 { 开始, 以 } 结束。"""


def _call_mcp(payload):
    """通过临时文件调 mavis.cmd,避免 PowerShell 引号问题"""
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp_path = f.name
    try:
        return subprocess.run(
            ['mavis.cmd', 'mcp', 'call', 'matrix', 'matrix_describe_images', '--file', tmp_path],
            capture_output=True, text=True, encoding='utf-8',
            shell=True
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _parse_response(out, n_expected):
    """从 MCP 返回 stdout 里抠 n_expected 个 JSON 字典"""
    try:
        resp = json.loads(out)
    except Exception:
        return [None] * n_expected
    candidates = []
    if isinstance(resp, dict):
        if 'results' in resp and isinstance(resp['results'], list):
            candidates = resp['results']
        elif 'content' in resp and isinstance(resp['content'], list):
            candidates = resp['content']
        else:
            candidates = [resp]
    elif isinstance(resp, list):
        candidates = resp
    out_list = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        text = c.get('text') or c.get('description') or c.get('content') or ''
        if isinstance(text, list) and text:
            text = text[0].get('text', '') if isinstance(text[0], dict) else str(text[0])
        if not text:
            continue
        # 非贪婪匹配,避免抓到多个 JSON
        m = re.search(r'\{[\s\S]*?\}', text)
        if m:
            try:
                out_list.append(json.loads(m.group(0)))
                continue
            except Exception:
                pass
        out_list.append(None)
    while len(out_list) < n_expected:
        out_list.append(None)
    return out_list[:n_expected]


def describe_batch(paths):
    """批量读(<=10 张/批),返回 [dict, ...]"""
    payload = {
        "image_info": [
            {"file": p.replace('\\', '/'), "prompt": EXTRACT_PROMPT}
            for p in paths
        ]
    }
    result = _call_mcp(payload)
    if result.returncode != 0:
        print(f'  X MCP call failed: {result.stderr[:200]}')
        return [None] * len(paths)
    return _parse_response(result.stdout, len(paths))


def describe_one(path):
    """单张(留作兼容,基本不用)"""
    return describe_batch([path])[0] if describe_batch([path]) else None


# ============================================================
# 2. 构造新文件名
# ============================================================
def build_new_name(info, original_path):
    """根据 AI 返回构造新文件名: <HHMMSS>_<addr8>_<amt>.jpg
    关键:用 收款方地址 前 8 位(不是发款方),这样能和公告里的"业绩地址"对上。
    """
    tx_time = (info or {}).get('tx_time') or ''
    # 优先用 收款方(和公告的"业绩地址"对应),没有才退到发款方
    to_addr = (info or {}).get('to_addr_short') or ''
    from_addr = (info or {}).get('from_addr_short') or ''
    amount = (info or {}).get('amount_number') or ''

    # 时间戳
    hh = mm = ss = None
    m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', tx_time)
    if m:
        hh, mm, ss = m.group(1).zfill(2), m.group(2), m.group(3)
    if not hh:
        mtime = os.path.getmtime(original_path)
        dt = datetime.datetime.fromtimestamp(mtime)
        hh, mm, ss = dt.strftime('%H'), dt.strftime('%M'), dt.strftime('%S')

    # 日期
    date_m = re.search(r'(\d{4})-(\d{2})-(\d{2})', tx_time)
    if date_m:
        date_str = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"
    else:
        date_str = datetime.date.today().isoformat()

    # 收款方地址前 8 位
    addr8 = ''
    if to_addr and to_addr.startswith('0x'):
        addr8 = to_addr[2:10].lower()
    elif from_addr and from_addr.startswith('0x'):
        # 退到发款方
        addr8 = from_addr[2:10].lower()

    # 金额:保留 2 位
    amt_clean = ''
    if amount:
        try:
            amt_clean = f"{float(amount):.2f}".replace('.', '')
        except Exception:
            amt_clean = re.sub(r'[^\d]', '', amount) or '0'

    stem_parts = [hh + mm + ss]
    if addr8:
        stem_parts.append(addr8)
    if amt_clean and amt_clean != '0':
        stem_parts.append(amt_clean)
    stem = '_'.join(stem_parts)
    return f"{stem}.jpg", date_str


# ============================================================
# 3. 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shot-dir', default=r'G:\餐补\screenshots')
    ap.add_argument('--batch-size', type=int, default=3,
                    help='AI 视觉每批处理的截图数(<=10)')
    ap.add_argument('--dry-run', action='store_true',
                    help='只打印,不动文件')
    args = ap.parse_args()

    inbox = os.path.join(args.shot_dir, '_inbox')
    by_date = os.path.join(args.shot_dir, 'by_date')
    print('=' * 60)
    print('   截图自动改名器 (TP 钱包 OCR)')
    print('=' * 60)
    print(f'收件箱: {inbox}')
    print(f'归档根: {by_date}')
    print()

    if not os.path.isdir(inbox):
        print(f'X 收件箱不存在: {inbox}')
        return

    files = sorted([
        os.path.join(inbox, f)
        for f in os.listdir(inbox)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp'))
    ])
    if not files:
        print('收件箱空,无需处理。')
        return
    print(f'发现 {len(files)} 张截图待处理\n')

    if args.dry_run:
        print('(DRY-RUN 模式,不实际改文件)')

    success = skipped = failed = 0
    bs = max(1, min(args.batch_size, 10))
    for i in range(0, len(files), bs):
        batch = files[i:i+bs]
        print(f'[{i+1}-{i+len(batch)}/{len(files)}] 处理中...')
        infos = describe_batch(batch)
        for path, info in zip(batch, infos):
            orig_name = os.path.basename(path)
            if not info:
                print(f'  X {orig_name}  AI 识别失败,留在 _inbox/ 手动处理')
                failed += 1
                continue
            new_name, date_str = build_new_name(info, path)
            target_dir = os.path.join(by_date, date_str)
            target_path = os.path.join(target_dir, new_name)
            print(f'  - {orig_name}')
            print(f'      AI 识别: from={info.get("from_addr_short")} amount={info.get("amount_number")} {info.get("amount_currency")} time={info.get("tx_time")}')
            print(f'      改名 -> {new_name}')
            print(f'      归档 -> {target_dir}')
            if not args.dry_run:
                os.makedirs(target_dir, exist_ok=True)
                # 防重名
                if os.path.exists(target_path):
                    base, ext = os.path.splitext(new_name)
                    j = 2
                    while os.path.exists(os.path.join(target_dir, f"{base}_{j}{ext}")):
                        j += 1
                    target_path = os.path.join(target_dir, f"{base}_{j}{ext}")
                shutil.move(path, target_path)
            success += 1

    print()
    print('=' * 60)
    print(f'处理完成: 成功 {success} / 失败 {failed}')
    if not args.dry_run and success:
        print(f'下一步: python build_index.py  (刷新 HTML 索引)')


if __name__ == '__main__':
    main()
