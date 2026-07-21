"""
卖出监控器模块 - 精确定位卖出逻辑问题

功能:
1. 卖出链路全程监控
2. 失败场景精确分类（对应MECE分析的28个场景）
3. 实时告警和统计
4. 问题诊断和建议

设计理念:
- 无侵入性: 通过装饰器和钩子实现,不修改核心业务逻辑
- 高性能: 异步统计,不阻塞交易
- 可配置: 告警规则和通知方式可灵活配置
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from threading import Lock
import json

from logger import get_logger
import config

logger = get_logger("sell_monitor")


class SellMonitor:
    """卖出监控器 - 单例模式"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        # 监控数据存储
        self.sell_attempts = deque(maxlen=1000)  # 最近1000次卖出尝试
        self.failure_stats = defaultdict(int)    # 失败场景统计
        self.alert_history = deque(maxlen=100)   # 最近100条告警

        # 线程安全锁
        self.stats_lock = Lock()

        # 告警配置
        self.alert_rules = self._load_alert_rules()

        # 启动标志
        self.monitoring_enabled = True

        logger.info("✅ 卖出监控器初始化完成")

    def _load_alert_rules(self) -> Dict:
        """加载告警规则配置"""
        return {
            # P0告警: 极高风险,需要立即处理
            'P0': {
                'qmt_not_initialized': {
                    'enabled': True,
                    'threshold': 1,  # 出现1次立即告警
                    'interval': 0,   # 不限制告警频率
                    'message': '🔴 [P0] QMT未初始化,所有卖出操作将失败！'
                },
                'stop_loss_retry_limit': {
                    'enabled': True,
                    'threshold': 1,
                    'interval': 0,
                    'message': '🔴 [P0] 止损信号重试超限被放弃,风险敞口持续！'
                },
                'pending_order_conflict': {
                    'enabled': True,
                    'threshold': 3,  # 连续3次告警
                    'interval': 300, # 5分钟内
                    'message': '🔴 [P0] 活跃委托单持续阻断卖出,可能存在系统同步问题'
                }
            },
            # P1告警: 高风险,需要优先处理
            'P1': {
                'auto_trading_disabled': {
                    'enabled': True,
                    'threshold': 5,  # 5次信号被忽略
                    'interval': 600, # 10分钟内
                    'message': '🟠 [P1] 自动交易已关闭,多个卖出信号被忽略'
                },
                'price_fetch_failed': {
                    'enabled': True,
                    'threshold': 3,
                    'interval': 180,
                    'message': '🟠 [P1] 价格获取连续失败,可能影响卖出执行'
                },
                'qmt_api_failed': {
                    'enabled': True,
                    'threshold': 3,
                    'interval': 300,
                    'message': '🟠 [P1] QMT API调用连续失败,检查客户端状态'
                }
            },
            # P2告警: 中等风险,需要关注
            'P2': {
                'validation_failed': {
                    'enabled': True,
                    'threshold': 5,
                    'interval': 600,
                    'message': '🟡 [P2] 信号验证频繁失败,检查数据质量'
                },
                'condition_not_met': {
                    'enabled': True,
                    'threshold': 10,
                    'interval': 1800,
                    'message': '🟡 [P2] 执行条件频繁不满足,检查配置和环境'
                }
            }
        }

    def record_sell_attempt(self,
                          stock_code: str,
                          signal_type: str,
                          stage: str,
                          status: str,
                          reason: Optional[str] = None,
                          details: Optional[Dict] = None):
        """
        记录卖出尝试

        参数:
        - stock_code: 股票代码
        - signal_type: 信号类型 (stop_loss/take_profit_half/take_profit_full)
        - stage: 执行阶段 (detection/validation/execution/api_call)
        - status: 状态 (success/failed/blocked)
        - reason: 失败原因（对应MECE分析的场景编号）
        - details: 详细信息字典
        """
        if not self.monitoring_enabled:
            return

        attempt = {
            'timestamp': config.now_cst().isoformat(),
            'stock_code': stock_code,
            'signal_type': signal_type,
            'stage': stage,
            'status': status,
            'reason': reason,
            'details': details or {}
        }

        with self.stats_lock:
            self.sell_attempts.append(attempt)

            # 失败场景统计
            if status == 'failed' and reason:
                self.failure_stats[reason] += 1

        # 生成详细日志
        self._log_attempt(attempt)

        # 检查告警规则
        if status == 'failed' and reason:
            self._check_alert_rules(reason, attempt)

    def _log_attempt(self, attempt: Dict):
        """生成结构化日志"""
        stock_code = attempt['stock_code']
        signal_type = attempt['signal_type']
        stage = attempt['stage']
        status = attempt['status']
        reason = attempt.get('reason', '')
        details = attempt.get('details', {})

        # 日志前缀根据状态决定
        prefix = {
            'success': '✅',
            'failed': '❌',
            'blocked': '⚠️'
        }.get(status, 'ℹ️')

        # 基础日志
        base_msg = f"{prefix} [SELL_MONITOR] {stock_code} {signal_type} | 阶段:{stage} | 状态:{status}"

        if status == 'success':
            logger.info(base_msg)
        elif status == 'failed':
            # 失败日志包含更多细节
            error_msg = f"{base_msg} | 失败原因:{reason}"
            if details:
                error_msg += f" | 详情:{json.dumps(details, ensure_ascii=False)}"
            logger.error(error_msg)
        else:
            logger.warning(base_msg)

    def _check_alert_rules(self, reason: str, attempt: Dict):
        """检查告警规则并触发告警"""
        # 映射失败原因到告警规则
        reason_to_rule = {
            # P0场景
            '1.5': 'qmt_not_initialized',
            '1.7': 'stop_loss_retry_limit',
            '2.1': 'pending_order_conflict',

            # P1场景
            '1.1': 'auto_trading_disabled',
            '4.1': 'price_fetch_failed',
            '4.2': 'price_fetch_failed',
            '4.3': 'price_fetch_failed',
            '5.1': 'qmt_api_failed',
            '5.2': 'qmt_api_failed',

            # P2场景
            '2.2': 'validation_failed',
            '2.3': 'validation_failed',
            '2.4': 'validation_failed',
            '2.5': 'validation_failed',
            '2.6': 'validation_failed',
            '3.1': 'condition_not_met',
            '3.2': 'condition_not_met',
            '3.3': 'condition_not_met',
            '3.4': 'condition_not_met',
            '3.5': 'condition_not_met'
        }

        rule_key = reason_to_rule.get(reason)
        if not rule_key:
            return

        # 查找规则配置
        rule_config = None
        priority = None
        for p in ['P0', 'P1', 'P2']:
            if rule_key in self.alert_rules[p]:
                rule_config = self.alert_rules[p][rule_key]
                priority = p
                break

        if not rule_config or not rule_config['enabled']:
            return

        # 检查告警阈值
        threshold = rule_config['threshold']
        interval = rule_config['interval']

        # 统计时间窗口内的失败次数
        now = config.now_cst()
        window_start = now - timedelta(seconds=interval) if interval > 0 else datetime.min

        recent_failures = [
            a for a in self.sell_attempts
            if datetime.fromisoformat(a['timestamp']) >= window_start
            and a.get('reason') == reason
            and a['status'] == 'failed'
        ]

        if len(recent_failures) >= threshold:
            self._trigger_alert(priority, rule_key, rule_config, attempt, len(recent_failures))

    def _trigger_alert(self, priority: str, rule_key: str, rule_config: Dict, attempt: Dict, failure_count: int):
        """触发告警"""
        stock_code = attempt['stock_code']
        signal_type = attempt['signal_type']
        reason = attempt.get('reason', '')

        alert_msg = rule_config['message']
        detail_msg = f"\n股票代码: {stock_code}\n信号类型: {signal_type}\n场景编号: {reason}\n失败次数: {failure_count}"

        full_msg = alert_msg + detail_msg

        # 记录告警
        alert_record = {
            'timestamp': config.now_cst().isoformat(),
            'priority': priority,
            'rule_key': rule_key,
            'message': full_msg,
            'attempt': attempt
        }

        with self.stats_lock:
            self.alert_history.append(alert_record)

        # 输出告警日志
        if priority == 'P0':
            logger.error(f"🚨 {full_msg}")
        elif priority == 'P1':
            logger.warning(f"⚠️ {full_msg}")
        else:
            logger.info(f"ℹ️ {full_msg}")

        # 发送外部通知（如启用）
        if hasattr(config, 'ENABLE_SELL_ALERT_NOTIFICATION') and config.ENABLE_SELL_ALERT_NOTIFICATION:
            self._send_notification(full_msg, priority)

    def _send_notification(self, message: str, priority: str):
        """发送外部通知（微信/企微/邮件等）"""
        try:
            # 尝试导入Methods中的微信推送功能
            try:
                from Methods import WX_send
            except ImportError:
                logger.warning("Methods模块不可用,跳过外部通知")
                return

            # 只有P0和P1级别的告警才发送微信通知
            if priority in ['P0', 'P1']:
                WX_send(message)
                logger.info(f"✅ 告警通知已发送: {priority}")
        except Exception as e:
            logger.warning(f"告警通知发送失败: {str(e)}")

    def get_statistics(self, hours: int = 1) -> Dict:
        """
        获取监控统计信息

        参数:
        - hours: 统计时间范围(小时),默认1小时

        返回:
        - Dict: 统计信息
        """
        with self.stats_lock:
            now = config.now_cst()

            # 指定时间范围的数据
            time_threshold = now - timedelta(hours=hours)
            recent_attempts = [
                a for a in self.sell_attempts
                if datetime.fromisoformat(a['timestamp']) >= time_threshold
            ]

            # 统计各阶段成功/失败数量
            stage_stats = defaultdict(lambda: {'success': 0, 'failed': 0, 'blocked': 0})
            for attempt in recent_attempts:
                stage = attempt['stage']
                status = attempt['status']
                stage_stats[stage][status] += 1

            # 失败原因排行
            failure_ranking = sorted(
                self.failure_stats.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            # 最近告警
            recent_alerts = list(self.alert_history)[-20:]

            # 计算总体统计
            total_success = sum(counts['success'] for counts in stage_stats.values())
            total_failed = sum(counts['failed'] for counts in stage_stats.values())
            total_blocked = sum(counts['blocked'] for counts in stage_stats.values())

            return {
                'monitoring_enabled': self.monitoring_enabled,
                'total_attempts': len(self.sell_attempts),
                'recent_1h_attempts': len(recent_attempts),
                'success_count': total_success,
                'failed_count': total_failed,
                'blocked_count': total_blocked,
                'stage_statistics': dict(stage_stats),
                'top_10_failure_reasons': failure_ranking,
                'recent_alerts': recent_alerts,
                'failure_stats_summary': dict(self.failure_stats)
            }

    def get_diagnostic_report(self, stock_code: Optional[str] = None) -> str:
        """
        生成诊断报告

        参数:
        - stock_code: 可选,指定股票代码生成该股票的报告
        """
        stats = self.get_statistics()

        report_lines = [
            "=" * 80,
            "卖出监控诊断报告",
            "=" * 80,
            f"生成时间: {config.now_cst().strftime('%Y-%m-%d %H:%M:%S')}",
            f"监控状态: {'✅ 启用' if stats['monitoring_enabled'] else '❌ 禁用'}",
            "",
            "📊 统计概览",
            "-" * 80,
            f"总尝试次数: {stats['total_attempts']}",
            f"最近1小时: {stats['recent_1h_attempts']}",
            ""
        ]

        # 阶段统计
        report_lines.append("🔍 各阶段统计 (最近1小时)")
        report_lines.append("-" * 80)
        for stage, counts in stats['stage_statistics'].items():
            success = counts['success']
            failed = counts['failed']
            blocked = counts['blocked']
            total = success + failed + blocked
            success_rate = (success / total * 100) if total > 0 else 0
            report_lines.append(
                f"{stage:20s} | 成功:{success:3d} | 失败:{failed:3d} | 阻断:{blocked:3d} | 成功率:{success_rate:6.2f}%"
            )
        report_lines.append("")

        # 失败原因排行
        report_lines.append("❌ Top 10 失败原因")
        report_lines.append("-" * 80)
        for i, (reason, count) in enumerate(stats['top_10_failure_reasons'], 1):
            reason_desc = self._get_reason_description(reason)
            report_lines.append(f"{i:2d}. [{reason}] {reason_desc}: {count} 次")
        report_lines.append("")

        # 最近告警
        report_lines.append("🚨 最近告警 (最多20条)")
        report_lines.append("-" * 80)
        for alert in stats['recent_alerts'][-5:]:  # 只显示最近5条
            timestamp = alert['timestamp']
            priority = alert['priority']
            message = alert['message'].split('\n')[0]  # 只显示第一行
            report_lines.append(f"[{timestamp}] {priority} - {message}")
        report_lines.append("")

        # 如果指定股票代码,添加该股票的详细信息
        if stock_code:
            report_lines.append(f"🎯 股票 {stock_code} 详细信息")
            report_lines.append("-" * 80)
            stock_attempts = [
                a for a in self.sell_attempts
                if a['stock_code'] == stock_code
            ]
            report_lines.append(f"总尝试次数: {len(stock_attempts)}")

            # 最近5次尝试
            report_lines.append("最近5次尝试:")
            for attempt in list(stock_attempts)[-5:]:
                timestamp = attempt['timestamp']
                signal_type = attempt['signal_type']
                stage = attempt['stage']
                status = attempt['status']
                reason = attempt.get('reason', 'N/A')
                report_lines.append(
                    f"  [{timestamp}] {signal_type} | {stage} | {status} | {reason}"
                )
            report_lines.append("")

        # 建议
        report_lines.append("💡 优化建议")
        report_lines.append("-" * 80)
        suggestions = self._generate_suggestions(stats)
        for suggestion in suggestions:
            report_lines.append(f"• {suggestion}")

        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def _get_reason_description(self, reason: str) -> str:
        """获取失败原因的描述"""
        descriptions = {
            # 类别1: 配置开关阻断
            '1.1': '自动交易总开关关闭',
            '1.2': '卖出权限开关关闭',
            '1.3': '止盈止损功能关闭',
            '1.4': '模拟模式配置错误',
            '1.5': 'QMT连接未初始化',
            '1.6': '同步/异步API配置不匹配',
            '1.7': '重试计数器达到上限',

            # 类别2: 信号验证失败
            '2.1': '活跃委托单冲突',
            '2.2': '止损价格数据无效',
            '2.3': '止损价格比例异常',
            '2.4': '亏损比例过小',
            '2.5': '价格异常值检测',
            '2.6': '止盈信号成本价无效',

            # 类别3: 执行条件不满足
            '3.1': '持仓数据不存在',
            '3.2': '可卖出检查失败',
            '3.3': '卖出数量无效',
            '3.4': '持仓数量类型错误',
            '3.5': '股票代码格式错误',

            # 类别4: 价格获取失败
            '4.1': 'xtdata获取价格失败',
            '4.2': 'data_manager获取价格失败',
            '4.3': '价格有效性验证失败',

            # 类别5: QMT API调用失败
            '5.1': 'order_stock()返回None',
            '5.2': '订单被QMT拒绝',
            '5.3': '滑点调整导致价格异常',
            '5.4': '订单ID映射丢失',

            # 类别6: 异步执行问题
            '6.1': '信号被提前标记为已处理',
            '6.2': '持仓数据同步延迟',
            '6.3': '回调函数未正确处理'
        }
        return descriptions.get(reason, '未知原因')

    def _generate_suggestions(self, stats: Dict) -> List[str]:
        """根据统计数据生成优化建议"""
        suggestions = []

        # 基于失败原因生成建议
        for reason, count in stats['top_10_failure_reasons'][:3]:
            if count >= 5:
                if reason in ['1.1', '1.2', '1.3']:
                    suggestions.append(f"检查配置开关: {self._get_reason_description(reason)} (发生 {count} 次)")
                elif reason in ['2.1']:
                    suggestions.append(f"优化持仓同步频率,减少活跃委托单冲突 (发生 {count} 次)")
                elif reason in ['4.1', '4.2', '4.3']:
                    suggestions.append(f"增加价格获取的容错机制 (发生 {count} 次)")
                elif reason in ['5.1', '5.2']:
                    suggestions.append(f"检查QMT客户端状态和网络连接 (发生 {count} 次)")

        # 基于成功率生成建议
        for stage, counts in stats['stage_statistics'].items():
            total = counts['success'] + counts['failed'] + counts['blocked']
            if total > 0:
                success_rate = counts['success'] / total
                if success_rate < 0.5:
                    suggestions.append(f"{stage} 阶段成功率较低 ({success_rate:.1%}),需要重点排查")

        if not suggestions:
            suggestions.append("系统运行良好,暂无优化建议")

        return suggestions

    def enable(self):
        """启用监控"""
        self.monitoring_enabled = True
        logger.info("✅ 卖出监控已启用")

    def disable(self):
        """禁用监控"""
        self.monitoring_enabled = False
        logger.warning("⚠️ 卖出监控已禁用")

    def get_top_failures(self, limit: int = 10) -> List[tuple]:
        """
        获取失败原因排行

        参数:
        - limit: 返回前N个失败原因

        返回:
        - List[tuple]: [(reason, count), ...]
        """
        with self.stats_lock:
            return sorted(
                self.failure_stats.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]

    def get_stock_statistics(self, stock_code: str, hours: int = 24) -> Dict:
        """
        获取指定股票的统计信息

        参数:
        - stock_code: 股票代码
        - hours: 统计时间范围(小时),默认24小时

        返回:
        - Dict: 统计信息
        """
        with self.stats_lock:
            now = config.now_cst()
            time_threshold = now - timedelta(hours=hours)

            # 过滤指定股票和时间范围的记录
            stock_attempts = [
                a for a in self.sell_attempts
                if a['stock_code'] == stock_code and
                   datetime.fromisoformat(a['timestamp']) >= time_threshold
            ]

            # 统计
            success_count = sum(1 for a in stock_attempts if a['status'] == 'success')
            failed_count = sum(1 for a in stock_attempts if a['status'] == 'failed')
            blocked_count = sum(1 for a in stock_attempts if a['status'] == 'blocked')

            # 失败原因统计
            failure_reasons = defaultdict(int)
            for a in stock_attempts:
                if a['status'] == 'failed' and a.get('reason'):
                    failure_reasons[a['reason']] += 1

            return {
                'stock_code': stock_code,
                'time_range_hours': hours,
                'total_attempts': len(stock_attempts),
                'success_count': success_count,
                'failed_count': failed_count,
                'blocked_count': blocked_count,
                'failure_reasons': dict(failure_reasons),
                'latest_attempt': stock_attempts[-1] if stock_attempts else None
            }

    def clear_statistics(self):
        """清空统计数据（用于测试或重置）"""
        with self.stats_lock:
            self.sell_attempts.clear()
            self.failure_stats.clear()
            self.alert_history.clear()
        logger.info("✅ 监控统计数据已清空")


# 全局单例
_sell_monitor_instance = None


def get_sell_monitor() -> SellMonitor:
    """获取卖出监控器单例"""
    global _sell_monitor_instance
    if _sell_monitor_instance is None:
        _sell_monitor_instance = SellMonitor()
    return _sell_monitor_instance


# 便捷函数
def record_sell_attempt(stock_code: str, signal_type: str, stage: str, status: str,
                       reason: Optional[str] = None, details: Optional[Dict] = None):
    """便捷函数: 记录卖出尝试"""
    monitor = get_sell_monitor()
    monitor.record_sell_attempt(stock_code, signal_type, stage, status, reason, details)


def get_sell_statistics() -> Dict:
    """便捷函数: 获取统计信息"""
    monitor = get_sell_monitor()
    return monitor.get_statistics()


def get_diagnostic_report(stock_code: Optional[str] = None) -> str:
    """便捷函数: 生成诊断报告"""
    monitor = get_sell_monitor()
    return monitor.get_diagnostic_report(stock_code)


if __name__ == "__main__":
    # 测试代码
    monitor = get_sell_monitor()

    # 模拟一些卖出尝试
    test_scenarios = [
        ('000001.SZ', 'stop_loss', 'detection', 'success', None),
        ('000001.SZ', 'stop_loss', 'validation', 'failed', '2.1', {'available': 0, 'volume': 1000}),
        ('600036.SH', 'take_profit_half', 'detection', 'success', None),
        ('600036.SH', 'take_profit_half', 'validation', 'success', None),
        ('600036.SH', 'take_profit_half', 'execution', 'failed', '4.1', {'error': 'xtdata连接失败'}),
    ]

    for scenario in test_scenarios:
        stock_code, signal_type, stage, status, reason, *details = scenario + (None,)
        detail_dict = details[0] if details else None
        monitor.record_sell_attempt(stock_code, signal_type, stage, status, reason, detail_dict)
        time.sleep(0.1)

    # 打印诊断报告
    print(monitor.get_diagnostic_report())
    print("\n")
    print(monitor.get_diagnostic_report('000001.SZ'))
