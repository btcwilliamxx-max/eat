# -*- coding: utf-8 -*-
# build_index.py
# 读 阿奇XX_达标公告.txt + 扫描 G:/餐补/screenshots/by_date/
# 生成 可搜索的 index.html
#
# 用法:
#     python build_index.py                         # 处理 G:/餐补 下所有公告
#     python build_index.py "G:/somewhere"          # 指定公告目录
#     python build_index.py --shot-dir "G:/餐补/screenshots"  # 指定截图根目录
import os
import re
import sys
import json
import time
import argparse
import datetime
import webbrowser
import html as html_lib


# ============================================================
# 1. 解析公告 txt
# ============================================================
def parse_announcements(txt_path):
    """
    解析一份公告 txt,返回 list of dict:
    [
      {
        'date_range': '6/8-6/10',
        'group_studio_nick': '橡树（润泽）社区-湖南邵阳-刘细珍',
        'address_full': '0x019Cd547bbf1487A762CE8021bEfCcC32682A2Ad',
        'address_short': '0x019Cd',
        'ark_amount': '19.61',
        'order_no': '4d8098d3-...',
        'currency': 'RMB',
        'people': '20',
        'subsidy_usdt': '200.0',
        'performance': '6293',
        'source_file': '阿奇01_达标公告.txt',
        'announce_index': 1,
      },
      ...
    ]
    """
    with open(txt_path, encoding='utf-8') as f:
        content = f.read()

    source_name = os.path.basename(txt_path)
    parts = content.split('\n\n' + '=' * 18 + '\n\n')
    results = []
    for idx, ann in enumerate(parts, 1):
        if not ann.strip():
            continue
        rec = {
            'date_range': '',
            'group_studio_nick': '',
            'address_full': '',
            'address_short': '',
            'transfer_short': '',
            'ark_amount': '',
            'order_no': '',
            'currency': 'RMB',
            'people': '',
            'subsidy_usdt': '',
            'performance': '',
            'source_file': source_name,
            'announce_index': idx,
            'raw_text': ann,
        }

        # 日期范围
        m = re.search(r'📆\s+([^\n]+?)\s+餐补', ann)
        if m:
            rec['date_range'] = m.group(1).strip()

        # 🏠  社区-专属群-昵称
        m = re.search(r'🏠\s+([^\n]+)', ann)
        if m:
            rec['group_studio_nick'] = m.group(1).strip()

        # 业绩地址(脱敏后格式: 0xXXXXX******XXXXX,5 + 5)
        m = re.search(r'业绩地址[：:]\s*(0x[0-9A-Fa-f]{5})\*+[0-9A-Fa-f]+', ann)
        if m:
            short = m.group(1)
            rec['address_short'] = short
            rec['address_full'] = short + ' (完整地址见源公告)'

        # 拨款地址 (业绩地址 ≠ 拨款地址 时, 公告里会多一行 "拨款地址:0xXXXXX****xxxxx")
        # 用于按拨款地址找截图 (因为截图文件名是 tv_address[1] 收款方 = 拨款地址)
        m = re.search(r'拨款地址[：:]\s*(0x[0-9A-Fa-f]{5})\*+[0-9A-Fa-f]+', ann)
        if m:
            rec['transfer_short'] = m.group(1)

        # 订单编号
        m = re.search(r'订单编号[：:]\s*([\w\-]+)', ann)
        if m:
            rec['order_no'] = m.group(1).strip()

        # 等值 ARK
        m = re.search(r'等值ARK[：:]\s*([\d\.]+)', ann)
        if m:
            rec['ark_amount'] = m.group(1)

        # 用餐金额(币种)
        m = re.search(r'用餐金额[：:]\s*[\d\.]+\s*([A-Z]+)', ann)
        if m:
            rec['currency'] = m.group(1)

        # 用餐人数
        m = re.search(r'用餐人数[：:]\s*(\d+)', ann)
        if m:
            rec['people'] = m.group(1)

        # 补贴金额
        m = re.search(r'补贴金额[：:]\s*([\d\.]+)\s*USDT', ann)
        if m:
            rec['subsidy_usdt'] = m.group(1)

        # 业绩(用"业绩:1234 USDT")
        m = re.search(r'(?:当日|[\d/\-]+\s*)业绩[：:]\s*([\d\.]+)', ann)
        if m:
            rec['performance'] = m.group(1)

        results.append(rec)
    return results


