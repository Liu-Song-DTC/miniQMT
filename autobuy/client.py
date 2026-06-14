"""
miniqmt_autobuy HTTP 客户端。

严格复用 web1.0 的买入 API 路径下单，并查询持仓用于防重。
下单: POST /api/actions/execute_buy {strategy, quantity, stocks}  (需 X-API-Token)
持仓: GET  /api/positions?version=-1                              (返回完整持仓)
"""
from __future__ import annotations

import requests

from .config import AutoBuyConfig, get_autobuy_logger
from .pool import normalize_code

logger = get_autobuy_logger("autobuy.client")


class WebClient:
    def __init__(self, cfg: AutoBuyConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url
        self.timeout = cfg.timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_token:
            h["X-API-Token"] = self.cfg.api_token
        return h

    def buy(self, code: str) -> tuple:
        """对单只股票下单。返回 (success, http_status, result_dict)。

        复用 execute_buy: strategy=custom_stock, quantity=1, stocks=[code]，
        web 端按 config.POSITION_UNIT 决定单笔金额。
        """
        url = f"{self.base_url}/api/actions/execute_buy"
        body = {"strategy": "custom_stock", "quantity": 1, "stocks": [code]}
        try:
            resp = requests.post(url, json=body, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as e:
            logger.error(f"下单请求失败 {code}: {e}")
            return False, None, {"error": str(e)}

        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        success = resp.status_code == 200 and data.get("status") == "success" \
            and int(data.get("success_count", 0)) > 0
        logger.info(f"下单 {code}: HTTP {resp.status_code} success={success} resp={data}")
        return success, resp.status_code, data

    def get_held_codes(self) -> set | None:
        """查询当前持仓的规范化代码集合(用于防重)。查询失败返回 None。"""
        url = f"{self.base_url}/api/positions"
        try:
            resp = requests.get(url, params={"version": -1}, headers=self._headers(), timeout=self.timeout)
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"查询持仓失败: {e}")
            return None

        # 兼容多种返回结构: {'data':{'positions':[...]}} / {'positions':[...]} / [...]
        positions = []
        if isinstance(data, dict):
            inner = data.get("data", data)
            if isinstance(inner, dict):
                positions = inner.get("positions") or inner.get("positions_all") or []
            elif isinstance(inner, list):
                positions = inner
        elif isinstance(data, list):
            positions = data

        held = set()
        for p in positions:
            if isinstance(p, dict):
                code = p.get("stock_code") or p.get("code")
                if code:
                    held.add(normalize_code(str(code)))
        logger.debug(f"当前持仓 {len(held)} 只: {held}")
        return held
