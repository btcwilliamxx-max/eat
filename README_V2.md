# whitelist_bot V2 - 完全新手教程

> **适用**：完全没碰过 Python / Telegram API 的人
> **目标**：Windows 电脑上，从 0 到跑通 V2 自动白名单脚本
> **时间**：30-60 分钟（含装 Python 和登录拿验证码）

---

## 0. 准备

- Windows 10 / 11
- 一个 **自己的** Telegram 账号（用于跑脚本 + 收验证码）
- 能正常访问 Telegram（收 SMS 验证码）
- 已经有 **`api_id` + `api_hash`**：
  - 公司/同事给
  - 或自己注册：https://my.telegram.org → "API development tools" → 创建 app → 拿 `api_id` (数字) + `api_hash` (字符串)
- 你的 **AI白名單群** chat_id（不会拿？见 [Step 4](#step-4-找你的-ai白名單群-chat_id)）

---

## 1. 装 Python（没装的话）

1. 打开 https://www.python.org/downloads/
2. 下载 **Python 3.10 或更高**
3. 安装时 **务必勾选** ☑ **"Add Python to PATH"** ← **最重要的一步**
4. 装完验证：开 PowerShell 跑

   ```powershell
   python --version
   ```

   应该看到 `Python 3.10.x` 或更高。如果 `python` 找不到，重装时确认勾了 "Add Python to PATH"。

---

## 2. 装 telethon（Python Telegram 客户端库）

```powershell
pip install telethon
```

> 找不到 pip？用 `python -m pip install telethon`

---

## 3. 拿代码

**两种方式二选一：**

### A. 用 GitHub（推荐）

```powershell
cd D:\whitelist_bot          # 你要放脚本的目录，任意目录都行（不要放 G 盘 kefuhuifu 项目里）
git clone https://github.com/btcwilliamxx-max/eat.git
cd eat
```

### B. 让同事直接拷文件给你

让同事发 `whitelist_bot_v2.py` + `first_login.py` 两个文件（不到 30KB），拷到你**任意目录**（比如 `D:\whitelist_bot\`）。

---

## 4. 登录 Telegram 拿 session

```powershell
cd D:\whitelist_bot\eat        # 或你放脚本的目录
python first_login.py --field TG_SESSION_STRING_2
```

脚本会依次问你：

| 提示 | 输入 |
|------|------|
| `Please enter your phone (or bot token):` | 你的手机号（**国际格式**，如 `+8613812345678`） |
| `Please enter the code you received:` | Telegram 客户端收到的 **5 位验证码**（2 分钟内有效） |
| `Please enter your password:` | 2FA 密码（**如果**你开了两步验证），**没**开直接回车 |

登录成功后会：
- 自动写 **`.env`** 文件（含 `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING_2`）
- 自动写 **`tg_session_2.txt`** 文件（session 备份，不要给别人看）

**注意**：
- 收不到验证码？Telegram 同一号 **1 分钟内** 只能发 1 次，等 5 分钟再试
- 手机漫游关了？打开再试
- **不要**用别人的 session 字符串（等于借号），必须**自己**登录拿

---

## 5. 找你的 AI白名單群 chat_id

```powershell
python find_chat_id.py 白名單
```

输出类似：

```
============================================================
  find_chat_id - 列 +你自己的号 所有 dialog
  关键字过滤: "白名單"
============================================================
登录: @xxx
拉 dialogs (可能几秒)...

找到 1 个群 (总 dialogs: 150)

chat_id        type        username               名称
----------------------------------------------------------------------
3123456789     group                              AI白名單
============================================================
```

**记下 `chat_id`**（比如 `3123456789`）—— 接下来要用。

找不到？试试不带关键字：

```powershell
python find_chat_id.py
```

翻找群名含 "白名單" 的那个。

---

## 6. 跑 V2（dry-run 测试）

**先把 chat_id 配好**——二选一：

### 方式 1：跑时传参数（不用改代码）

```powershell
python whitelist_bot_v2.py --chat-id 3123456789
```

### 方式 2：改代码顶部

打开 `whitelist_bot_v2.py`，找到这行：

```python
DEFAULT_CHAT_IDS = [5526703064]
```

改成你自己的：

```python
DEFAULT_CHAT_IDS = [3123456789]    # ← 你的 chat_id
```

改完保存，然后跑：

```powershell
python whitelist_bot_v2.py
```

---

**会看到**：

```
============================================================
  whitelist_bot (V2) - DRY-RUN
============================================================
  监听群:   {3123456789}
  机器人:   @addAIloginwhitelistbot
  新加 reply: "+"
  已开 reply: "之前已经加过了"
  无效 reply: "地址不对"
  bot 反馈 timeout: 10s
  已处理:   0 条
  关闭:     Ctrl+C
============================================================

  ⚠️  DRY-RUN 模式 - 不会实际发消息, 只 print 计划动作
  确认输出对后, 用 --live 切真:
      python whitelist_bot_v2.py --live

[OK] 登录: @你的用户名 (你的ID)
[OK] bot: @addAIloginwhitelistbot (id=xxx)
[*] 监听 1 个群, 等消息...
```

**注意**：
- 监听群 = `你的 chat_id` ✅
- 监听 `1 个群` ✅
- 状态 `DRY-RUN` ✅
- **没**红色 traceback 报错

看到 `[OK] 登录` 和 `[*] 监听 1 个群` 就 OK 了。

**窗口别关**，让它继续监听。

---

## 7. 测试 3 个 case

切到 **AI白名單 群**，分别发 3 条测试消息（**用同事的 AI白名單群**或自己的测试群，别在生产群发）：

### Case 1：完整地址（业务消息）

发：
```
0xBEEF000000000000000000000000000000000000
https://t.me/c/123456789/123
```

应该看到脚本窗口：
```
[NEW] chat="AI白名單" sender=@xxx msg=...
       addresses: ['0xBEEF000000000000000000000000000000000000']
       mode: DRY-RUN
  -> [DRY] (Conversation 内部发) "/a 0xBEEF..." to @addAIloginwhitelistbot
  -> [DRY] 等 bot 反馈 (timeout 10s)
  -> [DRY] (假设新加) reply "+"
```

### Case 2：少几位地址（无效）

发：
```
0x12345
https://t.me/c/123456789/124
```

应该看到：
```
[INVALID] msg ... 有 1 个无效地址 (缺几位/多几位)
           invalid: 0x12345 (hex_len=5)
  -> [DRY] reply "地址不对" to msg ...
```

### Case 3：单独地址（V2 允许无 t.me 链接）

发：
```
0xDEAD000000000000000000000000000000000000
```

应该看到跟 Case 1 类似，**不要求** t.me 链接（V2 vs V1 区别）。

**3 个 case 都对** → 切真跑。

---

## 8. 切真跑

确认 dry-run 都对：

```powershell
# 方式 1: 传参
python whitelist_bot_v2.py --chat-id 3123456789 --live

# 方式 2: 改完代码
python whitelist_bot_v2.py --live
```

**窗口常驻**，**别关**。

去 AI白名單 群发业务消息，看：
- 群里**有**你的号 reply "+" / "之前已经加过了" / "已开" / "地址不对"
- 打开手机 Telegram 看 `@addAIloginwhitelistbot` 私聊 → 应该看到 "白名單地址新增成功" 或 "批量處理完成" 反馈

**停止**：回到 PowerShell 窗口，按 `Ctrl+C`。

---

## 常见问题

### Q1: `python` 找不到

**A**: Python 没装好。重装时**务必**勾选 ☑ "Add Python to PATH"。装完**关掉** PowerShell 重新开。

### Q2: `pip` 找不到

**A**: 用 `python -m pip install telethon`。

### Q3: 收不到 Telegram 验证码

**A**:
- Telegram 同一号 1 分钟内只能发 1 次，等 5 分钟再试
- 手机漫游关了？打开
- 装了科学上网？Telegram 在中国大陆需要代理（HTTP / SOCKS 代理）

### Q4: 2FA 密码忘了

**A**: 去 Telegram 客户端 → Settings → Privacy → Two-Step Verification → 输入密码 / 重置。

### Q5: 改完 `DEFAULT_CHAT_IDS` 跑还是默认 5526703064

**A**: 缓存问题。改完 **Ctrl+C 停掉再重启**脚本。

### Q6: 脚本启动但收不到消息

**A**:
- 确认 `.env` 里的 `TG_SESSION_STRING_2` 是**你自己的** session（不是别人给的）
- 确认你的 Telegram 号**在** AI白名單群里（用手机登自己的号看群里有没有你的号）
- 重启脚本（Ctrl+C 再跑）
- 看脚本窗口**有没**红色报错

### Q7: bot 反馈超时（10s 没回）

**A**:
- bot 服务器可能卡了，等 1 分钟重试
- 同一秒大量发 `/a` 可能被 bot 限速
- 看脚本窗口的 `X bot 反馈 timeout (10s)` 错误，**不影响**白名单已经加上（bot 收到命令了，**只是** bot 反馈没收到）

### Q8: 重复处理（processed.json 没去重）

**A**: 看 `whitelist_v2_processed.json` 是否存在。第一次跑会创建，重复消息**不**会重复发 `/a`。

要**重跑**某条消息（测试），删 `whitelist_v2_processed.json` 里的对应行。

### Q9: PowerShell 中文乱码

**A**: 跑前加 `$env:PYTHONIOENCODING='utf-8'`。这不影响脚本逻辑，**只是**显示问题。

### Q10: 怎么知道 bot username 对不对

**A**: 跑 `python find_chat_id.py addAIloginwhitelistbot` 试，**不**带 chat_id 看 bot 详情。**或者**用手机打开 `@addAIloginwhitelistbot` 看能不能发消息。

---

## 完整命令清单（收藏用）

```powershell
# 一次性 setup
pip install telethon
git clone https://github.com/btcwilliamxx-max/eat.git
cd eat
python first_login.py --field TG_SESSION_STRING_2
python find_chat_id.py 白名單
                                    # 记下 chat_id
# 编辑 whitelist_bot_v2.py, 改 DEFAULT_CHAT_IDS = [你的chat_id]

# 每天用
python whitelist_bot_v2.py --live                       # 监听 + 自动化

# 或者传参, 不用改代码
python whitelist_bot_v2.py --chat-id 3123456789 --live

# 测试
python whitelist_bot_v2.py                              # 默认 dry-run
python whitelist_bot_v2.py --chat-id 3123456789          # 指定群, dry-run

# 看历史
cat whitelist_v2.log                                    # PowerShell: Get-Content whitelist_v2.log
```

---

## 文件清单（这个目录应该有什么）

```
D:\whitelist_bot\eat\        # 或你放脚本的目录
├── .env                       # ← 登录后自动创建, 含你的 session, 不要给别人
├── .gitignore                 # 排除 .env / log / processed.json
├── first_login.py             # 登录拿 session (第 4 步)
├── find_chat_id.py            # 找群 chat_id (第 5 步)
├── whitelist_bot.py           # V1 (有 t.me 链接要求, 一般不用)
├── whitelist_bot_v2.py        # V2 主程序 (第 6-8 步)
├── tg_session_2.txt           # session 备份, 登录后自动创建
├── whitelist_v2.log           # 运行时日志 (持续增长)
└── whitelist_v2_processed.json  # 去重表 (持续增长)
```

`.env` 和 `tg_session_2.txt` **绝对不要** commit / 共享 / 发给同事 —— **等于账号密码**。

---

## 完了？

跑通后：

1. 群里发业务消息，bot 自动开白名单
2. 群里 reply "+" / "之前已经加过了" / "已开" / "地址不对"（按情况）
3. 客服看到 reply 知道处理了
4. 你不用每条都人工操作

**新的需求**（V2.1 / V3）？比如：
- 暂停 / 启用脚本（手机发命令）
- 多人协同（不被 reply 计数检查误伤）
- 跑在云 VPS（不依赖电脑开关机）

再聊。