# ============================================================
# 2. 扫描 G:\餐补\screenshots\by_date\<日期>\*.jpg
#    建立 {address_short: [screenshot_path]} 索引
# ============================================================
def build_screenshot_index(shot_root):
    """
    扫描两个目录:
      1. G:/餐补/screenshots/by_date/<日期>/*.jpg   (rename_screenshots.py 归档)
      2. G:/餐补/screenshots/_inbox/<日期>/*.png    (capture_v2.py 直接产出, 跳过 rename)

    截图命名规则:
      旧 (3 段): 175853_0x5f9731d9_892.jpg
      新 (2 段): 182255_0x00ef480.png        ← capture_v2.py 默认命名, 0 token
      没地址:   013059_unknown.png            ← 不进索引 (跳过)

    返回: {
        'by_short_addr': {  # 0x + 8位地址 (兼容: 文件名只给 0x 后 8 字符)
            '0x5f9731d9': ['G:\\...\\175853_0x5f9731d9_892.jpg'],
        },
        'by_amount_ark': {  # "892" 这种
            '892': [...],
        },
        'all_files': [...],
    }
    """
    by_short_addr = {}
    by_amount_ark = {}
    all_files = []

    if not os.path.exists(shot_root):
        return {'by_short_addr': by_short_addr, 'by_amount_ark': by_amount_ark, 'all_files': all_files}

    # 扫描目录列表: (dir_basename, 是否需要 exists)
    scan_dirs = []
    for sub in ('by_date', '_inbox'):
        d = os.path.join(shot_root, sub)
        if os.path.isdir(d):
            scan_dirs.append(d)

    for parent in scan_dirs:
        for date_folder in sorted(os.listdir(parent)):
            date_path = os.path.join(parent, date_folder)
            if not os.path.isdir(date_path):
                continue
            for fn in os.listdir(date_path):
                if not fn.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
                    continue
                full = os.path.join(date_path, fn)
                all_files.append(full)
                # 解析文件名
                stem = os.path.splitext(fn)[0]
                parts = stem.split('_')
                # 至少 2 段: 时间戳_地址
                if len(parts) < 2:
                    continue
                addr_part = parts[1]
                # 跳过 "unknown" / "0x_unknown" 之类
                if not addr_part or 'unknown' in addr_part.lower() or '0x' not in addr_part.lower():
                    continue
                # 标准化: 只存 0x 后的 8 字符 (匹配时跟公告的 address_short [去 0x 后的 5 位] 比对)
                # 文件里写的是 0x00ef480 (0x 后 7 字符) 或 0x5f9731d9 (0x 后 8 字符)
                # 公告 address_short = "0x019Cd" → 去 0x 后 "019cd" (5 字符)
                # find_screenshot 用 addr5 startswith 比对, 索引 key 应是不带 0x 的 8 字符
                addr_after_0x = addr_part.lower().replace('0x', '')
                addr_key = addr_after_0x[:8]  # 不带 0x 前缀, 跟 find_screenshot 兼容
                by_short_addr.setdefault(addr_key, []).append(full)
                # 金额(只在 3 段文件名时取)
                if len(parts) >= 3:
                    amt_part = parts[2]
                    m = re.match(r'(\d+)', amt_part)
                    if m:
                        by_amount_ark.setdefault(m.group(1), []).append(full)

    return {'by_short_addr': by_short_addr, 'by_amount_ark': by_amount_ark, 'all_files': all_files}


def find_screenshot(rec, ss_index):
    """根据一条公告记录找截图(0 匹配/1 匹配/N 匹配)
    优先用 ARK 短地址(业绩地址)找, 找不到降级用拨款地址(transfer_short)
    """
    # 候选地址列表: [ARK地址, 拨款地址] (顺序优先)
    candidates = []
    for key in ('address_short', 'transfer_short'):
        v = rec.get(key, '')
        if v:
            candidates.append(v)

    if not candidates:
        return []

    for short in candidates:
        addr5 = (short[2:] if short.startswith('0x') else short).lower()  # 统一小写
        for k, paths in ss_index['by_short_addr'].items():
            if k.lower().startswith(addr5):
                return paths
    return []


