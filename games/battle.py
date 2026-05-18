#!/usr/bin/env python3
"""
菲菲战棋 - 双人回合制对战游戏
适合微信消息中间人模式
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ==================== 配置 ====================
SAVE_DIR = Path("/home/xckj/suyuan/games/saves")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

BOARD_SIZE = 5

# 地形类型
TERRAIN_EMPTY = "empty"
TERRAIN_FOREST = "forest"
TERRAIN_ROCK = "rock"

# 地形显示
TERRAIN_ICONS = {
    TERRAIN_EMPTY: "⬜",
    TERRAIN_FOREST: "🌲",
    TERRAIN_ROCK: "⛰️",
}

# 玩家图标
PLAYER_ICONS = {
    "player1": "🟦",  # 你的棋子
    "player2": "🟥",  # 菲菲的棋子
}

# 基地图标
BASE_ICONS = {
    (0, 0): "🏠",   # 你的基地
    (4, 4): "🏰",   # 菲菲的基地
}

# 道具
ITEM_ICONS = {
    "sword": "⚔️",
    "shield": "🛡️",
}

# ==================== 游戏类 ====================
class BattleGame:
    def __init__(self, player1_name: str, player2_name: str = "菲菲"):
        self.player1_name = player1_name
        self.player2_name = player2_name
        self.game_id = self._generate_game_id()
        self.created_at = datetime.now().isoformat()

        # 初始化棋盘
        self.board = self._generate_board()

        # 玩家状态
        self.players = {
            "player1": {
                "name": player1_name,
                "position": [0, 0],
                "attack": 3,
                "defense": 0,
                "base": [0, 4],  # 目标基地
            },
            "player2": {
                "name": player2_name,
                "position": [4, 4],
                "attack": 3,
                "defense": 0,
                "base": [4, 0],  # 目标基地
            }
        }

        # 当前回合
        self.current_turn = "player1"
        self.turn_count = 1

        # 游戏状态
        self.status = "playing"  # playing, finished
        self.winner = None
        self.finish_reason = None

        # 移动历史
        self.move_history: List[Dict] = []

        # 森林减速状态
        self.forest_slow = {  # 谁在森林中，还需要几步才能出来
            "player1": 0,
            "player2": 0,
        }

    def _generate_game_id(self) -> str:
        """生成游戏ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=4))
        return f"battle_{timestamp}_{random_str}"

    def _generate_board(self) -> List[List[Dict]]:
        """生成随机棋盘"""
        board = []
        for y in range(BOARD_SIZE):
            row = []
            for x in range(BOARD_SIZE):
                # 基地位置是空地
                if (x, y) in [(0, 0), (4, 4)]:
                    cell = {"terrain": TERRAIN_EMPTY, "item": None}
                else:
                    # 随机生成地形
                    rand = random.random()
                    if rand < 0.15:
                        terrain = TERRAIN_FOREST
                    elif rand < 0.25:
                        terrain = TERRAIN_ROCK
                    else:
                        terrain = TERRAIN_EMPTY

                    # 随机生成道具（仅空地）
                    item = None
                    if terrain == TERRAIN_EMPTY:
                        item_rand = random.random()
                        if item_rand < 0.08:
                            item = "sword"
                        elif item_rand < 0.16:
                            item = "shield"

                    cell = {"terrain": terrain, "item": item}
                row.append(cell)
            board.append(row)

        # 确保起点周围至少有一条路
        self._ensure_path(board)
        return board

    def _ensure_path(self, board: List[List[Dict]]):
        """确保至少有一条路径可以到达对方基地"""
        # 简单处理：如果起点被完全封死，移除一些岩石
        start_positions = [(0, 0), (4, 4)]
        for x, y in start_positions:
            blocked = True
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                    if board[ny][nx]["terrain"] != TERRAIN_ROCK:
                        blocked = False
                        break

            if blocked:
                # 移除一个相邻的岩石
                for dx, dy in [(0, 1), (1, 0)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                        if board[ny][nx]["terrain"] == TERRAIN_ROCK:
                            board[ny][nx]["terrain"] = TERRAIN_EMPTY
                            break

    def get_cell(self, x: int, y: int) -> Optional[Dict]:
        """获取格子信息"""
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            return self.board[y][x]
        return None

    def render_board(self, show_hidden: bool = True) -> str:
        """渲染棋盘"""
        lines = []

        # 获取双方位置
        p1_pos = tuple(self.players["player1"]["position"])
        p2_pos = tuple(self.players["player2"]["position"])

        # 列号
        lines.append("   0   1   2   3   4")
        lines.append("  " + "─" * 21)

        for y in range(BOARD_SIZE):
            row_parts = [f"{y}│"]
            for x in range(BOARD_SIZE):
                cell = self.board[y][x]

                # 确定显示什么
                if (x, y) == p1_pos:
                    icon = PLAYER_ICONS["player1"]
                elif (x, y) == p2_pos:
                    icon = PLAYER_ICONS["player2"]
                elif (x, y) in BASE_ICONS:
                    icon = BASE_ICONS[(x, y)]
                elif cell["item"]:
                    icon = ITEM_ICONS[cell["item"]]
                else:
                    icon = TERRAIN_ICONS[cell["terrain"]]

                row_parts.append(f" {icon} │")

            lines.append("".join(row_parts))
            if y < BOARD_SIZE - 1:
                lines.append("  " + "├" + "─┼".join(["───"] * 5) + "┤")

        lines.append("  " + "─" * 21)
        return "\n".join(lines)

    def get_player_info(self, player_key: str) -> str:
        """获取玩家信息"""
        p = self.players[player_key]
        name = p["name"]
        pos = tuple(p["position"])
        icon = PLAYER_ICONS[player_key]

        info = f"{icon} {name}"
        info += f"\n   位置: {pos}"
        info += f"\n   攻击: {p['attack']}  防御: {p['defense']}"

        return info

    def move(self, player_key: str, direction: str) -> Dict:
        """移动棋子"""
        if self.status != "playing":
            return {
                "success": False,
                "message": f"游戏已结束！获胜者: {self.winner}"
            }

        if self.current_turn != player_key:
            current_name = self.players[self.current_turn]["name"]
            return {
                "success": False,
                "message": f"现在轮到 {current_name} 行动！"
            }

        # 检查森林减速
        if self.forest_slow[player_key] > 0:
            self.forest_slow[player_key] -= 1
            self._switch_turn()
            return {
                "success": True,
                "message": "你在森林中，移动缓慢！再等一回合...",
                "slow_effect": True
            }

        # 计算新位置
        pos = self.players[player_key]["position"]
        new_pos = list(pos)

        direction_map = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
        }

        if direction not in direction_map:
            return {
                "success": False,
                "message": f"无效方向！请使用: up, down, left, right"
            }

        dx, dy = direction_map[direction]
        new_pos[0] += dx
        new_pos[1] += dy

        # 检查边界
        if not (0 <= new_pos[0] < BOARD_SIZE and 0 <= new_pos[1] < BOARD_SIZE):
            return {
                "success": False,
                "message": "无法移动到棋盘外！"
            }

        # 检查岩石
        cell = self.board[new_pos[1]][new_pos[0]]
        if cell["terrain"] == TERRAIN_ROCK:
            return {
                "success": False,
                "message": "前面是岩石⛰️，无法通过！"
            }

        # 检查是否与对方相遇
        opponent = "player2" if player_key == "player1" else "player1"
        opp_pos = tuple(self.players[opponent]["position"])

        if tuple(new_pos) == opp_pos:
            return self._battle(player_key, opponent)

        # 执行移动
        old_pos = pos
        self.players[player_key]["position"] = new_pos

        # 检查森林减速
        events = []
        if cell["terrain"] == TERRAIN_FOREST:
            self.forest_slow[player_key] = 1  # 下一回合也会被减速
            events.append("进入森林🌲，下回合移动缓慢！")

        # 检查道具
        if cell["item"]:
            item = cell["item"]
            if item == "sword":
                self.players[player_key]["attack"] += 1
                events.append("获得⚔️武器，攻击+1！")
            elif item == "shield":
                self.players[player_key]["defense"] += 1
                events.append("获得🛡️护甲，防御+1！")
            cell["item"] = None  # 移除道具

        # 检查胜利条件（到达基地）
        target_base = tuple(self.players[player_key]["base"])
        if tuple(new_pos) == target_base:
            self.status = "finished"
            self.winner = player_key
            self.finish_reason = "占领基地"

        # 记录历史
        self.move_history.append({
            "turn": self.turn_count,
            "player": player_key,
            "from": old_pos,
            "to": new_pos,
            "direction": direction,
        })

        # 切换回合
        self._switch_turn()

        result = {
            "success": True,
            "new_position": new_pos,
            "events": events,
        }

        if self.status == "finished":
            result["game_over"] = True
            result["winner"] = self.players[self.winner]["name"]
            result["reason"] = "占领对方基地！"

        return result

    def _battle(self, attacker: str, defender: str) -> Dict:
        """战斗处理"""
        att = self.players[attacker]
        defe = self.players[defender]

        # 计算战斗力
        att_power = att["attack"] + random.randint(1, 6)
        def_power = defe["attack"] + random.randint(1, 6) + defe["defense"]

        self.status = "finished"

        if att_power > def_power:
            self.winner = attacker
            self.finish_reason = "battle"
            return {
                "success": True,
                "battle": True,
                "attacker": att["name"],
                "defender": defe["name"],
                "att_power": att_power,
                "def_power": def_power,
                "winner": att["name"],
                "message": f"⚔️战斗！{att['name']}({att_power}) vs {defe['name']}({def_power})，{att['name']}获胜！"
            }
        else:
            self.winner = defender
            self.finish_reason = "battle"
            return {
                "success": True,
                "battle": True,
                "attacker": att["name"],
                "defender": defe["name"],
                "att_power": att_power,
                "def_power": def_power,
                "winner": defe["name"],
                "message": f"⚔️战斗！{att['name']}({att_power}) vs {defe['name']}({def_power})，{defe['name']}获胜！"
            }

    def _switch_turn(self):
        """切换回合"""
        if self.current_turn == "player1":
            self.current_turn = "player2"
        else:
            self.current_turn = "player1"
            self.turn_count += 1

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "game_id": self.game_id,
            "player1_name": self.player1_name,
            "player2_name": self.player2_name,
            "created_at": self.created_at,
            "board": self.board,
            "players": self.players,
            "current_turn": self.current_turn,
            "turn_count": self.turn_count,
            "status": self.status,
            "winner": self.winner,
            "finish_reason": self.finish_reason,
            "move_history": self.move_history,
            "forest_slow": self.forest_slow,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BattleGame":
        """反序列化"""
        game = cls.__new__(cls)
        game.game_id = data["game_id"]
        game.player1_name = data["player1_name"]
        game.player2_name = data["player2_name"]
        game.created_at = data["created_at"]
        game.board = data["board"]
        game.players = data["players"]
        game.current_turn = data["current_turn"]
        game.turn_count = data["turn_count"]
        game.status = data["status"]
        game.winner = data["winner"]
        game.finish_reason = data["finish_reason"]
        game.move_history = data["move_history"]
        game.forest_slow = data["forest_slow"]
        return game


