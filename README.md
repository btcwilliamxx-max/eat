# 餐补公告工具链

## 文件清单

| 文件 | 作用 |
|---|---|
| `run_all.bat` | **双击这个就行** — 一键跑完 3 步 |
| `run_all.ps1` | 一键脚本的 PowerShell 主体(被 .bat 调用) |
| `gen_announce.py` | 读 阿奇XX.xlsx → 生成 达标公告.txt / 未达标公告.txt |
| `rename_screenshots.py` | 扫 `_inbox/` → AI 读截图 → 自动改名归档到 `by_date/<日期>/` |
| `build_index.py` | 解析公告 txt + 扫截图 → 生成 可搜索的 index.html |
| `index.html` | (生成产物) 搜索页 |
| `阿奇XX_达标公告.txt` | (生成产物) 公告文本 |

## 目录结构

```
C:\Users\92071\Desktop\餐补\
  run_all.bat                  ← 双击这个
  run_all.ps1
  gen_announce.py
  rename_screenshots.py
  build_index.py
  index.html                   (自动生成)
  阿奇XX.xlsx
  阿奇01_达标公告.txt           (自动生成)
  阿奇02_达标公告.txt           (自动生成)

G:\餐补\screenshots\
  _inbox\                      ← 18:00 后新截图先扔这里
  by_date\
    2026-06-12\                ← 改完名归档到这里
      175853_5f9731d9_892.jpg
    2026-06-13\
      ...
```

## 每天操作流程

### 18:00 前 —— 生成文字公告

**方式 A:直接跑生成脚本**
```powershell
cd C:\Users\92071\Desktop\餐补
python -X utf8 gen_announce.py
```
按提示选 Excel,回车确认。

**方式 B:用 run_all.bat(也会跑这一步)**
直接双击,但只跑到选完 Excel 就停了 —— 不推荐,适合你后面想再跑改名/索引时再用。

---

### 18:00 后 —— 转账 + 截图采集

在 TP 钱包 / 雷电模拟器里批量转账。**每完成一笔,截一张图,直接拖进** `G:\餐补\screenshots\_inbox\`。

文件名不用改,乱一点没关系。

---

### 下发结束 —— 一键归档 + 生成搜索页

**双击** `C:\Users\92071\Desktop\餐补\run_all.bat`。

弹出黑窗,按顺序跑:
1. **生成公告** —— 提示选 Excel,输编号回车;再问 `是否开始...`,输 `y` 回车
2. **AI 改名截图** —— 自动扫 `_inbox`,显示识别结果,改名为 `<时间戳>_<地址前8位>_<金额>.jpg` 移到 `by_date/YYYY-MM-DD/`
3. **生成搜索页** —— 自动打开浏览器,出现 `index.html`

整个流程 3-5 分钟。

---

### 找截图的日常用法

在自动打开的 `index.html` 里:
- 顶部搜索框输 **地址前 6 位**(如 `0x019Cd`)
- 或输 **金额**(如 `19.61`)
- 或输 **昵称 / 社区 / 日期 / 订单号**
- 右侧"📎 截图"链接 → 点击直接打开对应转账凭证

| 你公告里想找什么 | 在搜索框输什么 |
|---|---|
| 业绩地址 0x019Cd... | `0x019Cd` |
| 等值 ARK 19.61 | `19.61` |
| 订单号 4d8098d3... | `4d8098d3` |
| 昵称 "刘细珍" | `刘细珍` |
| 日期 6/10 | `6/10` |
| 社区 "橡树" | `橡树` |

## 双击 run_all.bat 的前提

| 前提 | 检查方法 | 已就绪 |
|---|---|---|
| Python 3.8+ 在 PATH | PowerShell 输 `python --version` | ✅ |
| mavis.cmd 在 PATH | PowerShell 输 `mavis.cmd --version` | ✅ |
| 3 个 Python 脚本都在 餐补 目录 | 文件夹里看得到 | ✅ |
| 截图仓库 `G:\餐补\screenshots\` 存在 | 文件夹看得到 | ✅ |
| 当天 Excel 在桌面 | `阿奇XX.xlsx` | 看你 |

如果哪个前提不满足,run_all.bat 会**明确报错并暂停**,告诉你哪一项不行。

## 常见问题

**Q: 双击 .bat 闪一下就关了?**
A: 检查 PowerShell 执行策略。在 PowerShell(管理员)里输:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
但实际上 `run_all.bat` 用了 `-ExecutionPolicy Bypass`,**一般不会有这问题**。

**Q: 改名脚本跑完,HTML 里还是"未找到"?**
A: 跑完会自动刷;如果没刷成功,手动跑:
```powershell
cd C:\Users\92071\Desktop\餐补
python -X utf8 build_index.py
```

**Q: AI 识别金额错了,文件名变成 `8_92_xxx.jpg`?**
A: 改用 `--batch-size 1` 重跑那张:
```powershell
python -X utf8 rename_screenshots.py --batch-size 1
```
或者直接手动改名后丢进 `by_date/` 对应日期目录。

**Q: 雷电模拟器截图带边框,识别会受影响吗?**
A: 边框不会被识别,只有"交易详情"卡片里的内容会被读。

**Q: 同一地址 18:00 前后有多笔转账怎么办?**
A: 重命名加了时间戳(精确到秒),不会冲突;合并公告里地址相同会自动关联。

**Q: 我想再跑一次改名(比如新增了几张图)?**
A: 直接双击 `run_all.bat`,它会跑全部 3 步;或者只跑改名:
```powershell
python -X utf8 rename_screenshots.py
```

**Q: 只想刷新搜索页?**
A:
```powershell
python -X utf8 build_index.py
```
它会自动用浏览器打开 `index.html`。

---

# 第二部分:批量截 TP 钱包转账详情(独立工具)

> 这一部分是**独立工具**,不集成进 `run_all.bat`。你**只是观察钱包的"看客"**,公司财务统一转账,你只负责"到点了去观察钱包里截每笔转账详情"。

## 文件

| 文件 | 作用 |
|---|---|
| `capture_receipts.bat` | **双击启动** |
| `capture_receipts.py` | 主脚本 |

## 前置

| 条件 | 备注 |
|---|---|
| 雷电模拟器 1920×1080 平板版 | 你的设置 |
| ADB 可用 | 雷电自带 `adb.exe`,或在 PATH 里 |
| 观察钱包已打开,切到**「转出」** tab | 你手动 |
| 截图仓库 `G:\餐补\screenshots\` 已建 | 已就绪 |

## 流程

```
18:00 财务批量转出(公司钱包,你不需要做任何事)
     ↓