# ============================================================
# 3. 生成 HTML
# ============================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>餐补公告索引 - {title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    margin: 0; padding: 16px;
    background: #f5f5f7; color: #1d1d1f;
  }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }}
  .meta {{ color: #6e6e73; font-size: 13px; margin-bottom: 16px; }}
  .search-bar {{
    position: sticky; top: 0;
    background: rgba(245,245,247,0.95);
    backdrop-filter: blur(8px);
    padding: 12px 0; margin-bottom: 12px;
    border-bottom: 1px solid #d2d2d7;
    z-index: 10;
  }}
  .search-bar input {{
    width: 100%; max-width: 600px; padding: 10px 14px;
    font-size: 15px; border: 1px solid #d2d2d7; border-radius: 8px;
    background: #fff; outline: none;
  }}
  .search-bar input:focus {{ border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0,113,227,0.15); }}
  .stats {{ margin-left: 12px; color: #6e6e73; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
    border-radius: 10px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f3;
    font-size: 13px; vertical-align: top; }}
  th {{ background: #fafafc; font-weight: 600; color: #6e6e73; font-size: 12px;
    text-transform: uppercase; letter-spacing: 0.5px; }}
  tr:hover td {{ background: #f8f9fb; }}
  .addr {{ font-family: "SF Mono", Consolas, monospace; font-size: 12px; color: #6e6e73; }}
  .ark {{ font-weight: 600; color: #1d1d1f; }}
  .shot-link {{
    display: inline-block; padding: 3px 8px; border-radius: 5px;
    font-size: 11px; text-decoration: none; margin-right: 4px; margin-bottom: 2px;
  }}
  .shot-link.have {{ background: #d1f4d8; color: #1d6f3a; }}
  .shot-link.none {{ background: #f0f0f3; color: #999; cursor: default; }}
  .group {{ color: #1d1d1f; font-weight: 500; }}
  .empty {{ padding: 40px; text-align: center; color: #999; }}
  .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px;
    font-size: 11px; background: #e8e8ed; color: #6e6e73; margin-left: 4px; }}
  .copy-btn {{
    background: #0071e3; color: #fff; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 12px; cursor: pointer;
    white-space: nowrap; transition: background-color 0.15s;
    min-width: 78px; box-sizing: border-box; text-align: center;
  }}
  .copy-btn:hover {{ background: #005bb5; }}
  .copy-btn.copied {{ background: #28a745; }}
  .copy-group-btn {{
    background: linear-gradient(135deg, #ff9500 0%, #ff6b00 100%);
    color: #fff; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 12px; cursor: pointer;
    white-space: nowrap; transition: background-color 0.15s;
    box-shadow: 0 1px 3px rgba(255,107,0,0.4);
    position: relative;
    min-width: 88px; box-sizing: border-box; text-align: center;
  }}
  .copy-group-btn::before {{
    content: '🏠';
    margin-right: 3px;
    filter: drop-shadow(0 1px 1px rgba(0,0,0,0.2));
  }}
  .copy-group-btn:hover {{
    background: linear-gradient(135deg, #ffaa33 0%, #ff8000 100%);
    box-shadow: 0 1px 3px rgba(255,107,0,0.4);
  }}
  .copy-img-btn {{
    background: #34c759; color: #fff; border: none; border-radius: 5px;
    padding: 3px 8px; font-size: 11px; cursor: pointer;
    white-space: nowrap; transition: background-color 0.15s;
    margin-left: 4px;
    min-width: 78px; box-sizing: border-box; text-align: center;
  }}
  .copy-img-btn:hover {{ background: #248a3d; }}
  .copy-img-btn.copied {{ background: #1d6f3a; }}
  .copy-group-btn.copied {{
    background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%);
    box-shadow: 0 1px 3px rgba(40,167,69,0.4);
  }}
  /* 跳到群按钮: 紫色, 一键唤起 Telegram 话题 */
  .tg-link-btn {{
    background: linear-gradient(135deg, #29b6f6 0%, #0078d4 100%);
    color: #fff; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 12px; cursor: pointer;
    white-space: nowrap; transition: background-color 0.15s;
    text-decoration: none; display: inline-block;
  }}
  .tg-link-btn:hover {{ background: linear-gradient(135deg, #4ec9f7 0%, #1a8ce0 100%); }}
  .tg-link-btn.none {{
    background: #f0f0f3; color: #999; cursor: default;
  }}
  /* 反馈徽章: 绝对定位, 不撑大按钮 */
  .copy-badge {{
    position: absolute;
    top: -7px; right: -7px;
    width: 18px; height: 18px;
    border-radius: 50%;
    background: #28a745;
    color: #fff;
    font-size: 11px; line-height: 18px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    pointer-events: none;
  }}
  .copy-badge.fail {{ background: #dc3545; }}
  /* 行激活: 不同按钮 3 种颜色, sticky 到下一行被点 */
  tr.row-active-yellow td {{
    background: rgba(255, 200, 0, 0.22) !important;
  }}
  tr.row-active-blue td {{
    background: rgba(0, 113, 227, 0.18) !important;
  }}
  tr.row-active-green td {{
    background: rgba(52, 199, 89, 0.22) !important;
  }}
  tr.row-active-yellow, tr.row-active-blue, tr.row-active-green {{
    box-shadow: inset 0 0 0 2px rgba(0,0,0,0.08);
  }}
</style>
</head>
<body>
<h1>餐补公告索引 <span class="badge">{total} 条</span></h1>
<div class="meta">{meta}</div>

<div class="search-bar">
  <input type="text" id="q" placeholder="搜索 地址前几位 / 金额 / 昵称 / 日期 / 订单号 / 社区" autocomplete="off">
  <span class="stats" id="stats"></span>
</div>

<table>
<thead>
<tr>
  <th>#</th>
  <th>日期</th>
  <th>🏠 社区-专属群-昵称</th>
  <th>地址</th>
  <th>ARK</th>
  <th>USDT</th>
  <th>币种</th>
  <th>截图</th>
  <th>✈️ 跳到群</th>
  <th>操作</th>
</tr>
</thead>
<tbody id="tbody">
  {rows}
</tbody>
</table>

<script>
// ===== 行激活管理: 点哪个按钮, 哪一行变半透明色, sticky 到下一行被点 =====
let activeRow = null;
let activeColor = null;
function activateRow(btn, color) {{
  const tr = btn.closest('tr');
  if (!tr) return;
  if (activeRow === tr) return;  // 同一行, 不重复
  if (activeRow) {{
    activeRow.classList.remove('row-active-yellow', 'row-active-blue', 'row-active-green');
  }}
  tr.classList.add('row-active-' + color);
  activeRow = tr;
  activeColor = color;
}}

// ===== 复制反馈工具: 不用 textContent, 用徽章避免按钮宽度变化 =====
function showBadge(btn, ok) {{
  // 删旧徽章
  const old = btn.querySelector('.copy-badge');
  if (old) old.remove();
  // 加新徽章
  const badge = document.createElement('span');
  badge.className = 'copy-badge' + (ok ? '' : ' fail');
  badge.textContent = ok ? '✓' : '✕';
  btn.appendChild(badge);
  btn.classList.add('copied');
  // 同步激活行背景: 按按钮 class 选颜色
  let color = null;
  if (btn.classList.contains('copy-group-btn')) color = 'yellow';
  else if (btn.classList.contains('copy-img-btn')) color = 'green';
  else if (btn.classList.contains('copy-btn')) color = 'blue';
  activateRow(btn, color);
  setTimeout(() => {{
    badge.remove();
    btn.classList.remove('copied');
  }}, 1500);
}}

const q = document.getElementById('q');
const tbody = document.getElementById('tbody');
const stats = document.getElementById('stats');
const rows = Array.from(tbody.querySelectorAll('tr'));

function normalize(s) {{ return (s || '').toString().toLowerCase(); }}

function apply() {{
  const needle = normalize(q.value.trim());
  let shown = 0;
  for (const r of rows) {{
    if (!needle) {{ r.style.display = ''; shown++; continue; }}
    const hay = normalize(r.dataset.search);
    r.style.display = hay.includes(needle) ? '' : 'none';
    if (r.style.display !== 'none') shown++;
  }}
  stats.textContent = needle ? `显示 ${{shown}} / ${{rows.length}}` : `共 ${{rows.length}} 条`;
}}
q.addEventListener('input', apply);
apply();

// ===== 复制公告全文 =====
document.querySelectorAll('.copy-btn').forEach(btn => {{
  btn.addEventListener('click', async (e) => {{
    const tr = e.currentTarget.closest('tr');
    if (!tr) return;
    const text = tr.dataset.raw || '';  // dataset 自动反转义 HTML
    const ok = () => showBadge(btn, true);
    try {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        ok();
        return;
      }}
    }} catch (err) {{
      // 继续走降级
    }}
    // 降级:临时 textarea + execCommand
    try {{
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      const success = document.execCommand('copy');
      document.body.removeChild(ta);
      if (success) ok();
      else showBadge(btn, false);
    }} catch (err) {{
      showBadge(btn, false);
    }}
  }});
}});

// ===== 复制三要素 (社区-专属群-昵称) =====
document.querySelectorAll('.copy-group-btn').forEach(btn => {{
  btn.addEventListener('click', async (e) => {{
    const tr = e.currentTarget.closest('tr');
    if (!tr) return;
    const text = tr.dataset.group || '';
    if (!text) {{
      showBadge(btn, false);
      return;
    }}
    const ok = () => showBadge(btn, true);
    try {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        ok();
        return;
      }}
    }} catch (err) {{
      // 继续降级
    }}
    try {{
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      const success = document.execCommand('copy');
      document.body.removeChild(ta);
      if (success) ok();
      else showBadge(btn, false);
    }} catch (err) {{
      showBadge(btn, false);
    }}
  }});
}});

// ===== 复制图片到剪贴板 =====
document.querySelectorAll('.copy-img-btn').forEach(btn => {{
  btn.addEventListener('click', async (e) => {{
    const url = btn.dataset.shot;
    if (!url) {{
      showBadge(btn, false);
      return;
    }}
    const ok = () => showBadge(btn, true);
    const fail = (msg) => showBadge(btn, false);
    try {{
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const blob = await resp.blob();
      // navigator.clipboard.write 需要 ClipboardItem (Chrome 76+)
      if (!window.ClipboardItem) throw new Error('浏览器不支持');
      await navigator.clipboard.write([
        new ClipboardItem({{ 'image/png': blob }})
      ]);
      ok();
    }} catch (err) {{
      console.error('copy img failed:', err);
      fail(err.message || '需 http 模式');
    }}
  }});
}});
</script>

</body>
</html>
"""


def build_html(all_records, ss_index, out_path):
    rows = []
    for i, rec in enumerate(all_records, 1):
        shots = find_screenshot(rec, ss_index)
        if shots:
            link_parts = []
            for p in shots:
                rel = os.path.relpath(p, os.path.dirname(out_path)) if out_path else p
                rel = rel.replace(chr(92), '/')
                fname = os.path.basename(p)
                # data-shot 存 http 路径 (server 起来后才能用), 用前导 / 让 fetch 走同源
                link_parts.append(
                    f'<a class="shot-link have" href="/{rel}" target="_blank">📎 {fname}</a>'
                    f'<button class="copy-img-btn" type="button" data-shot="/{rel}" title="复制图片到剪贴板">📋复制图</button>'
                )
            links = ''.join(link_parts)
        else:
            links = '<span class="shot-link none">未找到</span>'

        search_blob = ' '.join([
            rec.get('date_range', ''),
            rec.get('group_studio_nick', ''),
            rec.get('address_short', ''),
            rec.get('ark_amount', ''),
            rec.get('order_no', ''),
            rec.get('subsidy_usdt', ''),
            rec.get('currency', ''),
            rec.get('source_file', ''),
        ])

        # data-raw 存完整公告原文(HTML escape 一下,JS 读时 dataset 会自动反转义回原字符串)
        raw_escaped = html_lib.escape(rec.get('raw_text', ''), quote=True)
        tg_url = rec.get('telegram_url', '')
        if tg_url:
            tg_cell = f'<a class="tg-link-btn" href="{tg_url}" target="_blank" title="唤起 Telegram 话题">✈️ 跳到群</a>'
        else:
            tg_cell = '<span class="tg-link-btn none">未匹配</span>'
        rows.append(f'''<tr data-search="{html_lib.escape(search_blob)}" data-raw="{raw_escaped}" data-group="{html_lib.escape(rec.get('group_studio_nick', ''), quote=True)}">
  <td>{i}</td>
  <td>{html_lib.escape(rec.get('date_range', ''))}</td>
  <td class="group">{html_lib.escape(rec.get('group_studio_nick', ''))}</td>
  <td class="addr">{html_lib.escape(rec.get('address_short', ''))}</td>
  <td class="ark">{html_lib.escape(rec.get('ark_amount', ''))}</td>
  <td>{html_lib.escape(rec.get('subsidy_usdt', ''))}</td>
  <td>{html_lib.escape(rec.get('currency', ''))}</td>
  <td>{links}</td>
  <td>{tg_cell}</td>
  <td>
    <div style="display:flex; gap:4px;">
      <button class="copy-btn" type="button">📋 复制</button>
      <button class="copy-group-btn" type="button" title="复制社区-专属群-昵称">三要素</button>
    </div>
  </td>
</tr>''')

    meta = (
        f'截图根目录: {ss_index.get("__root__", "")} · '
        f'已索引截图: {len(ss_index.get("all_files", []))} 张'
    )
    html = HTML_TEMPLATE.format(
        title='+'.join(sorted({r['source_file'].replace("_达标公告.txt", "").replace("_未达标公告.txt", "") for r in all_records})),
        total=len(all_records),
        meta=meta,
        rows='\n'.join(rows) if rows else '<tr><td colspan="9" class="empty">没找到公告</td></tr>',
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ============================================================
# 3.5 群组映射: 从群组映射表.json 找群 + 话题, 生成 t.me/c/.../... 链接
# ============================================================
def load_group_mapping(mapping_path):
    """加载 群组映射表.json, 返回 {群名前缀: (chat_id, {topic名: topic_id})}"""
    if not os.path.exists(mapping_path):
        print(f'[!] 群组映射表不存在: {mapping_path}, 跳到群功能禁用')
        return {}
    try:
        with open(mapping_path, encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        print(f'[!] 群组映射表加载失败: {e}')
        return {}
    # 索引: 群名前缀(到第一个 '-' 前) -> {chat_id, {topic_name: topic_id}}
    index = {}
    for chat_title, info in raw.items():
        topics = info.get('topics', []) or []
        topic_map = {}
        for t in topics:
            name = t.get('name', '').strip()
            tid = t.get('topic_id')
            if name and tid is not None:
                topic_map[name] = tid
        chat_id = info.get('chat_id')
        if chat_id is None:
            continue
        # 用群名前缀(到 '-') 做 key: 公告 "泰山（幸运）-天泽新社区-孙铭泽"
        # → 群前缀 "泰山（幸运）", 找 key startswith 前缀
        prefix = chat_title.split('-')[0].strip()
        if prefix:
            index[prefix] = {'chat_id': chat_id, 'topic_map': topic_map, 'chat_title': chat_title}
    print(f'[OK] 群组映射: {len(index)} 个群前缀')
    return index


def find_telegram_url(group_studio_nick, mapping):
    """从 '泰山（幸运）-天泽新社区-孙铭泽' 找 (chat_id, topic_id) -> t.me/c/.../... URL
    返回 None 表示没匹配上
    匹配策略: 群前缀(去除 emoji/特殊字符) + topic 名都做模糊匹配
    """
    if not group_studio_nick or not mapping:
        return None
    parts = group_studio_nick.split('-')
    if len(parts) < 2:
        return None
    group_prefix = parts[0].strip()
    topic_name = parts[1].strip()

    # 标准化群前缀: 去 emoji, 去 "社区", 去 "专属服务群", 去 "(...)" 内容
    def norm(s):
        s = re.sub(r'[\U0001F300-\U0001FAFF🏠]', '', s)  # 去除 emoji
        s = s.replace('专属服务群', '').replace('社区', '').strip()
        return s
    np = norm(group_prefix)
    nt = norm(topic_name)

    # 1) 精确: 群前缀完全等于某个 mapping key 的 normalize
    info = None
    matched_key = None
    for k, v in mapping.items():
        if norm(k) == np:
            info = v
            matched_key = k
            break
    # 2) 模糊: contains (优先 longest)
    if not info:
        candidates = [(k, v) for k, v in mapping.items() if np in norm(k) or norm(k) in np]
        if candidates:
            # 取 norm 长度最长的(最具体)
            candidates.sort(key=lambda x: -len(norm(x[0])))
            matched_key, info = candidates[0]
    if not info:
        return None

    chat_id = info['chat_id']
    # topic: 先精确, 再模糊 contains
    topic_map = info['topic_map']
    topic_id = None
    if topic_name in topic_map:
        topic_id = topic_map[topic_name]
    else:
        # 模糊
        for tn, tid in topic_map.items():
            if nt in norm(tn) or norm(tn) in nt:
                topic_id = tid
                break
    if topic_id is None:
        return None

    if str(chat_id).startswith('-100'):
        link_chat_id = str(chat_id)[4:]
    else:
        link_chat_id = str(chat_id)
    if link_chat_id.lstrip('-').isdigit():
        url = f'https://t.me/c/{link_chat_id}/{topic_id}'
    else:
        url = f'https://t.me/{link_chat_id}/{topic_id}'
    return url


# ============================================================
# 4. 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('announce_dir', nargs='?', default=r'G:\餐补',
                    help='公告 txt 所在目录')
    ap.add_argument('--shot-dir', default=r'G:\餐补\screenshots',
                    help='截图根目录(含 by_date/)')
    ap.add_argument('--out', default=None,
                    help='HTML 输出路径(默认 公告目录/index.html)')
    args = ap.parse_args()

    print('=' * 60)
    print('   餐补公告索引生成器')
    print('=' * 60)
    print(f'公告目录: {args.announce_dir}')
    print(f'截图目录: {args.shot_dir}')
    print()

    if not os.path.isdir(args.announce_dir):
        print(f'X 公告目录不存在: {args.announce_dir}')
        return

    # 1) 收公告 - 兼容两种命名:
    #    旧的: 阿奇XX_达标公告.txt
    #    新的: 达标公告.txt (gen_announce.py 直接生成)
    txts = []
    for f in os.listdir(args.announce_dir):
        if f == '达标公告.txt':
            txts.append(f)
        elif f.endswith('_达标公告.txt') and (f.startswith('阿奇') or f.startswith('阿')):
            txts.append(f)
    txts.sort()
    print(f'找到 {len(txts)} 份公告:')
    for t in txts:
        print(f'  - {t}')
    print()

    all_records = []
    for t in txts:
        all_records.extend(parse_announcements(os.path.join(args.announce_dir, t)))
    print(f'解析出 {len(all_records)} 条公告')
    print()

    # 2) 索引截图
    ss_index = build_screenshot_index(args.shot_dir)
    ss_index['__root__'] = args.shot_dir
    print(f'扫描截图: {len(ss_index["all_files"])} 张')
    for f in ss_index['all_files'][:5]:
        print(f'  - {f}')
    if len(ss_index['all_files']) > 5:
        print(f'  ... +{len(ss_index["all_files"]) - 5} 张')
    print()

    # 2.5) 加载群组映射
    mapping_path = os.path.join(args.announce_dir, '群组映射表.json')
    mapping = load_group_mapping(mapping_path)
    if mapping:
        # 给每条 record 算 telegram_url
        url_matched = 0
        for r in all_records:
            url = find_telegram_url(r.get('group_studio_nick', ''), mapping)
            r['telegram_url'] = url
            if url:
                url_matched += 1
        print(f'已匹配 Telegram 链接: {url_matched} / {len(all_records)} 条')
        print()

    # 3) 统计匹配情况
    matched = sum(1 for r in all_records if find_screenshot(r, ss_index))
    print(f'已匹配截图: {matched} / {len(all_records)} 条')
    print()

    # 4) 输出 HTML
    out = args.out or os.path.join(args.announce_dir, 'index.html')
    build_html(all_records, ss_index, out)
    print(f'HTML 已生成: {out}')

    # 5) 浏览器打开 (用本地 http server, 解决 file:// 下复制图片被禁用的问题)
    try:
        import subprocess
        import socket as _sock
        from urllib.request import urlopen

        port = 8765
        # 检查端口是否占用
        def _port_in_use(p):
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                try:
                    s.bind(('127.0.0.1', p)); return False
                except OSError:
                    return True

        # 起 server (后台)
        server_script = os.path.join(os.path.dirname(os.path.abspath(out)), 'serve.py')
        if os.path.exists(server_script):
            if _port_in_use(port):
                print(f'[*] 端口 {port} 已被占用, 假设 server 已启动')
            else:
                # 用 Popen 起后台, 不阻塞当前进程
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                subprocess.Popen(
                    ['python', '-X', 'utf8', server_script, str(port)],
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                )
                # 等 server 起来
                for _ in range(30):
                    if not _port_in_use(port):
                        break
                    time.sleep(0.2)
                print(f'[OK] server 已起: http://localhost:{port}/index.html')
            url = f'http://localhost:{port}/index.html'
            # 强制新标签, 不复用 file:// 旧 tab
            webbrowser.open_new(url)
        else:
            # 没 serve.py 兜底用 file://
            if os.name == 'nt':
                os.startfile(out)
    except Exception as e:
        # 失败兜底
        try:
            if os.name == 'nt':
                os.startfile(out)
        except Exception:
            pass


if __name__ == '__main__':
    main()
