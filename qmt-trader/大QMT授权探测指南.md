# 大QMT交易授权探测 & 可用性快速验证指南

> 目的：在真实大QMT环境下，**只读、零下单**地判断你的 QMT 策略端授权到哪条交易通道
> —— **VBA 内置 API（`passorder`）** 还是 **miniQMT `xttrader`**，并快速验证大QMT是否可用。
>
> 这直接决定「大QMT文件IPC降级方案」能否落地：当前 [qmt_trade_executor.py](qmt_trade_executor.py)
> 依赖 `xttrader`；若你的券商只授权 `passorder` 而收紧了 `xttrader`，则 executor 需改造成
> passorder 版本。先探测、再决策。

## 一、两个脚本

| 脚本 | 运行位置 | 作用 |
|------|---------|------|
| [probe_qmt_authorization.py](probe_qmt_authorization.py) | **QMT 策略编辑器内**（定时运行/模型交易） | 在 QMT 策略引擎命名空间里同时探测 `passorder`(VBA) 与 `xttrader` 两条通道 |
| [probe_qmt_xttrader.py](probe_qmt_xttrader.py) | 大QMT机器的**普通 Python(Anaconda)** | 独立验证 `xttrader` 连通性（现有 executor 走的通道） |

> ⚠️ 安全：两脚本**只做检测和只读查询**。`passorder` 仅检测「是否可调用」，**绝不实际调用**；
> 全程不产生任何委托。

## 二、脚本一：QMT 策略端授权探针（最关键）

### 2.1 改账号
打开 [probe_qmt_authorization.py](probe_qmt_authorization.py)，改这两行：
```python
ACCOUNT_ID = "你的资金账号"                       # 必改
QMT_USERDATA_MINI = r"C:\光大证券金阳光QMT实盘\userdata_mini"  # xttrader 探测用，按实际改
```
（若你已按 IPC 方案在 `C:\QuantIPC\{账号}\config.json` 配好账号，`ACCOUNT_ID` 可留默认，脚本会自动读取。）

### 2.2 放进 QMT 运行（二选一）

- **定时运行模式（推荐，与 executor 部署方式一致，最贴近实战）**
  1. QMT → 策略交易 → Python策略 → 新建 **定时运行**
  2. 脚本路径选 `probe_qmt_authorization.py`，周期填 `5000ms`，运行
  3. 跑一轮即可（脚本内有防重，多跑不会重复输出）

- **模型交易模式（passorder 需 ContextInfo 时最准）**
  1. QMT → 策略交易 → 新建 **模型交易**，加载本脚本
  2. 点运行，等 `init/handlebar` 触发一次

### 2.3 看结果
- QMT 的「日志/运行输出」窗口会打印逐项结论
- 同时写入文件：`C:\QuantIPC\probe_result.txt`（更可靠，日志可能被截断）

输出示例：
```
== Channel 1: VBA built-in API ==
  passorder callable: True
  get_trade_detail_data callable: True
  [OK] VBA read account ok args=('12345678','STOCK','ACCOUNT'): total~523100.0 avail~120300.0
  >> VBA channel verdict: USABLE
== Channel 2: miniQMT xttrader ==
  [OK] import xtquant.xttrader ok
  connect() rc: 0 (0=success)
  [OK] query_stock_asset ok: total=523100.0 avail=120300.0
  >> xttrader channel verdict: USABLE
===================== FINAL VERDICT =====================
Both channels usable: current qmt_trade_executor.py (xttrader) deployable...
```

> ⚠️ **编码说明**：[probe_qmt_authorization.py](probe_qmt_authorization.py) 刻意写成**纯 ASCII**（英文输出、无中文），
> 因为 QMT 策略编辑器按 GBK 存储文件，源码里任何中文字节都会让 Python 的 UTF-8 源码解码报
> `SyntaxError: 'utf-8' codec can't decode byte 0xd4`。**请直接复制仓库里的最新版本**粘贴进 QMT，勿改动中文/编码。
> （[probe_qmt_xttrader.py](probe_qmt_xttrader.py) 在普通 Anaconda Python 里运行，UTF-8 正常，**不要**粘进 QMT 编辑器。）

## 三、脚本二：独立 xttrader 连通性探针

在**大QMT机器**上，用普通 Python 运行（前置：QMT 已登录、开启极简模式=行情+交易）：
```bash
# 自动读取项目 account_config.json / config
python qmt-trader/probe_qmt_xttrader.py

# 或显式指定
python qmt-trader/probe_qmt_xttrader.py --path "C:/光大证券金阳光QMT实盘/userdata_mini" --account 12345678
```
返回码：`0`=通道可用；非0=不可用（输出含具体原因/超时/未登录等）。

## 四、结果判读 → 部署决策

| VBA(passorder) | xttrader | 结论与行动 |
|:---:|:---:|-----------|
| ✅ | ✅ | 现有 [qmt_trade_executor.py](qmt_trade_executor.py)（xttrader 版）**直接可用**；passorder 亦可作未来备份通道 |
| ❌ | ✅ | 现有 executor **直接可用**，无需 passorder 改造。也可考虑直接 miniQMT 直连（不必走文件IPC） |
| ✅ | ❌ | 现有 xttrader 版 executor **不可用**；需把 executor 改造成 `passorder` + `get_trade_detail_data` 版本（建议单独立项，参考 litaolemo/xtquant_big_convert） |
| ❌ | ❌ | 账号可能**未登录/未授权**：先确认 QMT 已登录、极简模式已开；仍失败则联系券商确认交易权限 |

## 五、常见问题

1. **`passorder 可用: True` 但查资金失败**
   多为账号未在该 QMT 登录，或 `get_trade_detail_data` 参数格式在你的 QMT 版本有差异（脚本已尝试多种；仍失败请把 `probe_result.txt` 贴出对照）。

2. **`import xtquant.xttrader 失败`**
   当前 Python 环境没有 xtquant 交易模块。QMT 策略编辑器内一般自带；独立 Python 需用 QMT 自带环境或正确安装 miniQMT。

3. **`connect() 返回非0 / 超时`**
   QMT 未启动、未登录、未开极简模式，或 `userdata_mini` 路径不对。

4. **探针会不会误下单？**
   不会。`passorder` 只检测存在性，不调用；其余全是 `query_*` / `get_trade_detail_data` 只读接口。

---
探针只用于诊断，验证完可从 QMT 策略列表移除。正式交易请部署 [qmt_trade_executor.py](qmt_trade_executor.py)。