18:01 你:启动雷电 → 打开观察钱包 → 切到"转出"tab
     ↓
双击 capture_receipts.bat
     ↓
[脚本自动]
  ├─ AI 视觉读列表第一行 → 拿到地址+金额+时间
  ├─ 点击该行 → 等详情页加载
  ├─ AI 视觉读详情页 → 校验时间和状态
  ├─ 截图 → 裁剪 → 存到 G:\餐补\screenshots\_inbox\<今天日期>\
  ├─ 返回列表 → 读下一行
  └─ 看到"昨天"时间(如 06-12 17:58) → 自动停止
     ↓
8-15 分钟后, G:\餐补\screenshots\_inbox\2026-06-13\ 有 N 张详情图
     ↓
下一步走之前的流程:
  双击 rename_screenshots.bat 改名归档
  双击 run_all.bat(或单独跑 build_index.py)出搜索页
```

## 关键说明

- **不读公告 txt**:每天笔数 100/120/133 都无所谓,脚本不关心数量
- **停止条件**:详情页时间不是"今天"就停(自动识别日期)
- **断点续传**:进度存档到 `G:\餐补\screenshots\capture_progress.json`,中断后双击 `.bat` 选 `--resume`(暂时需手动加参数,后续可改)
- **每 10 笔暂停**让你确认:防止跑过头;想跳过就在提示时按回车

## 如果卡住了

| 现象 | 原因 | 处理 |
|---|---|---|
| 报"找不到 adb.exe" | ADB 没装/不在 PATH | 用雷电自带的 adb.exe 路径 `--adb "C:\...\adb.exe"` |
| 报"设备 X 未连接" | 雷电没开/ADB 调试没开 | 雷电里 `设置 → 其他 → ADB 调试 = 开`,默认端口 5555 |
| 列表第一行读不到 | 不在"转出"tab / 列表空了 | 切到"转出"tab,确认最上面有今天的转出 |
| 一直停不下来 | 时间格式没被 AI 识别 | Ctrl+C 中断,检查 `capture_progress.json` 里的 `last_tx_time` |

## 与 run_all.bat 的关系

- **不联动**:`capture_receipts.bat` 是独立工具
- **接力**:`capture_receipts` 把图存到 `_inbox/`,之后 `run_all.bat` 跑改名 + 索引会一起处理
- **典型一天流程**:
  1. 18:00 财务转完
  2. 双击 `capture_receipts.bat` → 等它跑完
  3. 双击 `run_all.bat` → 改名 + 出搜索页

---

# 第三部分:雷电 + uiautomator2 自动截图 (替代人工, 0 token)

> **v2 推荐** —— 之前 v1 用了 AI 视觉(每张图调用一次),token 成本太高。
> v2 完全本地,只用 TP 钱包的 Android 资源 ID 定位控件,0 token,5-8 分钟截 100 张。

## 文件

| 文件 | 作用 |
|---|---|
| `capture_v2.bat` | **双击启动** |
| `capture_v2.py` | uiautomator2 + ADB screencap |

## 依赖(一次性)

```bash
pip install uiautomator2
python -m uiautomator2 init    # 把 ATX Agent 装到雷电
```

雷电设置:`设置 → 其他设置 → ADB 调试 = 开启`(默认 5555 端口)。

## 流程

```
观察钱包 → 切"转出"tab(你手动,一次性)
     ↓
