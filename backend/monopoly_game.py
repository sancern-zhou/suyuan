#!/usr/bin/env python3
"""
菲菲大富翁 - 双人回合制棋盘游戏
通过微信指令操作终端
"""

import random
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, List

# 游戏配置
BOARD_SIZE = 10
SAVE_FILE = "/home/xckj/suyuan/backend/monopoly_state.json"

# 格子事件类型
EVENT_TYPES = ["empty", "boost", "slow", "coin", "fate"]
EVENT_NAMES = {
    "empty": "⬜ 空地",
    "boost": "⚡ 加速",
    "slow": "🐢 减速",
    "coin": "💰 金币",
    "fate": "❓ 命运"
}
EVENT_DESC = {
    "empty": "无事发生",
    "boost": "再前进2格！",
    "slow": "后退1格...",
    "coin": "获得1金币！",
    "fate": "命运抉择！"
}

# 道具配置
ITEMS = {
    "shield": {"name": "🛡️ 护盾", "cost": 2, "desc": "抵挡一次减速/后退"},
    "rocket": {"name": "🚀 火箭", "cost": 3, "desc": "直接前进3格"}
}


@dataclass
class Player:
    name: str
    icon: str
    position: int = 0
    coins: int = 1
    shield: bool = False
    skip_turn: bool = False

    def has_item(self, item: str) -> bool:
        return item == "shield" and self.shield


@dataclass
class GameState:
    board_events: List[str]
    player1: Player
    player2: Player
    current_player: int = 0  # 0 或 1
    turn: int = 1
    winner: Optional[str] = None
    game_log: List[str] = None

    def __post_init__(self):
        if self.game_log is None:
            self.game_log = []


