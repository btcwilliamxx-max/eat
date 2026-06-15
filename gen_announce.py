# -*- coding: utf-8 -*-
"""
餐补公告生成器 v2.0  (阿奇固定表版)
- 文字模版:逐字符保留 v1 原版,零修改
- 列映射:启动时按别名自动匹配,只让你确认一次
- 达标/未达标:不再看「审核结果」列,改用 業績 / 補貼金額(USDT) 是否非空
- 日期解析:Excel 序列数 / 6月8日 / 06/08 / 2026-06-08 / 8位数字
- 备注允许为空
"""
import pandas as pd
import numpy as np
import os
import sys
import re
import traceback
import datetime

# ============================================================
# 1. 列别名映射表(写死,启动时自动匹配)
#    内部字段名(社区/工作室/昵称)按用户口径对应:
#      community -> 專屬群
#      studio    -> 社區
#      nickname  -> 暱稱
# ============================================================
COLUMN_MAPPING = {
    '申請日期起':    ['申請日期起', '申请日期起'],
    '申請日期止':    ['申請日期止', '申请日期止'],
    '專屬群':        ['專屬群', '专属群', 'community'],
    '社區':          ['社區', '社区', 'studio', '工作室名称', '工作室名稱'],
    '暱稱':          ['暱稱', '昵称', 'nickname'],
    '用餐人數':      ['用餐人數', '用餐人数', '人数', 'people'],
    '用餐金額':      ['用餐金額', '用餐金额', 'amount'],
    'ARK地址':       ['ARK地址', 'Ark地址', 'ark地址', '业绩地址', '業績地址'],
    '業績':          ['業績', '业绩', '实际业绩', '實際業績', 'performance'],
    '補貼金額_USDT': ['波波金額\nUSDT', '波波金額USDT', '波波金额USDT', '波波金额_USDT', '波波金額_USDT',
                     '补贴金额', '補貼金額', 'subsidy'],
    '等值ARK':       ['波波金額\nARK', '波波金額ARK', '波波金额ARK', '波波金额_ARK', '波波金額_ARK',
                     '等值ARK', '等值 ARK', 'ark_value'],
    '訂單編號':      ['Order ID', 'order id', '订单编号', '訂單編號', 'order_no'],
    '撥款地址':      ['撥款地址', '拨款地址', 'transfer_address'],
    '備註':          ['波波備註', '小文字备注', '備註', '备注', 'remark'],  # 允许匹配不到
    '幣別':          ['幣別', '币别', 'currency'],
}


def normalize_header(s):
    if s is None:
        return ''
    s = str(s)
    s = s.replace('\n', '').replace('\r', '').replace(' ', '').replace('\u3000', '')
    return s.strip()


def auto_map_columns(df_columns):
    norm_map = {normalize_header(c): c for c in df_columns}
    result = {}
    unmatched = []
    for field, aliases in COLUMN_MAPPING.items():
        hit = None
        for alias in aliases:
            if normalize_header(alias) in norm_map:
                hit = norm_map[normalize_header(alias)]
                break
        result[field] = hit
        if hit is None and field not in ('備註', '幣別'):
            unmatched.append((field, aliases))
    return result, unmatched


# ============================================================
# 2. 日期解析器
# ============================================================
def parse_date(val):
    if val is None:
        return None
    if isinstance(val, (float, np.floating)) and pd.isna(val):
        return None

    if isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
        try:
            return (val.month, val.day)
        except Exception:
            return None

    if isinstance(val, (int, float, np.integer, np.floating)) and not isinstance(val, bool):
        try:
            d = pd.to_datetime(val, unit='D', origin='1899-12-30')
            if not pd.isna(d) and d.year >= 2000:
                return (d.month, d.day)
        except Exception:
            pass

    s = str(val).strip()
    if not s or s.lower() in ('nan', 'nat', 'none', 'null'):
        return None

    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]', s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 12 and 1 <= b <= 31:
            return (a, b)

    m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})\s*$', s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 and b <= 12:
            return (b, a)
        if b > 12 and a <= 12:
            return (a, b)
        return (a, b)

    m = re.match(r'^\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', s)
    if m:
        mo, d = int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return (mo, d)

    if len(s) == 8 and s.isdigit():
        mo, d = int(s[4:6]), int(s[6:8])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return (mo, d)

    try:
        d = pd.to_datetime(s, errors='coerce')
        if not pd.isna(d) and d.year >= 2000:
            return (d.month, d.day)
    except Exception:
        pass

    return None


def format_single_date(val):
    md = parse_date(val)
    if md is None:
        return ""
    return f"{md[0]}/{md[1]}"