双击 capture_v2.bat → ENTER 开始
     ↓
[脚本自动]
  ├─ 用 tv_amount 取第一行金额作为指纹
  ├─ 点第一行进详情
  ├─ 等"发款方"字样出现(条件等待,不等固定 sleep)
  ├─ ADB 截屏 (0.1 秒)
  ├─ PIL 裁剪 (0 token, 0 AI)
  ├─ 用 tv_address[1] 取收款方地址
  ├─ 用 tv_transaction_time 取时间戳
  ├─ 命名: HHMMSS_0xb803ebd.png → 存到 _inbox/2026-MM-DD/
  ├─ 指纹对比: 一样就向上滑动让下一笔进第一行
  └─ 防卡死: 连续 3 次同文件名 → 自动停
     ↓
5-8 分钟, G:\餐补\screenshots\_inbox\2026-06-14\ 100+ 张
     ↓
下一步走之前的流程:
  rename_screenshots.bat → 改名归档
  run_all.bat → 出搜索页
```

## 关键:用 TP 钱包的 Android 资源 ID 定位

这是 v2 的核心。TP 钱包每个控件有稳定 `resource-id`,0 token 直接读 text。

### 列表页

| 字段 | 资源 ID | 说明 |
|---|---|---|
| 列表项金额 | `tv_amount` | 用 bounds 过滤 Y>500 避开资产卡片 |
| 列表项(其他) | `text='合约调用'` | 用来点第一行 |

### 详情页

| 字段 | 资源 ID | 说明 |
|---|---|---|
| 发款方地址 | `tv_address[0]` | 第一个 |
| **收款方地址** | **`tv_address[1]`** | 第二个,这才是我们要的 |
| 交易时间 | `tv_transaction_time` | 形如 `2026-06-13 18:13:15` |
| 状态 | `tv_transaction_status` | "转账成功" |
| 区块号 | `tv_block_number` | |
| 哈希 | `tv_transaction_id` | |
| 金额 | `tv_amount` | |
| 网络费 | `tv_fee` | |

## 双击 capture_v2.bat 的前提

| 前提 | 检查 |
|---|---|
| 雷电已开 | |
| 观察钱包已打开 + 切"转出"tab | 手动,一次性 |
| `pip install uiautomator2` | |
| `python -m uiautomator2 init` | 把 ATX 装到雷电 |
| 雷电 ADB 调试开启 | 端口 5555 |

## 跑出来的文件命名

`HHMMSS_0x[前9字符].png`,例如:
- `181315_0xb803ebd.png` (18:13:15, 收款方 0xB803...)
- `181315_0x659a441.png` (18:13:15, 收款方 0x659a...)

## 与 v1 (capture_receipts.py) 的关系

- **v1 (capture_receipts.py)**:用 AI 视觉,token 太贵,**已废弃**,文件保留作参考
- **v2 (capture_v2.py)**:0 token,推荐

## 与其他脚本的接力

- v2 截的图在 `_inbox/2026-MM-DD/`
- `rename_screenshots.py` 会读这些图(用 AI 视觉 1 次/图,改名归档)
- 跑 `run_all.bat` 自动完成:截图 → 改名 → 出搜索页

## 常见问题

**Q: 滑动到列表底部后,脚本不知道已经截完,会一直滑到没有数据?**
A: 当前没做"已到底"判断。手动 ctrl+C 停。后续可加"顶部检测"。
   或者你看到 `captured 100` 时按回车,脚本会让你"继续?" 输入 `q` 退。

**Q: 雷电 UI 升级了,资源 ID 变了怎么办?**
A: 重跑 `python -c "import uiautomator2 as u2; d=u2.connect('emulator-5554'); print(d.dump_hierarchy())" > xml.txt`
   找新的 ID,改 capture_v2.py 里的 ID 字符串。

**Q: 一次跑了 50 笔被 Ctrl+C,下次怎么继续?**
A: 当前版本用 `--max-items 200` 重新跑,会**重新截所有**(进度文件只记 done 项,不在白名单里)。
   建议:用 `rename_screenshots.py` 的"已存在跳过"机制,或者每次跑全量(因为快)。

**Q: 截图大小不对(图片看着奇怪)?**
A: `--crop-top 170` `--crop-bottom 500` 默认值,根据你的 1080x1920 屏调过。
   详情页结构如果变(比如多了个"查看更多"按钮),微调这两个值。

