"""baostock 接入规范化辅助模块。

新版 baostock(00.9.x) 相比旧版(0.8.x) 收紧了访问格式与行为：
- 登录前可通过 ``set_API_key`` 传入 API Key（旧版无此接口）；
- 服务端对证券代码格式、登录次数、账号权限/激活状态校验更严格；
- 复权类型 ``adjustflag`` 仅接受 ``'1'/'2'/'3'``（后复权/前复权/不复权）。

本模块把这些差异集中成几个纯函数，供 Methods.py 与 data_manager.py 复用，
保持各调用点逻辑一致、易于单元测试。
"""

import config

# 复权类型映射：mootdx 风格 -> baostock。
# baostock：1=后复权, 2=前复权, 3=不复权；未知值一律按不复权处理。
_ADJUST_MAP = {
    'qfq': '2', 'hfq': '1', 'bfq': '3',
    '1': '1', '2': '2', '3': '3',
}

# 新版收紧访问后可能出现的登录错误码 -> 可读提示。
_LOGIN_ERROR_HINTS = {
    '10001004': '客户端版本过期，请升级 baostock',
    '10001005': '账号登录数达到上限，请确认已正确 logout',
    '10001006': '用户权限不足（可能需配置 BAOSTOCK_API_KEY）',
    '10001007': '需要登录激活（请检查 BAOSTOCK_API_KEY）',
    '10001011': '黑名单用户',
}


def apply_api_key(bs):
    """登录前应用 API Key（仅当已配置且当前 baostock 版本支持时）。

    返回 True 表示成功设置；旧版 baostock(0.8.x) 无 set_API_key 时返回 False，
    匿名访问仍可获取免费数据。
    """
    api_key = getattr(config, 'BAOSTOCK_API_KEY', '') or ''
    if api_key and hasattr(bs, 'set_API_key'):
        try:
            bs.set_API_key(api_key)
            return True
        except Exception:
            return False
    return False


def normalize_adjustflag(flag):
    """把 adjustflag 归一化为 baostock 接受的 ``'1'/'2'/'3'``。

    兼容 mootdx 风格（qfq/hfq/bfq）与数字字符串；空值或未知值返回 ``'3'``（不复权）。
    """
    if flag is None:
        return '3'
    return _ADJUST_MAP.get(str(flag).strip().lower(), '3')


def describe_login_error(error_code, error_msg=''):
    """为收紧访问后的登录错误码补充可读说明，便于排查激活/权限类问题。"""
    hint = _LOGIN_ERROR_HINTS.get(str(error_code))
    if hint:
        return f"{error_msg}（{hint}）" if error_msg else hint
    return error_msg