def format_date_range(start_date, end_date):
    s = format_single_date(start_date)
    e = format_single_date(end_date)
    if s and e:
        if s == e:
            return s
        else:
            return f"{s}-{e}"
    elif s:
        return s
    elif e:
        return e
    else:
        return ""


# ============================================================
# 3. 地址脱敏(v1 原版逻辑)
# ============================================================
def mask_address(addr):
    try:
        if pd.isna(addr):
            return ""
        s = str(addr).strip()
        if s == "":
            return ""
        if not s.startswith('0x'):
            return s
        if len(s) <= 12:
            return s
        return s[:7] + "******" + s[-5:]
    except Exception:
        return str(addr)


# ============================================================
# 4. 达标判定:不再依赖「审核结果」列
#    业绩 或 补贴金额(USDT) 任一为空 -> 未达标
# ============================================================
def is_not_qualified(row, mapping):
    perf = row.get(mapping.get('業績'))
    sub = row.get(mapping.get('補貼金額_USDT'))
    remark = row.get(mapping.get('備註'))

    def _is_blank(v):
        if v is None:
            return True
        if isinstance(v, (float, np.floating)) and pd.isna(v):
            return True
        s = str(v).strip().lower()
        return s in ('', 'nan', 'nat', 'none', 'null', '0', '0.0')

    if _is_blank(perf) or _is_blank(sub):
        return True
    if remark is not None:
        rstr = str(remark)
        if '不達標' in rstr or '不达标' in rstr:
            return True
    return False


# ============================================================
# 4.5 币种映射:CNY -> RMB, 其他币种直接用原值
# ============================================================
CURRENCY_ALIAS = {
    'CNY': 'RMB',
    'RMB': 'RMB',  # 兼容老表里偶尔直接写 RMB 的
}


def get_currency_label(row, col_map):
    """从 `幣別` 列读币种,返回公告里要显示的标签"""
    col = col_map.get('幣別')
    if not col:
        return 'RMB'
    v = row.get(col)
    if v is None or (isinstance(v, (float, np.floating)) and pd.isna(v)):
        return 'RMB'
    s = str(v).strip()
    if not s or s.lower() in ('nan', 'nat', 'none', 'null'):
        return 'RMB'
    return CURRENCY_ALIAS.get(s.upper(), s.upper())


# ============================================================
# 5. 文字模版 —— 严格保留 v1 原版,逐字符对齐
# ============================================================
TEMPLATE_NOT_QUALIFIED = (
    "📢 餐补审核结果公告  \n"
    "📆  {date_range} 餐补\n"
    "🏠  {community}-{studio}-{nickname}\n"
    "----     \n"
    "您提交的餐补已完成审核  \n"
    "审核结果：未達標❌  \n"
    "当日业绩：{performance} USDT  \n"
    "业绩地址：{address}\n"
    "{extra_lines}----  \n"
    "• 统计范围新增业绩 ≥ 2,000 USDT（180天定期）（封顶 100 USDT）\n"
    "• 统计范围新增业绩 ≥ 5,000 USDT（180天定期）（封顶 200 USDT）\n"
    "• 统计范围新增业绩 ≥ 10000 USDT（180天定期）（封顶 300 USDT)"
)

TEMPLATE_FIRST_BLOCK = (
    "用餐人数：{people}  \n"
    "用餐金额：{amount} {currency}  \n"
    "补贴金额：{subsidy} USDT  \n"
    "{ark_line1}----"
)

TEMPLATE_SECOND_BLOCK = (
    "用餐人数：{next_people}  \n"
    "用餐金额：{next_amount} {currency}  \n"
    "补贴金额：{next_subsidy} USDT  \n"
    "{ark_line2}----"
)

TEMPLATE_MERGED = (
    "📢 餐补审核结果公告  \n"
    "📆  {date_range}  {next_date_range} 餐补\n"
    "🏠  {community}-{studio}-{nickname}\n"
    "----     \n"
    "您提交的餐补已完成审核   \n"
    "审核结果：已达标✅  \n"
    "{date_range}业绩：{performance} USDT  \n"
    "业绩地址：{address}\n"
    "{extra_lines1}{first_block}\n"
    "您提交的餐补已完成审核   \n"
    "审核结果：已达标✅  \n"
    "{next_date_range}业绩：{next_performance} USDT  \n"
    "业绩地址：{next_address}\n"
    "{extra_lines2}{second_block}\n"
    "合计拨款：{total_usdt_str} USDT\n"
    "等值ARK:  {total_ark_str} ARK\n"
    "----  \n"
    "{qualified_footer}"
)

