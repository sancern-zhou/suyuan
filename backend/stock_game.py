#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菲菲股市大亨 - 双人股市模拟游戏
作者: Claude
日期: 2026-05-10
"""

import json
import os
import random
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
import sys

# ==================== 配置 ====================
CONFIG = {
    "UPDATE_INTERVAL": 5,      # 股价更新间隔（秒）
    "AI_DECISION_INTERVAL": 10, # AI决策间隔（秒）
    "EVENT_PROBABILITY": 0.1,   # 大事件发生概率
    "INITIAL_CASH": 10000,      # 初始资金
    "PRICE_MIN": 10,            # 股票最低价
    "PRICE_MAX": 100,           # 股票最高价
    "SAVE_FILE": "stock_state.json",
}

# ==================== 数据模型 ====================
@dataclass
class Stock:
    """股票信息"""
    code: str        # 代码: tech, manu, cons
    name: str        # 名称
    icon: str        # 图标
    price: float     # 当前价格
    prev_price: float  # 前一价格（用于计算涨跌）
    high_52w: float  # 52周最高
    low_52w: float   # 52周最低

    @property
    def change_pct(self) -> float:
        """涨跌幅百分比"""
        if self.prev_price == 0:
            return 0
        return ((self.price - self.prev_price) / self.prev_price) * 100

    @property
    def trend_icon(self) -> str:
        """趋势图标"""
        if self.change_pct > 2:
            return "📈"
        elif self.change_pct < -2:
            return "📉"
        else:
            return "➡️"

@dataclass
class Portfolio:
    """投资组合"""
    cash: float
    holdings: Dict[str, int]  # {stock_code: shares}

    def __post_init__(self):
        if self.holdings is None:
            self.holdings = {}

@dataclass
class Transaction:
    """交易记录"""
    timestamp: str
    player: str        # player 或 ai
    action: str        # buy 或 sell
    stock_code: str
    stock_name: str
    shares: int
    price: float
    total: float

@dataclass
class GameState:
    """游戏状态"""
    stocks: Dict[str, Stock]
    player: Portfolio
    ai: Portfolio
    transactions: List[Transaction]
    day: int
    event_message: Optional[str] = None
    game_started: bool = False
    game_over: bool = False
    winner: Optional[str] = None

# ==================== 股票管理器 ====================
class StockMarket:
    """股票市场管理"""

    STOCKS_CONFIG = {
        "tech": {"name": "科技", "icon": "🚀"},
        "manu": {"name": "制造", "icon": "🏭"},
        "cons": {"name": "消费", "icon": "🛒"},
    }

    def __init__(self):
        self.stocks: Dict[str, Stock] = {}
        self._init_stocks()
        self.event_message = None

    def _init_stocks(self):
        """初始化股票"""
        for code, info in self.STOCKS_CONFIG.items():
            price = random.uniform(CONFIG["PRICE_MIN"], CONFIG["PRICE_MAX"])
            self.stocks[code] = Stock(
                code=code,
                name=info["name"],
                icon=info["icon"],
                price=price,
                prev_price=price,
                high_52w=price,
                low_52w=price,
            )

    def update_prices(self):
        """更新所有股票价格"""
        self.event_message = None

        # 检查是否触发大事件
        if random.random() < CONFIG["EVENT_PROBABILITY"]:
            self._trigger_market_event()

        for stock in self.stocks.values():
            # 保存前一价格
            stock.prev_price = stock.price

            # 计算波动
            if self.event_message and stock.code in self.event_message:
                # 大事件影响
                change = random.uniform(-0.30, 0.30)
            else:
                # 正常波动
                change = random.uniform(-0.05, 0.05)

            # 更新价格
            new_price = stock.price * (1 + change)
            new_price = max(1, min(new_price, 200))  # 价格限制
            stock.price = round(new_price, 2)

            # 更新52周高低
            stock.high_52w = max(stock.high_52w, stock.price)
            stock.low_52w = min(stock.low_52w, stock.price)

    def _trigger_market_event(self):
        """触发市场大事件"""
        events = [
            {"msg": "🔥 科技突破！AI芯片发布！", affected: ["tech"]},
            {"msg": "📉 制造业遇冷！订单减少！", affected: ["manu"]},
            {"msg": "🛍️ 消费狂欢！双十一来袭！", affected: ["cons"]},
            {"msg": "🌪️ 市场崩盘！全面下跌！", affected: ["tech", "manu", "cons"]},
            {"msg": "🚀 经济复苏！全面上涨！", affected: ["tech", "manu", "cons"]},
            {"msg": "📱 科技股大涨！新品发布！", affected: ["tech"]},
            {"msg": "🏭 制造业回暖！出口增长！", affected: ["manu"]},
        ]
        event = random.choice(events)
        self.event_message = event["msg"] + " (" + ",".join(event["affected"]) + ")"

    def get_stock(self, code: str) -> Optional[Stock]:
        """获取股票信息"""
        return self.stocks.get(code)

    def get_stock_by_name(self, name: str) -> Optional[Stock]:
        """通过名称获取股票"""
        for stock in self.stocks.values():
            if stock.name == name or stock.icon in name:
                return stock
        return None

# ==================== AI 玩家 ====================
class AITrader:
    """AI交易者 - 菲菲"""

    def __init__(self, market: StockMarket):
        self.market = market
        self.name = "菲菲"

    def make_decision(self, portfolio: Portfolio) -> Optional[Transaction]:
        """做出交易决策"""
        # 计算每只股票的买入评分
        scores = []
        for stock in self.market.stocks.values():
            # 策略：低价买入，高价卖出
            if stock.change_pct < -2:
                # 下跌超过2%，考虑买入
                score = -stock.change_pct  # 跌越多，分越高
                scores.append(("buy", stock.code, score))
            elif stock.change_pct > 3 and portfolio.holdings.get(stock.code, 0) > 0:
                # 上涨超过3%且持有，考虑卖出
                score = stock.change_pct
                scores.append(("sell", stock.code, score))

        if not scores:
            return None

        # 偶尔犯错（15%概率）
        if random.random() < 0.15:
            # 随机选择一个不优的操作
            action = random.choice(["buy", "sell"])
            stock_code = random.choice(list(self.market.stocks.keys()))
        else:
            # 选择最优操作
            scores.sort(key=lambda x: x[2], reverse=True)
            action, stock_code, _ = scores[0]

        stock = self.market.get_stock(stock_code)

        if action == "buy":
            # 买入：随机数量
            max_shares = int(portfolio.cash / stock.price)
            if max_shares < 10:
                return None
            shares = random.randint(10, min(100, max_shares))
            total = stock.price * shares
            if total > portfolio.cash:
                return None

            portfolio.cash -= total
            portfolio.holdings[stock_code] = portfolio.holdings.get(stock_code, 0) + shares

            return Transaction(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                player="ai",
                action="buy",
                stock_code=stock_code,
                stock_name=stock.name,
                shares=shares,
                price=stock.price,
                total=total,
            )

        else:  # sell
            # 卖出：随机数量
            owned = portfolio.holdings.get(stock_code, 0)
            if owned == 0:
                return None

            shares = random.randint(10, min(100, owned))
            total = stock.price * shares

            portfolio.holdings[stock_code] = owned - shares
            portfolio.cash += total

            return Transaction(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                player="ai",
                action="sell",
                stock_code=stock_code,
                stock_name=stock.name,
                shares=shares,
                price=stock.price,
                total=total,
            )

# ==================== 游戏控制器 ====================
class GameController:
    """游戏控制器"""

    def __init__(self):
        self.market = StockMarket()
        self.ai_trader = AITrader(self.market)
        self.state = GameState(
            stocks={},
            player=Portfolio(cash=CONFIG["INITIAL_CASH"], holdings={}),
            ai=Portfolio(cash=CONFIG["INITIAL_CASH"], holdings={}),
            transactions=[],
            day=1,
        )
        self.running = False
        self.lock = threading.Lock()
        self.update_thread = None
        self.ai_thread = None
        self.screen_needs_update = threading.Event()

        # 从存档加载（如果存在）
        self._try_load()

    def _try_load(self):
        """尝试加载存档"""
        if os.path.exists(CONFIG["SAVE_FILE"]):
            try:
                with open(CONFIG["SAVE_FILE"], "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 恢复股票
                for code, stock_data in data["stocks"].items():
                    self.state.stocks[code] = Stock(**stock_data)

                # 恢复玩家
                player_data = data["player"]
                self.state.player = Portfolio(**player_data)

                ai_data = data["ai"]
                self.state.ai = Portfolio(**ai_data)

                # 恢复交易记录
                self.state.transactions = [
                    Transaction(**t) for t in data["transactions"]
                ]

                self.state.day = data.get("day", 1)
                self.state.game_over = data.get("game_over", False)

                print(f"✅ 存档已加载，第 {self.state.day} 天")
            except Exception as e:
                print(f"⚠️  加载存档失败: {e}")
                self._init_new_game()
        else:
            self._init_new_game()

    def _init_new_game(self):
        """初始化新游戏"""
        for code, stock in self.market.stocks.items():
            self.state.stocks[code] = stock
        self.state.game_started = True
        print("🎮 新游戏开始！")

    def save(self):
        """保存游戏状态"""
        try:
            data = {
                "stocks": {k: asdict(v) for k, v in self.state.stocks.items()},
                "player": asdict(self.state.player),
                "ai": asdict(self.state.ai),
                "transactions": [asdict(t) for t in self.state.transactions],
                "day": self.state.day,
                "game_over": self.state.game_over,
            }
            with open(CONFIG["SAVE_FILE"], "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存失败: {e}")

    def calculate_total_assets(self, portfolio: Portfolio) -> float:
        """计算总资产"""
        stock_value = 0
        for code, shares in portfolio.holdings.items():
            stock = self.state.stocks.get(code)
            if stock:
                stock_value += stock.price * shares
        return portfolio.cash + stock_value

    def process_buy(self, stock_code: str, shares: int, is_ai: bool = False) -> dict:
        """处理买入"""
        with self.lock:
            stock = self.market.get_stock(stock_code)
            if not stock:
                return {"success": False, "message": f"未知股票代码: {stock_code}"}

            portfolio = self.state.ai if is_ai else self.state.player
            total = stock.price * shares

            if total > portfolio.cash:
                return {
                    "success": False,
                    "message": f"资金不足！需要 {total:.2f} 元，现有 {portfolio.cash:.2f} 元"
                }

            portfolio.cash -= total
            portfolio.holdings[stock_code] = portfolio.holdings.get(stock_code, 0) + shares

            player_name = "菲菲" if is_ai else "你"
            transaction = Transaction(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                player="ai" if is_ai else "player",
                action="buy",
                stock_code=stock_code,
                stock_name=stock.name,
                shares=shares,
                price=stock.price,
                total=total,
            )
            self.state.transactions.append(transaction)

            return {
                "success": True,
                "message": f"{player_name} 买入 {stock.icon}{stock.name} {shares}股 @ {stock.price:.2f} 元"
            }

    def process_sell(self, stock_code: str, shares: int, is_ai: bool = False) -> dict:
        """处理卖出"""
        with self.lock:
            stock = self.market.get_stock(stock_code)
            if not stock:
                return {"success": False, "message": f"未知股票代码: {stock_code}"}

            portfolio = self.state.ai if is_ai else self.state.player
            owned = portfolio.holdings.get(stock_code, 0)

            if owned < shares:
                return {
                    "success": False,
                    "message": f"持仓不足！持有 {owned} 股，要卖 {shares} 股"
                }

            total = stock.price * shares
            portfolio.holdings[stock_code] = owned - shares
            portfolio.cash += total

            player_name = "菲菲" if is_ai else "你"
            transaction = Transaction(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                player="ai" if is_ai else "player",
                action="sell",
                stock_code=stock_code,
                stock_name=stock.name,
                shares=shares,
                price=stock.price,
                total=total,
            )
            self.state.transactions.append(transaction)

            return {
                "success": True,
                "message": f"{player_name} 卖出 {stock.icon}{stock.name} {shares}股 @ {stock.price:.2f} 元"
            }

    def update_market(self):
        """更新市场"""
        with self.lock:
            self.market.update_prices()
            for code, stock in self.market.stocks.items():
                self.state.stocks[code] = stock

    def ai_decision(self):
        """AI决策"""
        with self.lock:
            result = self.ai_trader.make_decision(self.state.ai)
            if result:
                self.state.transactions.append(result)
                return f"🤖 菲菲: {result.action == 'buy' and '买入' or '卖出'} {result.stock_name} {result.shares}股"
        return None

    def check_winner(self) -> Optional[str]:
        """检查胜负"""
        player_assets = self.calculate_total_assets(self.state.player)
        ai_assets = self.calculate_total_assets(self.state.ai)

        if player_assets > ai_assets:
            return "你"
        elif ai_assets > player_assets:
            return "菲菲"
        else:
            return "平局"

# ==================== UI 渲染器 ====================
class UIRenderer:
    """终端UI渲染器"""

    # 颜色代码
    COLORS = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "reset": "\033[0m",
        "bold": "\033[1m",
    }

    @staticmethod
    def clear_screen():
        """清屏"""
        os.system("clear" if os.name != "nt" else "cls")

    @staticmethod
    def color(text: str, color_name: str) -> str:
        """给文字添加颜色"""
        color_code = UIRenderer.COLORS.get(color_name, "")
        reset = UIRenderer.COLORS["reset"]
        return f"{color_code}{text}{reset}"

    @classmethod
    def render(cls, game: GameController, last_message: str = ""):
        """渲染游戏界面"""
        cls.clear_screen()

        # 标题
        print(cls.color("╔" + "═" * 63 + "╗", "cyan"))
        print(cls.color("║" + " " * 15 + "📈 菲菲股市大亨" + " " * 34 + "║", "cyan"))
        print(cls.color("║" + " " * 20 + "实时更新中..." + " " * 30 + "║", "yellow"))
        print(cls.color("╚" + "═" * 63 + "╝", "cyan"))
        print()

        # 事件消息
        if game.market.event_message:
            print(cls.color(f"  ⚡ {game.market.event_message}", "yellow"))
            print()

        # 股票行情表
        print(cls.color("  📊 当前行情：", "white"))
        print(cls.color("  ┌" + "─" * 55 + "┐", "cyan"))
        print(cls.color("  │ 股票     │ 现价    │ 涨跌幅    │ 趋势 │ 52周范围     │", "cyan"))
        print(cls.color("  ├" + "─" * 55 + "┤", "cyan"))

        for stock in game.state.stocks.values():
            # 涨跌幅颜色
            change_color = "green" if stock.change_pct >= 0 else "red"
            change_str = f"{stock.change_pct:+.1f}%"

            # 股票信息
            stock_line = (
                f"  │ {stock.icon}{stock.name:<8} │ "
                f"{stock.price:>7.2f} │ "
                f"{cls.color(f'{change_str:>8}', change_color)} │ "
                f"{stock.trend_icon:<4} │ "
                f"{stock.low_52w:.2f}~{stock.high_52w:.2f} │"
            )
            print(stock_line)

        print(cls.color("  └" + "─" * 55 + "┘", "cyan"))
        print()

        # 玩家资产
        player_stock_value = 0
        for code, shares in game.state.player.holdings.items():
            stock = game.state.stocks.get(code)
            if stock:
                player_stock_value += stock.price * shares

        ai_stock_value = 0
        for code, shares in game.state.ai.holdings.items():
            stock = game.state.stocks.get(code)
            if stock:
                ai_stock_value += stock.price * shares

        player_total = game.state.player.cash + player_stock_value
        ai_total = game.state.ai.cash + ai_stock_value

        print(cls.color("  💰 资产对比：", "white"))
        print(f"  🟦 你:   现金 {game.state.player.cash:>8.2f} + 股票 {player_stock_value:>8.2f} = {cls.color(f'{player_total:.2f}', 'green')}")
        print(f"  🟥 菲菲: 现金 {game.state.ai.cash:>8.2f} + 股票 {ai_stock_value:>8.2f} = {cls.color(f'{ai_total:.2f}', 'red')}")
        print()

        # 持仓详情
        print(cls.color("  📋 你的持仓：", "white"))
        if game.state.player.holdings:
            for code, shares in game.state.player.holdings.items():
                if shares > 0:
                    stock = game.state.stocks.get(code)
                    if stock:
                        value = stock.price * shares
                        print(f"     {stock.icon}{stock.name}: {shares}股 × {stock.price:.2f} = {value:.2f} 元")
        else:
            print("     (空仓)")
        print()

        # 最近交易
        if game.state.transactions:
            print(cls.color("  📜 最近交易：", "white"))
            recent = game.state.transactions[-5:]
            for t in recent:
                player_icon = "🤖" if t.player == "ai" else "👤"
                action_str = "买入" if t.action == "buy" else "卖出"
                print(f"     {t.timestamp} {player_icon} {action_str} {t.stock_name} {t.shares}股 @ {t.price:.2f}")
        print()

        # 最后消息
        if last_message:
            print(cls.color(f"  ➤ {last_message}", "yellow"))
            print()

        # 命令提示
        print(cls.color("  ─" * 63, "cyan"))
        print(cls.color("  📖 命令：", "white"))
        print("     买入: buy [股票名] [数量]     例: buy 科技 100")
        print("     卖出: sell [股票名] [数量]    例: sell 制造 50")
        print("     查看行情: 行情 / status")
        print("     查看排行: 排行 / rank")
        print("     历史记录: 历史 / history")
        print("     保存游戏: 保存 / save")
        print("     退出游戏: 退出 / quit / exit")
        print(cls.color("  ─" * 63, "cyan"))
        print()
        print(cls.color("  > ", "green"), end="", flush=True)

# ==================== 游戏主程序 ====================
class StockGame:
    """股市游戏主程序"""

    def __init__(self):
        self.game = GameController()
        self.renderer = UIRenderer()
        self.last_message = ""
        self.input_queue = []
        self.input_ready = threading.Event()

    def start(self):
        """启动游戏"""
        self.game.running = True

        # 启动股价更新线程
        self.game.update_thread = threading.Thread(
            target=self._update_loop, daemon=True
        )
        self.game.update_thread.start()

        # 启动AI决策线程
        self.game.ai_thread = threading.Thread(
            target=self._ai_loop, daemon=True
        )
        self.game.ai_thread.start()

        # 主循环
        self._main_loop()

    def _update_loop(self):
        """股价更新循环"""
        while self.game.running:
            time.sleep(CONFIG["UPDATE_INTERVAL"])
            if self.game.running:
                self.game.update_market()
                self.game.screen_needs_update.set()

    def _ai_loop(self):
        """AI决策循环"""
        while self.game.running:
            time.sleep(CONFIG["AI_DECISION_INTERVAL"])
            if self.game.running:
                msg = self.game.ai_decision()
                if msg:
                    self.last_message = msg
                self.game.screen_needs_update.set()

    def _main_loop(self):
        """主循环（用户输入）"""
        # 首次渲染
        self.renderer.render(self.game, self.last_message)

        while self.game.running:
            # 等待输入或屏幕更新
            self.game.screen_needs_update.wait(timeout=0.1)

            if self.game.screen_needs_update.is_set():
                # 屏幕需要更新（股价变化或AI操作）
                self.renderer.render(self.game, self.last_message)
                self.game.screen_needs_update.clear()
                print(self.last_message or "按回车继续...", end="", flush=True)

            # 非阻塞输入检查
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    self._process_command(line)
                    self.renderer.render(self.game, self.last_message)

    def _process_command(self, command: str):
        """处理用户命令"""
        cmd = command.lower().strip()

        # 买入命令
        if cmd.startswith("buy ") or cmd.startswith("买入"):
            parts = command.split()
            if len(parts) < 3:
                self.last_message = "❌ 格式错误: buy [股票名] [数量]"
                return

            stock_name = parts[1]
            try:
                shares = int(parts[2])
            except ValueError:
                self.last_message = "❌ 数量必须是整数"
                return

            # 查找股票
            stock = self.game.market.get_stock_by_name(stock_name)
            if not stock:
                # 尝试用代码查找
                stock = self.game.market.get_stock(stock_name.lower())

            if not stock:
                self.last_message = f"❌ 未找到股票: {stock_name}"
                return

            result = self.game.process_buy(stock.code, shares)
            self.last_message = result["message"]

        # 卖出命令
        elif cmd.startswith("sell ") or cmd.startswith("卖出"):
            parts = command.split()
            if len(parts) < 3:
                self.last_message = "❌ 格式错误: sell [股票名] [数量]"
                return

            stock_name = parts[1]
            try:
                shares = int(parts[2])
            except ValueError:
                self.last_message = "❌ 数量必须是整数"
                return

            stock = self.game.market.get_stock_by_name(stock_name)
            if not stock:
                stock = self.game.market.get_stock(stock_name.lower())

            if not stock:
                self.last_message = f"❌ 未找到股票: {stock_name}"
                return

            result = self.game.process_sell(stock.code, shares)
            self.last_message = result["message"]

        # 查看行情
        elif cmd in ["行情", "status", "行情"]:
            self.last_message = "📊 已刷新行情"

        # 查看排行
        elif cmd in ["排行", "rank", "排名"]:
            player_assets = self.game.calculate_total_assets(self.game.player)
            ai_assets = self.game.calculate_total_assets(self.game.ai)
            winner = self.game.check_winner()

            self.last_message = (
                f"🏆 排行榜:\n"
                f"   你: {player_assets:.2f} 元\n"
                f"   菲菲: {ai_assets:.2f} 元\n"
                f"   当前领先: {winner}"
            )

        # 历史记录
        elif cmd in ["历史", "history"]:
            if not self.game.state.transactions:
                self.last_message = "📜 暂无交易记录"
                return

            lines = ["📜 交易历史:"]
            for t in self.game.state.transactions[-20:]:
                player_icon = "🤖" if t.player == "ai" else "👤"
                action_str = "买入" if t.action == "buy" else "卖出"
                lines.append(
                    f"   {t.timestamp} {player_icon} {action_str} "
                    f"{t.stock_name} {t.shares}股 @ {t.price:.2f}"
                )
            self.last_message = "\n".join(lines)

        # 保存
        elif cmd in ["保存", "save"]:
            self.game.save()
            self.last_message = "✅ 游戏已保存"

        # 退出
        elif cmd in ["退出", "quit", "exit", "q"]:
            self.game.running = False
            self.game.save()
            print("\n👋 游戏已退出，感谢游玩！")
            sys.exit(0)

        else:
            self.last_message = f"❌ 未知命令: {command}"

# ==================== 入口点 ====================
def main():
    """主函数"""
    print("🎮 正在启动《菲菲股市大亨》...")
    print()

    game = StockGame()

    try:
        game.start()
    except KeyboardInterrupt:
        print("\n\n👋 游戏已中断，感谢游玩！")
        game.game.save()
    except Exception as e:
        print(f"\n❌ 游戏错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
