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
import argparse
import datetime
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
    """根据一条公告记录找截图(0 匹配/1 匹配/N 匹配)"""
    # 公告里 address_short 是 0x + 5位(脱敏后),文件名是 8 位收款方
    short = rec.get('address_short', '')  # 例如 0x019Cd
    if not short:
        return []
    addr5 = (short[2:] if short.startswith('0x') else short).lower()  # 统一小写
    # 8 位地址前 5 位应该等于 addr5
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
    white-space: nowrap; transition: background 0.15s;
  }}
  .copy-btn:hover {{ background: #005bb5; }}
  .copy-btn.copied {{ background: #28a745; }}
  .copy-group-btn {{
    background: linear-gradient(135deg, #ff9500 0%, #ff6b00 100%);
    color: #fff; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 12px; cursor: pointer;
    white-space: nowrap; transition: all 0.15s;
    box-shadow: 0 1px 3px rgba(255,107,0,0.4);
    position: relative;
  }}
  .copy-group-btn::before {{
    content: '🏠';
    margin-right: 3px;
    filter: drop-shadow(0 1px 1px rgba(0,0,0,0.2));
  }}
  .copy-group-btn:hover {{
    background: linear-gradient(135deg, #ffaa33 0%, #ff8000 100%);
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(255,107,0,0.5);
  }}
  .copy-group-btn.copied {{
    background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%);
    box-shadow: 0 1px 3px rgba(40,167,69,0.4);
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
  <th>操作</th>
</tr>
</thead>
<tbody id="tbody">
  {rows}
</tbody>
</table>

<script>
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
    const orig = btn.textContent;
    const ok = () => {{
      btn.textContent = '✅ 已复制';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = orig;
        btn.classList.remove('copied');
      }}, 1500);
    }};
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
      else btn.textContent = '❌ 复制失败';
    }} catch (err) {{
      btn.textContent = '❌ 复制失败';
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
      btn.textContent = '❌ 无内容';
      return;
    }}
    const orig = btn.textContent;
    const ok = () => {{
      btn.textContent = '✅ 已复制';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = orig;
        btn.classList.remove('copied');
      }}, 1500);
    }};
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
      else btn.textContent = '❌ 复制失败';
    }} catch (err) {{
      btn.textContent = '❌ 复制失败';
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
            links = ''.join(
                f'<a class="shot-link have" href="file:///{p.replace(chr(92), "/")}" target="_blank">📎 {os.path.basename(p)}</a>'
                for p in shots
            )
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
        rows.append(f'''<tr data-search="{html_lib.escape(search_blob)}" data-raw="{raw_escaped}" data-group="{html_lib.escape(rec.get('group_studio_nick', ''), quote=True)}">
  <td>{i}</td>
  <td>{html_lib.escape(rec.get('date_range', ''))}</td>
  <td class="group">{html_lib.escape(rec.get('group_studio_nick', ''))}</td>
  <td class="addr">{html_lib.escape(rec.get('address_short', ''))}</td>
  <td class="ark">{html_lib.escape(rec.get('ark_amount', ''))}</td>
  <td>{html_lib.escape(rec.get('subsidy_usdt', ''))}</td>
  <td>{html_lib.escape(rec.get('currency', ''))}</td>
  <td>{links}</td>
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
# 4. 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('announce_dir', nargs='?', default=r'C:\Users\92071\Desktop\餐补',
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

    # 3) 统计匹配情况
    matched = sum(1 for r in all_records if find_screenshot(r, ss_index))
    print(f'已匹配截图: {matched} / {len(all_records)} 条')
    print()

    # 4) 输出 HTML
    out = args.out or os.path.join(args.announce_dir, 'index.html')
    build_html(all_records, ss_index, out)
    print(f'HTML 已生成: {out}')

    # 5) 浏览器打开(本地)
    try:
        if os.name == 'nt':
            os.startfile(out)
    except Exception:
        pass


if __name__ == '__main__':
    main()