# ==================== 存储管理 ====================
def save_game(game: BattleGame) -> str:
    """保存游戏"""
    filepath = SAVE_DIR / f"{game.game_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(game.to_dict(), f, ensure_ascii=False, indent=2)
    return str(filepath)


def load_game(game_id: str) -> Optional[BattleGame]:
    """加载游戏"""
    filepath = SAVE_DIR / f"{game_id}.json"
    if not filepath.exists():
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return BattleGame.from_dict(data)


def list_games() -> List[Dict]:
    """列出所有存档"""
    games = []
    for filepath in SAVE_DIR.glob("battle_*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        games.append({
            "game_id": data["game_id"],
            "player1": data["player1_name"],
            "player2": data["player2_name"],
            "status": data["status"],
            "winner": data.get("winner"),
            "turn": data["turn_count"],
            "created_at": data["created_at"],
        })
    # 按创建时间倒序
    games.sort(key=lambda x: x["created_at"], reverse=True)
    return games


# ==================== 命令处理 ====================
def cmd_new(player1_name: str, player2_name: str = "菲菲"):
    """开始新游戏"""
    game = BattleGame(player1_name, player2_name)
    save_game(game)

    print(f"\n{'═'*30}")
    print(f"🎮 菲菲战棋 - 新游戏开始！")
    print(f"{'═'*30}\n")
    print(f"📋 游戏ID: {game.game_id}")
    print(f"\n{game.render_board()}\n")
    print(f"玩家信息:")
    print(f"   {game.get_player_info('player1')}\n")
    print(f"   {game.get_player_info('player2')}\n")
    print(f"当前回合: 第{game.turn_count}回合 - {game.players[game.current_turn]['name']}")
    print(f"\n💡 提示:")
    print(f"   🏠 你的基地(0,0) → 目标(4,4)")
    print(f"   🏰 菲菲基地(4,4) → 目标(0,0)")
    print(f"   🌲森林减速  ⛰️岩石不可过  ⚔️攻击+1  🛡️防御+1")
    print(f"\n📝 移动命令: python3 battle.py --move {game.game_id} up/down/left/right")
    print(f"📝 查看状态: python3 battle.py --status {game.game_id}")


