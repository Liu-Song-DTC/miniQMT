# qmt_trade_client.py
# 大QMT文件IPC方案 — 策略端调用库
# 在你的量化策略程序里 import 这个模块，替换掉 xttrader 的直接调用
#
# 使用：
#   from qmt_trade_client import send_order, wait_result, cancel_order, is_qmt_alive

import os
import json
import time
import uuid
from datetime import datetime

IPC_ROOT = r"C:\QuantIPC"


def send_order(action, stock_code, volume, price=None, price_type="limit",
               strategy="default", timeout_sec=30):
    """
    发送下单指令 → QMT执行

    参数:
        action: "buy" 或 "sell"
        stock_code: "000001.SZ" 格式
        volume: 股数（100的整数倍）
        price: 限价（市价单传 None）
        price_type: "limit" 或 "market"
        strategy: 来源策略名称（用于复盘标记）
        timeout_sec: 超时自动撤单秒数（0=不撤）

    返回:
        order_id（全局唯一字符串），可用 wait_result() 等待成交结果
    """
    order_id = f"ORD_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    order = {
        "version": "1.0",
        "order_id": order_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
        "action": action,
        "stock_code": stock_code,
        "price_type": price_type if price_type else "market",
        "price": price if price else 0,
        "volume": volume,
        "strategy": strategy,
        "timeout_sec": timeout_sec,
        "remark": ""
    }
    # 先写.tmp再rename → 原子写入，防止QMT读到半截文件
    tmp = os.path.join(IPC_ROOT, "orders", "pending", f"_{order_id}.tmp")
    final = os.path.join(IPC_ROOT, "orders", "pending", f"{order_id}.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(order, f, ensure_ascii=False, indent=2)
    os.rename(tmp, final)  # NTFS原子操作
    return order_id


def wait_result(order_id, timeout=60, poll_interval=0.2):
    """
    等待成交回执

    参数:
        order_id: send_order() 返回的订单ID
        timeout: 最大等待秒数
        poll_interval: 轮询间隔（秒）

    返回:
        dict（成交回执）或 None（超时）
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in os.listdir(os.path.join(IPC_ROOT, "orders", "done")):
            if order_id in f:
                with open(os.path.join(IPC_ROOT, "orders", "done", f), "r") as fh:
                    return json.load(fh)
        time.sleep(poll_interval)
    return None


def cancel_order(order_id):
    """发送撤单指令"""
    cancel = {
        "version": "1.0",
        "cancel_id": f"CAN_{order_id}",
        "order_id": order_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
        "reason": "strategy_cancel"
    }
    with open(os.path.join(IPC_ROOT, "cancel", f"cancel_{order_id}.json"), "w") as f:
        json.dump(cancel, f, ensure_ascii=False, indent=2)


def is_qmt_alive(max_age=10):
    """
    检查QMT是否在线

    参数:
        max_age: 心跳文件最大允许时间差（秒）

    返回:
        True=在线, False=离线
    """
    path = os.path.join(IPC_ROOT, "status", "heartbeat.json")
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < max_age


def get_account():
    """
    读取账户快照（最近一次QMT写入的持仓/资金数据）

    返回:
        dict 或 None
    """
    path = os.path.join(IPC_ROOT, "status", "account.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


# ======= 使用示例 =======
if __name__ == "__main__":
    if not is_qmt_alive():
        print("QMT不在线！")
        exit(1)

    oid = send_order("buy", "000001.SZ", 1000, price=10.50, strategy="demo")
    print(f"已发单: {oid}")

    result = wait_result(oid, timeout=60)
    if result:
        print(f"成交: {result['status']}, 价={result['filled_price']}, 量={result['filled_volume']}")
    else:
        print("超时，请检查订单状态")