class MonopolyGame:
    def __init__(self):
        self.state = self.load_or_create_game()

    def load_or_create_game(self) -> GameState:
        """加载或创建游戏"""
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 重建 Player 对象
                    player1 = Player(**data["player1"])
                    player2 = Player(**data["player2"])
                    return GameState(
                        board_events=data["board_events"],
                        player1=player1,
                        player2=player2,
                        current_player=data["current_player"],
                        turn=data["turn"],
                        winner=data.get("winner"),
                        game_log=data.get("game_log", [])
                    )
            except Exception as e:
                print(f"加载存档失败: {e}")

        # 创建新游戏
        board_events = self._generate_board()
        player1 = Player(name="你", icon="🟦", position=0, coins=2)
        player2 = Player(name="菲菲", icon="🟥", position=0, coins=2)
        return GameState(
            board_events=board_events,
            player1=player1,
            player2=player2,
            current_player=0,
            turn=1
        )

    def _generate_board(self) -> List[str]:
        """生成棋盘事件（起点和终点固定为空地）"""
        events = ["empty"]  # 起点
        for i in range(1, BOARD_SIZE):
            if i == BOARD_SIZE - 1:
                events.append("empty")  # 终点前
            else:
                weights = [40, 15, 15, 20, 10]  # empty, boost, slow, coin, fate
                events.append(random.choices(EVENT_TYPES, weights=weights)[0])
        events.append("empty")  # 终点
        return events

    def save_game(self):
        """保存游戏"""
        data = {
            "board_events": self.state.board_events,
            "player1": asdict(self.state.player1),
            "player2": asdict(self.state.player2),
            "current_player": self.state.current_player,
            "turn": self.state.turn,
            "winner": self.state.winner,
            "game_log": self.state.game_log[-20:]  # 只保留最近20条
        }
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_current_player(self) -> Player:
        """获取当前玩家"""
        return self.state.player1 if self.state.current_player == 0 else self.state.player2

    def get_other_player(self) -> Player:
        """获取对手"""
        return self.state.player2 if self.state.current_player == 0 else self.state.player1

    def switch_turn(self):
        """切换回合"""
        if self.state.current_player == 0:
            self.state.current_player = 1
        else:
            self.state.current_player = 0
            self.state.turn += 1

    def roll_dice(self) -> int:
        """掷骰子"""
        return random.randint(1, 6)

    def trigger_event(self, player: Player, position: int) -> str:
        """触发格子事件"""
        if position >= BOARD_SIZE:
            return ""

        event = self.state.board_events[position]
        message = EVENT_DESC[event]

        if event == "boost":
            player.position = min(BOARD_SIZE, player.position + 2)
            self.state.game_log.append(f"{player.icon}{player.name}加速前进2格！")
        elif event == "slow":
            if player.shield:
                player.shield = False
                message = "护盾抵挡了减速！"
                self.state.game_log.append(f"{player.icon}{player.name}的护盾破碎！")
            else:
                player.position = max(0, player.position - 1)
                self.state.game_log.append(f"{player.icon}{player.name}被减速后退1格")
        elif event == "coin":
            player.coins += 1
            self.state.game_log.append(f"{player.icon}{player.name}获得1金币！")
        elif event == "fate":
            fate = random.choice(["forward", "backward", "skip"])
            if fate == "forward":
                player.position = min(BOARD_SIZE, player.position + 2)
                message = "命运：前进2格！"
                self.state.game_log.append(f"{player.icon}{player.name}命运眷顾，前进2格")
            elif fate == "backward":
                if player.shield:
                    player.shield = False
                    message = "命运：护盾抵挡后退！"
                    self.state.log_append(f"{player.icon}{player.name}护盾抵挡命运")
                else:
                    player.position = max(0, player.position - 2)
                    message = "命运：后退2格..."
                    self.state.log_append(f"{player.icon}{player.name}命运捉弄，后退2格")
            else:
                player.skip_turn = True
                message = "命运：暂停一轮！"
                self.state.log_append(f"{player.icon}{player.name}被命运暂停一轮")

        return f"\n🎯 {EVENT_NAMES[event]}: {message}"

    def state_log_append(self, msg: str):
        """添加日志（修复方法名）"""
        self.state.game_log.append(msg)

    def check_winner(self) -> Optional[str]:
        """检查胜利条件"""
        if self.state.player1.position >= BOARD_SIZE:
            self.state.winner = "你"
            return "你"
        if self.state.player2.position >= BOARD_SIZE:
            self.state.winner = "菲菲"
            return "菲菲"
        return None

    def execute_roll(self):
        """执行掷骰子"""
        player = self.get_current_player()

        if player.skip_turn:
            player.skip_turn = False
            msg = f"{player.icon}{player.name}本轮暂停..."
            self.state.game_log.append(msg)
            self.switch_turn()
            return msg

        dice = self.roll_dice()
        old_pos = player.position
        player.position = min(BOARD_SIZE, player.position + dice)

        msg = f"{player.icon}{player.name}掷出 {dice} 点，从格{old_pos}前进到格{player.position}"
        self.state.game_log.append(msg)

        # 检查胜利
        if player.position >= BOARD_SIZE:
            winner = self.check_winner()
            if winner:
                self.save_game()
                return f"\n🎉 {winner}到达终点，获胜！"

        # 触发事件
        event_msg = self.trigger_event(player, player.position)

        # 再次检查胜利（可能被加速送到终点）
        if player.position >= BOARD_SIZE:
            winner = self.check_winner()
            if winner:
                self.save_game()
                return f"{event_msg}\n🎉 {winner}到达终点，获胜！"

        self.switch_turn()
        self.save_game()
        return f"{msg}{event_msg}"

    def execute_use_item(self, item: str) -> str:
        """使用道具"""
        player = self.get_current_player()

        if item == "shield":
            return "🛡️ 护盾是被动道具，自动触发！"

        if item == "rocket":
            if player.coins < ITEMS["rocket"]["cost"]:
                return "💸 金币不足！"
            player.coins -= ITEMS["rocket"]["cost"]
            old_pos = player.position
            player.position = min(BOARD_SIZE, player.position + 3)
            msg = f"{player.icon}{player.name}使用🚀火箭，从格{old_pos}飞到格{player.position}！"
            self.state.game_log.append(msg)

            if player.position >= BOARD_SIZE:
                winner = self.check_winner()
                if winner:
                    self.save_game()
                    return f"{msg}\n🎉 {winner}获胜！"

            self.switch_turn()
            self.save_game()
            return msg

        return f"❓ 未知道具: {item}"

    def render_board(self) -> str:
        """渲染棋盘"""
        board = []
        p1_pos = self.state.player1.position
        p2_pos = self.state.player2.position

        for i in range(BOARD_SIZE + 1):
            cell = ""
            if i == 0:
                cell = "起"
            elif i == BOARD_SIZE:
                cell = "🏁"
            else:
                event = self.state.board_events[i]
                cell = EVENT_NAMES[event].split()[0]  # 获取图标部分

            # 显示玩家
            if p1_pos == i and p2_pos == i:
                cell = f"双{cell}"
            elif p1_pos == i:
                cell = f"你{cell}"
            elif p2_pos == i:
                cell = f"菲{cell}"
            else:
                cell = f" {cell} "

            board.append(cell)

        return "🗺️ " + "".join(board)

    def render(self, last_action: str = ""):
        """渲染游戏界面"""
        os.system("clear" if os.name != "nt" else "cls")

        p1 = self.state.player1
        p2 = self.state.player2

        print("╔══════════════════════════════════╗")
        print("║    🎲 菲菲大富翁                 ║")
        print(f"║    第 {self.state.turn} 回合                     ║")
        print("╚══════════════════════════════════╝")
        print()

        # 玩家状态
        print(f"🟦 你：格 {p1.position}  💰{p1.coins}金币", end="")
        if p1.shield:
            print("  🛡️有护盾")
        else:
            print()
        print(f"🟥 菲菲：格 {p2.position}  💰{p2.coins}金币", end="")
        if p2.shield:
            print("  🛡️有护盾")
        else:
            print()
        print()

        # 棋盘
        print(self.render_board())
        print()

        # 当前玩家
        current = self.get_current_player()
        print(f"轮到：{current.icon} {current.name}")
        print()

        # 上次操作结果
        if last_action:
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(last_action)
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print()

        # 操作提示
        print("命令 (roll掷骰子 / use道具 / status状态 / log日志 / q退出 / help帮助):")

    def show_status(self):
        """显示详细状态"""
        p1 = self.state.player1
        p2 = self.state.player2

        print("═════════════════════════════════")
        print("📊 游戏状态")
        print("═════════════════════════════════")
        print(f"回合：{self.state.turn}")
        print(f"\n🟦 你：")
        print(f"  位置：格 {p1.position}/{BOARD_SIZE}")
        print(f"  金币：{p1.coins}")
        print(f"  护盾：{'有' if p1.shield else '无'}")
        print(f"  暂停：{'是' if p1.skip_turn else '否'}")
        print(f"\n🟥 菲菲：")
        print(f"  位置：格 {p2.position}/{BOARD_SIZE}")
        print(f"  金币：{p2.coins}")
        print(f"  护盾：{'有' if p2.shield else '无'}")
        print(f"  暂停：{'是' if p2.skip_turn else '否'}")

        print(f"\n🛒 道具商店：")
        for item, info in ITEMS.items():
            print(f"  {info['name']}：{info['cost']}金币 - {info['desc']}")

        print(f"\n🗺️ 棋盘事件：")
        for i in range(1, BOARD_SIZE):
            event = self.state.board_events[i]
            print(f"  格{i}: {EVENT_NAMES[event]}")

        print("\n═════════════════════════════════")
        input("按回车返回...")

    def show_log(self):
        """显示游戏日志"""
        print("═════════════════════════════════")
        print("📜 游戏日志")
        print("═════════════════════════════════")
        for log in self.state.game_log[-15:]:
            print(f"  {log}")
        print("═════════════════════════════════")
        input("按回车返回...")

    def show_help(self):
        """显示帮助"""
        print("═════════════════════════════════")
        print("📖 游戏帮助")
        print("═════════════════════════════════")
        print("基本命令：")
        print("  roll    - 掷骰子前进")
        print("  use     - 使用道具")
        print("  status  - 查看详细状态")
        print("  log     - 查看游戏日志")
        print("  help    - 显示帮助")
        print("  q       - 退出游戏")
        print("\n道具使用：")
        print("  use rocket  - 使用火箭(3金币)")
        print("\n格子事件：")
        for event, name in EVENT_NAMES.items():
            print(f"  {name}: {EVENT_DESC[event]}")
        print("\n胜利条件：")
        print("  先到达或超过第10格者获胜")
        print("═════════════════════════════════")
        input("按回车返回...")

    def buy_item(self, player: Player, item: str) -> str:
        """购买道具"""
        if item not in ITEMS:
            return f"❓ 未知道具: {item}"

        cost = ITEMS[item]["cost"]
        if player.coins < cost:
            return f"💸 金币不足！需要{cost}金币，当前{player.coins}金币"

        if item == "shield":
            if player.shield:
                return "🛡️ 已有护盾"
            player.coins -= cost
            player.shield = True
            msg = f"{player.icon}{player.name}购买🛡️护盾！"
            self.state.game_log.append(msg)
            return msg

        return "请在回合中使用道具"

    def run(self):
        """主游戏循环"""
        last_action = ""

        while True:
            self.render(last_action)
            last_action = ""

            # 检查游戏结束
            if self.state.winner:
                print(f"\n🎊 游戏结束！{self.state.winner}获胜！")
                print("是否重新开始？(y/n):", end=" ")
                if input().lower() == "y":
                    os.remove(SAVE_FILE)
                    self.state = self.load_or_create_game()
                    continue
                else:
                    break

            cmd = input("> ").strip().lower()

            if cmd == "q":
                print("保存游戏并退出...")
                self.save_game()
                break
            elif cmd == "roll":
                last_action = self.execute_roll()
            elif cmd == "status":
                self.show_status()
            elif cmd == "log":
                self.show_log()
            elif cmd == "help":
                self.show_help()
            elif cmd == "use rocket":
                last_action = self.execute_use_item("rocket")
            elif cmd == "buy shield":
                player = self.get_current_player()
                last_action = self.buy_item(player, "shield")
                self.save_game()
            elif cmd.startswith("use "):
                item = cmd[4:].strip()
                last_action = self.execute_use_item(item)
            elif cmd.startswith("buy "):
                item = cmd[4:].strip()
                player = self.get_current_player()
                last_action = self.buy_item(player, item)
                self.save_game()
            else:
                last_action = "❓ 未知命令，输入 help 查看帮助"


def main():
    """主函数"""
    print("🎲 菲菲大富翁")
    print("=" * 30)
    print("正在加载游戏...")

    game = MonopolyGame()
    game.run()


if __name__ == "__main__":
    main()