def cmd_status(game_id: str):
    """查看游戏状态"""
    game = load_game(game_id)
    if not game:
        print(f"❌ 游戏不存在: {game_id}")
        return

    print(f"\n{'═'*30}")
    print(f"📋 游戏状态 - {game.game_id}")
    print(f"{'═'*30}\n")
    print(f"{game.render_board()}\n")
    print(f"玩家信息:")
    print(f"   {game.get_player_info('player1')}\n")
    print(f"   {game.get_player_info('player2')}\n")
    print(f"当前回合: 第{game.turn_count}回合 - {game.players[game.current_turn]['name']}")

    if game.status == "finished":
        print(f"\n🏆 游戏结束！获胜者: {game.players[game.winner]['name']}")
        if game.finish_reason == "battle":
            print(f"   原因: 战斗胜利")
        else:
            print(f"   原因: 占领基地")


def cmd_move(game_id: str, direction: str, player_key: str = None):
    """移动棋子"""
    game = load_game(game_id)
    if not game:
        print(f"❌ 游戏不存在: {game_id}")
        return

    # 自动判断当前玩家
    if player_key is None:
        player_key = game.current_turn

    result = game.move(player_key, direction)
    save_game(game)

    print(f"\n{'═'*30}")
    print(f"🎮 移动: {game.players[player_key]['name']} → {direction}")
    print(f"{'═'*30}\n")

    if not result["success"]:
        print(f"❌ {result['message']}\n")
        print(f"{game.render_board()}\n")
        print(f"当前回合: {game.players[game.current_turn]['name']}")
        return

    if result.get("battle"):
        print(f"{result['message']}\n")
        print(f"{game.render_board()}\n")
        print(f"🏆 {game.players[game.winner]['name']} 获胜！")
        return

    if result.get("slow_effect"):
        print(f"⏸️ {result['message']}\n")
        print(f"{game.render_board()}\n")
        next_player = game.players[game.current_turn]["name"]
        print(f"当前回合: 第{game.turn_count}回合 - {next_player}")
        return

    print(f"{game.render_board()}\n")

    # 显示事件
    if result.get("events"):
        for event in result["events"]:
            print(f"   {event}")
        print()

    # 显示玩家信息
    print(f"玩家信息:")
    print(f"   {game.get_player_info('player1')}\n")
    print(f"   {game.get_player_info('player2')}\n")

    if result.get("game_over"):
        print(f"🏆 游戏结束！{result['winner']} {result['reason']}")
    else:
        next_player = game.players[game.current_turn]["name"]
        print(f"当前回合: 第{game.turn_count}回合 - {next_player}")


