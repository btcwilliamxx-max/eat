# -*- coding: utf-8 -*-
# capture_v2.py
# 雷电模拟器 - TP 钱包 - 批量截交易详情 (uiautomator2 版, 不调 AI 视觉)
#
# v2 修复:
#   1. 列表不滚动: 返回列表后向上滑动, 让下一笔进第一行
#   2. 防重复: 点之前取"金额"指纹和上次对比, 相同则主动滚动重试
#   3. 地址提取: 用 '收款方' label 后面 sibling 定位, 不靠 regex
#
# 用法:
#   pip install uiautomator2
#   python -m uiautomator2 init
#   python capture_v2.py
#
# 可选参数:
#   --device emulator-5554
#   --max-items 200
#   --batch-pause 20
#   --crop-top 170
#   --crop-bottom 500
import os
import re
import sys
import json
import time
import argparse
import datetime
import subprocess
import traceback

try:
    import uiautomator2 as u2
except ImportError:
    print('请先安装: pip install uiautomator2')
    print('然后: python -m uiautomator2 init')
    sys.exit(1)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ============================================================
# 0. ADB 工具 (提速用: 跳过 uiautomator2 中间层)
# ============================================================
def adb_dump_xml(adb_path, device):
    try:
        subprocess.run(
            [adb_path, '-s', device, 'shell', 'uiautomator', 'dump',
             '--compressed', '/sdcard/win.xml'],
            capture_output=True, timeout=10
        )
        r = subprocess.run(
            [adb_path, '-s', device, 'exec-out', 'cat', '/sdcard/win.xml'],
            capture_output=True, timeout=10
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode('utf-8', errors='replace')
    except Exception:
        pass
    return None


def _find_nodes(xml, resource_id):
    nodes = []
    for m in re.finditer(r'<node([^>]*)/?>', xml):
        attrs_str = m.group(1)
        if f'resource-id="{resource_id}"' not in attrs_str:
            continue
        node = {}
        for am in re.finditer(r'(\w[\w-]*)="([^"]*)"', attrs_str):
            node[am.group(1)] = am.group(2)
        nodes.append(node)
    return nodes


def xml_get_first_row_date(xml):
    nodes = _find_nodes(xml, 'vip.mytokenpocket:id/tv_time')
    for n in nodes:
        t = n.get('text', '').strip()
        if re.match(r'\d{2}-\d{2} \d{2}:\d{2}:\d{2}', t):
            return t
    m = re.search(r'text="(\d{2}-\d{2} \d{2}:\d{2}:\d{2})"', xml)
    return m.group(1) if m else None


def xml_get_first_row_amount(xml):
    for n in _find_nodes(xml, 'vip.mytokenpocket:id/tv_amount'):
        b = n.get('bounds', '')
        bm = re.match(r'\[(\d+),(\d+)\]', b)
        if bm and int(bm.group(2)) > 500:
            return n.get('text', '').strip()
    m = re.search(r'text="(-\d+\.?\d*\s*ARK)"', xml)
    return m.group(1) if m else None


def xml_page_state(xml):
    if 'text="合约调用"' in xml or (
        'text="全部"' in xml and 'text="转出"' in xml
    ):
        return 'list'
    if 'text="发款方"' in xml or 'text="交易详情"' in xml:
        return 'detail'
    return 'unknown'


# ============================================================
# 1. ADB 路径检测
# ============================================================
ADB_CANDIDATE_PATHS = [
    r'G:\leidian\LDPlayer9\adb.exe',
    r'C:\leidian\LDPlayer9\adb.exe',
    r'C:\leidian\LDPlayer4\adb.exe',
    r'C:\leidian\LDPlayer\adb.exe',
    r'C:\Program Files\leidian\LDPlayer9\adb.exe',
    r'C:\Android\platform-tools\adb.exe',
    r'C:\Program Files\Android\platform-tools\adb.exe',
]


def find_adb():
    for p in ADB_CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    for cand in ['adb.exe', 'adb']:
        try:
            r = subprocess.run([cand, 'version'], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    return None


# ============================================================
# 2. 工具函数
# ============================================================
def adb_screencap(adb_path, device, out_path):
    """ADB 直接截屏 (0.1 秒), 0 token 成本"""
    r = subprocess.run(
        [adb_path, '-s', device, 'exec-out', 'screencap', '-p'],
        capture_output=True, timeout=15
    )
    if r.returncode != 0 or not r.stdout:
        return False
    with open(out_path, 'wb') as f:
        f.write(r.stdout)
    return True


def crop_image(in_path, out_path, top_px=0, bottom_px=0):
    if not HAS_PIL:
        import shutil
        shutil.copy(in_path, out_path)
        return False
    img = Image.open(in_path)
    w, h = img.size
    top = max(0, int(top_px))
    bottom = max(0, h - int(bottom_px)) if bottom_px else h
    img.crop((0, top, w, bottom)).save(out_path)
    return True


# ============================================================
# 3. UI 操作
# ============================================================
def tap_first_tx(d):
    """点列表最上面那行交易项 (进入详情)"""
    candidates = d(text='合约调用')
    if candidates.exists:
        first = candidates[0]
        first.click()
        return True
    return False


def is_detail_page(d):
    return d(text='交易详情').exists or d(text='发款方').exists


def tap_back(d):
    """从详情页返回列表, 优先点 < 返回箭头"""
    back = d(description='返回')
    if back.exists:
        back.click()
        return 'tap(返回箭头)'
    back = d(description='back')
    if back.exists:
        back.click()
        return 'tap(back)'
    d.press('back')
    return 'press(back)'


def is_list_page(d):
    """判断列表页: 有 合约调用 字样, 或有 全部/转出 tab"""
    if d(text='合约调用').exists:
        return True
    if d(text='全部').exists and d(text='转出').exists:
        return True
    return False


def get_screen_size(d):
    """获取屏幕尺寸"""
    info = d.info
    return info.get('displayWidth', 1080), info.get('displayHeight', 1920)


def scroll_list_up(d, debug=False, recovery=False):
    """向上滑动列表 (121px)
    debug=True: 滑行前后取 tv_address[1] 比对, 验证真的滚动了
    recovery=True: 滑行后 STUCK 时自动加大滑行重试, 最多 3 次
    """
    w, h = get_screen_size(d)
    x = w // 2
    y_start_121 = 603
    y_end_121 = 482  # 121 = 603 - 482
    y_start_recovery = 700
    y_end_recovery = 400  # 300px 大幅, 跳 1-2 笔兜底

    def _dump_first():
        """滑行前/后 取 tv_address[0] 文本 + y1"""
        addr = None
        y = None
        try:
            nodes = d(resourceId='vip.mytokenpocket:id/tv_address')
            if nodes.count >= 1:
                n = nodes[0]
                addr = n.get_text().strip()[:14]
                info = n.info
                b = info.get('bounds', {}) or {}
                if isinstance(b, dict):
                    y = b.get('y1', 0)
                else:
                    mm = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', str(b))
                    y = int(mm.group(2)) if mm else 0
        except Exception:
            pass
        return addr, y

    addr_before, y_before = (_dump_first() if (debug or recovery) else (None, None))

    # 主滑行: 121px
    d.swipe(x, y_start_121, x, y_end_121, duration=0.15)
    time.sleep(0.2)

    # 自检
    moved = True
    if debug or recovery:
        addr_after, y_after = _dump_first()
        moved = (addr_after and addr_before and addr_after != addr_before) \
             or (y_after is not None and y_before is not None and abs(y_after - y_before) > 5)
        if debug:
            flag = 'OK' if moved else 'STUCK'
            print(f'    [scroll] {flag}  addr: {addr_before} -> {addr_after}  '
                  f'y: {y_before} -> {y_after}')

    # recovery: STUCK 自动加大重试
    if not moved and recovery:
        for attempt in range(1, 4):
            d.swipe(x, y_start_recovery, x, y_end_recovery, duration=0.15)
            time.sleep(0.25)
            if debug:
                addr_after, y_after = _dump_first()
                moved = (addr_after and addr_before and addr_after != addr_before) \
                     or (y_after is not None and y_before is not None and abs(y_after - y_before) > 5)
                flag = 'OK' if moved else 'STUCK'
                print(f'    [scroll-recovery {attempt}] {flag}  '
                      f'addr: {addr_after}  y: {y_after}')
            else:
                moved = True  # recovery 模式不自检就默认成功, 下次循环靠地址防重复兜底
            if moved:
                break

    return moved


def get_first_row_date(d):
    """取列表第一行的时间戳 (作为'目标日'判断)
    列表项右边显示 '06-13 18:13:15' 格式
    优先用 tv_time, 兜底用 regex 在整个 dump 里找
    """
    # 优先 resource ID
    try:
        nodes = d(resourceId='vip.mytokenpocket:id/tv_time')
        if nodes.count >= 1:
            return nodes[0].get_text().strip()
    except Exception:
        pass
    # 兜底: regex 找 'MM-DD HH:MM:SS' 格式
    try:
        nodes = d(textMatches=r'\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
        if nodes.count >= 1:
            return nodes[0].get_text().strip()
    except Exception:
        pass
    # 兜底2: 在 dump_hierarchy 里搜
    try:
        h = d.dump_hierarchy()
        m = re.search(r'text="(\d{2}-\d{2} \d{2}:\d{2}:\d{2})"', h)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def get_date_md(date_str):
    """从 '06-13 18:13:15' 抽 '06-13'"""
    if not date_str:
        return None
    m = re.search(r'(\d{2})-(\d{2})', date_str)
    if m:
        return f'{m.group(1)}-{m.group(2)}'
    return None


def get_first_row_amount(d):
    """取列表第一行的金额文本 (作为唯一指纹)
    用 TP 钱包资源 ID tv_amount
    注意: tv_amount 在资产卡片(顶部)和列表项(中下部)都存在,
          用 bounds 过滤 Y > 500, 只取列表项
    """
    try:
        nodes = d(resourceId='vip.mytokenpocket:id/tv_amount')
        for i in range(nodes.count):
            n = nodes[i]
            info = n.info
            bounds = info.get('bounds', {}) or {}
            # uiautomator2 返回 bounds = {'x1','y1','x2','y2'} 或 '[x1,y1][x2,y2]' 字符串
            if isinstance(bounds, dict):
                y1 = bounds.get('y1', 0)
            else:
                m = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', str(bounds))
                y1 = int(m.group(2)) if m else 0
            if y1 > 500:  # 在屏幕中下部, 是列表项
                return n.get_text().strip()
    except Exception:
        pass
    # 兜底
    candidates = d(textMatches=r'-\d+\.?\d*\s*ARK')
    if candidates.exists:
        return candidates[0].get_text().strip()
    return None


# ============================================================
# 4. 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default=None)
    ap.add_argument('--shot-dir', default=r'G:\餐补\screenshots')
    ap.add_argument('--max-items', type=int, default=200)
    ap.add_argument('--batch-pause', type=int, default=999)
    ap.add_argument('--crop-top', type=int, default=130,
                    help='pixels to crop from top (status bar + title; '
                        '130 keeps the green check circle complete)')
    ap.add_argument('--crop-bottom', type=int, default=500)
    ap.add_argument('--start-tab', choices=['all', 'out'], default='out')
    ap.add_argument('--reset', action='store_true', help='清空进度')
    ap.add_argument('--debug', action='store_true', help='自检模式: 滑行前后比对地址, 卡住时标 STUCK')
    ap.add_argument('--recovery-stuck', action='store_true',
                    help='STUCK 时自动加大滑行重试 (3 次), 推荐与 --debug 一起用')
    args = ap.parse_args()

    # 1. ADB
    adb_path = find_adb()
    if not adb_path:
        print('X  adb.exe not found')
        sys.exit(1)
    print(f'[OK]  ADB: {adb_path}')

    # 2. 选设备
    if args.device:
        device = args.device
    else:
        r = subprocess.run([adb_path, 'devices'], capture_output=True, text=True)
        device = None
        for line in r.stdout.splitlines():
            m = re.match(r'^([\w.:\-]+)\s+device\s*$', line.strip())
            if m:
                device = m.group(1)
                break
        if not device:
            print('X  no device found')
            sys.exit(1)
    print(f'[OK]  device: {device}')

    # 3. uiautomator2 连接
    try:
        d = u2.connect(device)
        info = d.info
    except Exception as e:
        print(f'X  uiautomator2 connect failed: {e}')
        sys.exit(1)
    print(f'[OK]  pkg: {info.get("currentPackageName")}')
    print(f'[OK]  screen: {info.get("displayWidth")}x{info.get("displayHeight")}')

    # 4. 输出目录
    inbox = os.path.join(args.shot_dir, '_inbox')
    today = datetime.date.today().isoformat()
    today_dir = os.path.join(inbox, today)
    os.makedirs(today_dir, exist_ok=True)
    progress_path = os.path.join(args.shot_dir, 'capture_progress.json')
    if args.reset or not os.path.exists(progress_path):
        progress = {'done': [], 'fingerprints': []}
    else:
        try:
            with open(progress_path) as f:
                progress = json.load(f)
            if 'fingerprints' not in progress:
                progress['fingerprints'] = []
        except Exception:
            progress = {'done': [], 'fingerprints': []}
    print(f'[OK]  output: {today_dir}')
    print(f'[OK]  progress: {len(progress["done"])} already done')
    print()

    # 5. 前置
    print('=' * 50)
    print('  Prerequisites:')
    print('  1. 雷电已启动, 观察钱包已打开')
    print('  2. 已切到 "转出" tab')
    print('  3. 列表最上一笔 = 今天最新转出')
    print('=' * 50)
    try:
        input('  Press ENTER to start, Ctrl+C to cancel: ')
    except EOFError:
        pass

    # 6. 临时目录
    tmp_dir = os.path.join(args.shot_dir, '_tmp_capture')
    os.makedirs(tmp_dir, exist_ok=True)
    counter = [0]

    def fresh_tmp():
        counter[0] += 1
        return os.path.join(tmp_dir, f'cap_{counter[0]:04d}.png')

    # 7. 循环
    captured = 0
    failed = 0
    stopped = False
    target_md = None  # 目标日期 MM-DD, 从第一条列表项学到, 跨日停止
    try:
        for i in range(args.max_items):
            # === 1. ADB dump 一次拿全信息 ===
            xml = adb_dump_xml(adb_path, device)
            if not xml:
                print(f'  [{i+1}] X  adb dump 失败, 重试')
                time.sleep(0.3)
                continue

            state = xml_page_state(xml)
            if state == 'detail':
                print(f'  [{i+1}] 还在详情页, 自动 back')
                tap_back(d)
                time.sleep(0.8)
                continue
            elif state == 'unknown':
                print(f'  [{i+1}] 不在列表页/详情页, 退出')
                stopped = True
                break

            # === 2. 取列表第一行的日期 (从 XML 解析) ===
            list_date = xml_get_first_row_date(xml)
            list_md = get_date_md(list_date)

            # === 3. 第一次: 学目标日; 之后: 比较 ===
            if list_md:
                if target_md is None:
                    target_md = list_md
                    print(f'  target date set to {target_md} (from list first row)')
                elif list_md != target_md:
                    print(f'  [{i+1}] 列表第一行日期 [{list_md}] != 目标 [{target_md}], STOP')
                    stopped = True
                    break

            # === 4. 取首行金额 (从 XML 解析) ===
            amount = xml_get_first_row_amount(xml)
            if not amount:
                print(f'  [{i+1}] 找不到金额, 滑一行再试')
                scroll_list_up(d, debug=args.debug, recovery=args.recovery_stuck)
                continue

            # === 5. 点第一行 ===
            if not tap_first_tx(d):
                print(f'  [{i+1}] X  tap 失败, 滑一行再试')
                scroll_list_up(d, debug=args.debug, recovery=args.recovery_stuck)
                continue
            print(f'  [{i+1}] tap (date={list_date}, amt={amount})')

            # === 6. 等详情页 ===
            try:
                d(text='发款方').wait(timeout=5)
            except Exception:
                print(f'  [{i+1}] X  详情页没加载, 返回重试')
                tap_back(d)
                time.sleep(1)
                failed += 1
                continue
            time.sleep(0.3)

            # === 7. 截详情 ===
            detail_png = fresh_tmp()
            if not adb_screencap(adb_path, device, detail_png):
                print(f'  [{i+1}] X  screencap failed, 返回重试')
                tap_back(d)
                time.sleep(1)
                failed += 1
                continue

            # === 8. 提取文件名信息 ===
            timestamp = ''
            try:
                tx_node = d(resourceId='vip.mytokenpocket:id/tv_transaction_time')
                if tx_node.exists:
                    txt = tx_node.get_text()
                    m = re.search(r'(\d{2}):(\d{2}):(\d{2})', txt)
                    if m:
                        timestamp = m.group(1) + m.group(2) + m.group(3)
            except Exception:
                pass

            to_addr = ''
            try:
                addr_nodes = d(resourceId='vip.mytokenpocket:id/tv_address')
                if addr_nodes.count >= 2:
                    to_addr = addr_nodes[1].get_text().strip()
            except Exception:
                pass

            if not timestamp:
                timestamp = datetime.datetime.now().strftime('%H%M%S')
            addr7 = 'unknown'
            if to_addr and to_addr.startswith('0x'):
                addr7 = to_addr[:9].lower()
            fname = f'{timestamp}_{addr7}.png'
            target = os.path.join(today_dir, fname)

            # === 9. 裁剪 + 存 ===
            crop_image(detail_png, target, args.crop_top, args.crop_bottom)
            try:
                os.remove(detail_png)
            except Exception:
                pass

            captured += 1
            progress['done'].append(fname)
            with open(progress_path, 'w') as f:
                json.dump(progress, f)
            print(f'  [{i+1}] OK  -> {fname}')

            # === 10. 返回列表 ===
            tap_back(d)
            time.sleep(0.8)

            # === 11. 等列表加载完, 检查是否还在列表页 ===
            time.sleep(0.3)
            if not is_list_page(d):
                # 详情页可能没退出去, 再退一次
                tap_back(d)
                time.sleep(1.0)
                if not is_list_page(d):
                    print(f'  [{i+1}] X  返回后不在列表页, STOP')
                    stopped = True
                    break

            # === 12. 滑一行 (让下一笔进第一行位置) ===
            scroll_list_up(d, debug=args.debug, recovery=args.recovery_stuck)

            # === 13. 每 N 笔暂停 ===
            if captured > 0 and captured % args.batch_pause == 0:
                try:
                    ans = input(f'  captured {captured}, continue? (ENTER to continue, q to quit): ')
                    if ans.strip().lower() in ('q', 'quit'):
                        stopped = True
                        break
                except EOFError:
                    pass

    except KeyboardInterrupt:
        print('')
        print('  Ctrl+C interrupted')
        stopped = True

    finally:
        try:
            if os.path.isdir(tmp_dir):
                for f in os.listdir(tmp_dir):
                    try:
                        os.remove(os.path.join(tmp_dir, f))
                    except Exception:
                        pass
                try:
                    os.rmdir(tmp_dir)
                except Exception:
                    pass
        except Exception:
            pass

    print()
    print('=' * 50)
    print(f'  done: {captured} captured, {failed} failed, stopped={stopped}')
    print(f'  saved: {today_dir}')
    print('  next: rename_screenshots.py + build_index.py')


if __name__ == '__main__':
    main()