TEMPLATE_QUALIFIED = (
    "📢 餐补审核结果公告  \n"
    "📆  {date_range} 餐补\n"
    "🏠  {community}-{studio}-{nickname}\n"
    "----     \n"
    "您提交的餐补已完成审核   \n"
    "审核结果：已达标✅  \n"
    "当日业绩：{performance} USDT  \n"
    "业绩地址：{address}\n"
    "{extra_lines}----  \n"
    "用餐人数：{people}  \n"
    "用餐金额：{amount} {currency}  \n"
    "补贴金额：{subsidy} USDT  \n"
    "{ark_line}{qualified_footer}"
)

TEMPLATE_QUALIFIED_FOOTER = (
    "----\n"
    "{remark_line}餐补达标补助提示 🔔\n"
    "已达标业绩审核通过\n"
    "按业绩可报额度与实际消费金额，取低值报销\n"
    "补贴以 ARK 发放（按发放当日0点币价）\n"
    "————————————\n"
    "• 统计范围新增业绩 ≥ 2,000 USDT（180天定期）（封顶 100 USDT）\n"
    "• 统计范围新增业绩 ≥ 5,000 USDT（180天定期）（封顶 200 USDT）\n"
    "• 统计范围新增业绩 ≥ 10000 USDT（180天定期）（封顶 300 USDT)"
)