def cmd_list():
    """列出所有存档"""
    games = list_games()

    if not games:
        print(f"\n📭 暂无存档")
        return

    print(f"\n{'═'*50}")
    print(f"📋 存档列表 (共{len(games)}个)")
    print(f"{'═'*30}\n")

    for i, game in enumerate(games, 1):
        status_icon = "✅" if game["status"] == "finished" else "🎮"
        winner_info = f" → {game['winner']}" if game["winner"] else ""
        print(f"{i}. {status_icon} {game['game_id']}")
        print(f"   {game['player1']} vs {game['player2']}{winner_info}")
        print(f"   回合: {game['turn']}  状态: {game['status']}")
        print()


# ==================== 主程序 ====================
def main():
    parser = argparse.ArgumentParser(
        description="菲菲战棋 - 双人回合制对战",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 battle.py --new "小明" "菲菲"
  python3 battle.py --status battle_20260510_1234_abc1
  python3 battle.py --move battle_20260510_1234_abc1 up
  python3 battle.py --list
        """
    )

    parser.add_argument("--new", nargs="+", metavar=("NAME1", "NAME2"),
                        help="开始新游戏，指定两个玩家名字")
    parser.add_argument("--status", metavar="GAME_ID",
                        help="查看游戏状态")
    parser.add_argument("--move", nargs=2, metavar=("GAME_ID", "DIRECTION"),
                        help=["移动棋子 (up/down/left/right)"])
    parser.add_argument("--list", action="store_true",
                        help="列出所有存档")

    args = parser.parse_args()

    if args.new:
        player1 = args.new[0]
        player2 = args.new[1] if len(args.new) > 1 else "菲菲"
        cmd_new(player1, player2)

    elif args.status:
        cmd_status(args.status)

    elif args.move:
        game_id, direction = args.move
        cmd_move(game_id, direction.lower())

    elif args.list:
        cmd_list()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