# ============================================================
# 6. 主流程
# ============================================================
def main():
    print("=" * 60)
    print("   餐补公告生成器 v2.0  (阿奇固定表版)")
    print("=" * 60)
    print()

    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        excel_files = [f for f in os.listdir(desktop) if f.lower().endswith(('.xlsx', '.xls'))]
        if not excel_files:
            print("❌ 桌面没有找到 Excel 文件")
            input("按回车退出...")
            return

        print("📋 桌面找到以下 Excel 文件:")
        for i, f in enumerate(excel_files, 1):
            print(f"  {i}. {f}")
        print()
        while True:
            try:
                choice = int(input(f"请选择文件 (1-{len(excel_files)}): ").strip())
                if 1 <= choice <= len(excel_files):
                    excel_file = excel_files[choice - 1]
                    break
                print(f"  请输入 1-{len(excel_files)}")
            except ValueError:
                print("  请输入数字")
        excel_path = os.path.join(desktop, excel_file)
        print(f"\n✅ 已选: {excel_file}")

        print("\n📊 读取 Excel ...")
        df = pd.read_excel(excel_path)
        df = df.dropna(how='all').dropna(axis=1, how='all')
        print(f"   数据规模: {len(df)} 行 × {len(df.columns)} 列")

        print("\n🔧 自动匹配列 ...")
        col_map, unmatched = auto_map_columns(df.columns)
        print(f"   {'字段':<18} {'匹配到':<35} {'样例'}")
        print(f"   {'-'*75}")
        for field in COLUMN_MAPPING.keys():
            actual = col_map.get(field)
            sample = ""
            if actual is not None and len(df) > 0:
                v = df.iloc[0][actual]
                s = str(v) if not pd.isna(v) else ""
                sample = (s[:25] + "...") if len(s) > 25 else s
            tag = "[OK]" if actual else ("[skip]" if field == '備註' else "[MISS]")
            print(f"   {field:<18} {tag:<6} {str(actual or '-'):<33} {sample}")

        if unmatched:
            print("\n❌ 以下必填字段匹配不到,程序中止:")
            for f, aliases in unmatched:
                print(f"   - {f}  期望: {aliases}")
                print(f"     实际表头: {list(df.columns)}")
            input("按回车退出...")
            return

        ans = input("\n确认开始生成公告? (y/n): ").strip().lower()
        if ans != 'y':
            print("已取消")
            return

        # 输出到脚本所在目录(用户习惯:每天下发完手动删掉公告 txt)
        out_dir = os.path.dirname(os.path.abspath(__file__))
        q_path = os.path.join(out_dir, "达标公告.txt")
        nq_path = os.path.join(out_dir, "未达标公告.txt")

        print(f"\n📁 输出目录: {out_dir}\n")

        # 每条公告生成后,把 footer 里的 {remark_line} 字面量做一次替换
        # 这样跟 v1 原版 f-string 的渲染行为完全一致(空时双换行,非空时备注行后接原换行)
        def render_footer(remark_line):
            return TEMPLATE_QUALIFIED_FOOTER.replace('{remark_line}', remark_line)

        success = merged = not_q = 0
        i = 0
        with open(q_path, 'w', encoding='utf-8') as fq, \
             open(nq_path, 'w', encoding='utf-8') as fnq:

            while i < len(df):
                try:
                    row = df.iloc[i]

                    sd_raw = row[col_map['申請日期起']]
                    ed_raw = row[col_map['申請日期止']]
                    date_range = format_date_range(sd_raw, ed_raw)

                    community = str(row[col_map['專屬群']]) if col_map['專屬群'] else ""
                    studio = str(row[col_map['社區']]) if col_map['社區'] else ""
                    nickname = str(row[col_map['暱稱']]) if col_map['暱稱'] else ""
                    people = str(row[col_map['用餐人數']]) if col_map['用餐人數'] else ""
                    amount = str(row[col_map['用餐金額']]) if col_map['用餐金額'] else ""
                    addr_raw = row[col_map['ARK地址']] if col_map['ARK地址'] else ""
                    performance = str(row[col_map['業績']]) if col_map['業績'] else ""
                    subsidy = str(row[col_map['補貼金額_USDT']]) if col_map['補貼金額_USDT'] else ""
                    ark_value = str(row[col_map['等值ARK']]) if col_map['等值ARK'] else ""
                    order_no = str(row[col_map['訂單編號']]) if col_map['訂單編號'] else ""
                    transfer_raw = str(row[col_map['撥款地址']]) if col_map['撥款地址'] else ""
                    remark_raw = row[col_map['備註']] if col_map['備註'] else ""

                    address = mask_address(addr_raw)
                    transfer_address = mask_address(transfer_raw)

                    remark_line = ""
                    if remark_raw and str(remark_raw).lower() not in ('nan', 'nat', 'none', 'null', ''):
                        r = str(remark_raw).strip()
                        if r:
                            remark_line = f"       备注：{r}\n"

                    ark_line = ""
                    if ark_value and ark_value.lower() not in ('nan', 'nat', 'none', 'null', ''):
                        ark_line = f"等值ARK：{ark_value} ARK\n"

                    extra_lines = ""
                    if transfer_address and transfer_address.lower() not in ('nan', 'nat', 'none', 'null', ''):
                        if transfer_address != address:
                            extra_lines += f"拨款地址：{transfer_address}\n"
                    if order_no and order_no.lower() not in ('nan', 'nat', 'none', 'null', ''):
                        extra_lines += f"订单编号：{order_no}\n"
                    if extra_lines:
                        extra_lines = extra_lines.rstrip() + "\n\n"
                    else:
                        extra_lines = "\n"

                    not_qualified_flag = is_not_qualified(row, col_map)

                    print(f"  [{i+1:3d}] 日期={date_range:<10} 业绩={performance:<8} "
                          f"补贴={subsidy}  {'未达标X' if not_qualified_flag else '达标V'}"
                          f"  | {community}-{nickname}")

                    # ----- 未达标 -----
                    if not_qualified_flag:
                        announcement = TEMPLATE_NOT_QUALIFIED.format(
                            date_range=date_range,
                            community=community,
                            studio=studio,
                            nickname=nickname,
                            performance=performance,
                            address=address,
                            extra_lines=extra_lines,
                        )
                        fnq.write(announcement)
                        i += 1
                        not_q += 1
                        if i < len(df):
                            fnq.write("\n\n" + "=" * 18 + "\n\n")
                        continue

                    # ----- 合并判定 -----
                    can_merge = False
                    if i + 1 < len(df):
                        nrow = df.iloc[i + 1]
                        if not is_not_qualified(nrow, col_map):
                            naddr_raw = str(nrow[col_map['ARK地址']]) if col_map['ARK地址'] else ""
                            if naddr_raw == str(addr_raw):
                                can_merge = True

                    if can_merge:
                        nrow = df.iloc[i + 1]
                        next_date_range = format_date_range(
                            nrow[col_map['申請日期起']], nrow[col_map['申請日期止']])
                        next_community = str(nrow[col_map['專屬群']])
                        next_studio = str(nrow[col_map['社區']])
                        next_nickname = str(nrow[col_map['暱稱']])
                        next_people = str(nrow[col_map['用餐人數']])
                        next_amount = str(nrow[col_map['用餐金額']])
                        next_performance = str(nrow[col_map['業績']])
                        next_subsidy = str(nrow[col_map['補貼金額_USDT']])
                        next_ark = str(nrow[col_map['等值ARK']])
                        next_order_no = str(nrow[col_map['訂單編號']])
                        next_transfer_address_raw = str(nrow[col_map['撥款地址']])
                        next_address_raw = str(nrow[col_map['ARK地址']])

                        next_address = mask_address(next_address_raw)
                        next_transfer_address = mask_address(next_transfer_address_raw)

                        extra_lines1 = ""
                        if transfer_address and transfer_address.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            if transfer_address != address:
                                extra_lines1 += f"拨款地址：{transfer_address}\n"
                        if order_no and order_no.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            extra_lines1 += f"订单编号：{order_no}\n"
                        ark_line1 = ""
                        if ark_value and ark_value.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            ark_line1 = f"等值ARK：{ark_value} ARK\n"
                        if extra_lines1:
                            extra_lines1 = extra_lines1.rstrip() + "\n\n"
                        else:
                            extra_lines1 = "\n"

                        extra_lines2 = ""
                        if next_transfer_address and next_transfer_address.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            if next_transfer_address != next_address:
                                extra_lines2 += f"拨款地址：{next_transfer_address}\n"
                        if next_order_no and next_order_no.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            extra_lines2 += f"订单编号：{next_order_no}\n"
                        ark_line2 = ""
                        if next_ark and next_ark.lower() not in ('nan', 'nat', 'none', 'null', ''):
                            ark_line2 = f"等值ARK：{next_ark} ARK\n"
                        if extra_lines2:
                            extra_lines2 = extra_lines2.rstrip() + "\n\n"
                        else:
                            extra_lines2 = "\n"

                        first_block = TEMPLATE_FIRST_BLOCK.format(
                            people=people, amount=amount, currency=get_currency_label(row, col_map),
                            subsidy=subsidy, ark_line1=ark_line1)
                        second_block = TEMPLATE_SECOND_BLOCK.format(
                            next_people=next_people, next_amount=next_amount,
                            currency=get_currency_label(nrow, col_map),
                            next_subsidy=next_subsidy, ark_line2=ark_line2)

                        try:
                            total_usdt = float(subsidy) + float(next_subsidy)
                            total_usdt_str = f"{total_usdt:.2f}"
                        except Exception:
                            total_usdt_str = f"{subsidy} + {next_subsidy}"

                        try:
                            total_ark = float(ark_value) + float(next_ark)
                            total_ark_str = f"{total_ark:.2f}"
                        except Exception:
                            total_ark_str = f"{ark_value} + {next_ark}"

                        announcement = TEMPLATE_MERGED.format(
                            date_range=date_range,
                            next_date_range=next_date_range,
                            community=community,
                            studio=studio,
                            nickname=nickname,
                            performance=performance,
                            address=address,
                            extra_lines1=extra_lines1,
                            first_block=first_block,
                            next_performance=next_performance,
                            next_address=next_address,
                            extra_lines2=extra_lines2,
                            second_block=second_block,
                            total_usdt_str=total_usdt_str,
                            total_ark_str=total_ark_str,
                            qualified_footer=render_footer(remark_line),
                        )
                        fq.write(announcement)
                        i += 2
                        merged += 1
                        success += 1
                        print(f"      -> 合并")
                        if i < len(df):
                            fq.write("\n\n" + "=" * 18 + "\n\n")
                        continue

                    # ----- 普通达标 -----
                    announcement = TEMPLATE_QUALIFIED.format(
                        date_range=date_range,
                        community=community,
                        studio=studio,
                        nickname=nickname,
                        performance=performance,
                        address=address,
                        extra_lines=extra_lines,
                        currency=get_currency_label(row, col_map),
                        people=people,
                        amount=amount,
                        subsidy=subsidy,
                        ark_line=ark_line,
                        qualified_footer=render_footer(remark_line),
                    )
                    fq.write(announcement)
                    i += 1
                    success += 1
                    if i < len(df):
                        fq.write("\n\n" + "=" * 18 + "\n\n")

                except Exception as e:
                    print(f"  X 第 {i+1} 条失败: {e}")
                    traceback.print_exc()
                    i += 1

        print()
        print("=" * 60)
        print("OK 生成完成")
        print("=" * 60)
        print(f"   总数据: {len(df)} 条")
        print(f"   普通达标: {success - merged} 条")
        print(f"   合并公告: {merged} 条 (覆盖 {merged*2} 条数据)")
        print(f"   未达标: {not_q} 条")
        print(f"   达标文件: {q_path}")
        print(f"   未达标文件: {nq_path}")

        # 不再自动 explorer 输出目录(输出到工作目录,用户自己看就行)

    except Exception as e:
        print(f"\nX 程序出错: {e}")
        traceback.print_exc()

    print()
    input("按回车退出...")


if __name__ == "__main__":
    try:
        import pandas as pd
    except ImportError:
        print("缺少 pandas,正在安装...")
        import subprocess
        subprocess.call([sys.executable, "-m", "pip", "install", "pandas", "openpyxl"])
        input("安装完成,请重新运行")
        sys.exit(0)
    main()
