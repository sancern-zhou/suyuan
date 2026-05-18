#!/usr/bin/env python3
"""
《菲菲探险记》—— 文字冒险探索游戏
一个异步回合制的文字冒险游戏，适合通过"消息中间人"模式游玩
"""

import json
import random
import sys
import os
from datetime import datetime
from pathlib import Path
from argparse import ArgumentParser

# 游戏配置
SAVE_DIR = Path("/home/xckj/suyuan/games/saves")
MAP_SIZE = 5
MAX_HP = 100

# 地图元素类型
TILE_TYPES = {
    "empty": {"emoji": "⬜", "name": "空地", "desc": "一片开阔的空地"},
    "forest": {"emoji": "🌲", "name": "森林", "desc": "茂密的森林，可能隐藏着秘密"},
    "river": {"emoji": "🌊", "name": "河流", "desc": "湍急的河流，无法直接通过"},
    "cave": {"emoji": "⛰️", "name": "山洞", "desc": "神秘的山洞，里面可能藏着宝物"},
    "chest": {"emoji": "📦", "name": "宝箱", "desc": "传说中的宝藏箱！"}
}

# 随机事件
FOREST_EVENTS = [
    {"text": "你走进森林，遇到了一只友好的松鼠。它吱吱叫着指向北方，似乎在暗示什么。", "effect": "hint_north"},
    {"text": "你在森林里发现了美味的浆果！生命值 +15", "effect": "heal", "value": 15},
    {"text": "森林里很安静，你收集了一些干树枝。物品：干树枝", "effect": "item", "item": "干树枝"},
    {"text": "一阵风吹过，树叶沙沙作响，你感到一丝不安...", "effect": "nothing"},
]

RIVER_EVENTS = [
    {"text": "你试图渡河，但水流太急了！被水蛭咬了一口。生命值 -10", "effect": "damage", "value": 10},
    {"text": "你在河边发现了一只破旧的小船！物品：小船", "effect": "item", "item": "小船"},
    {"text": "河水清澈见底，你看到了一些闪闪发光的东西...但够不着。", "effect": "nothing"},
]

CAVE_EVENTS = [
    {"text": "你在山洞里发现了一袋金币！物品：金币袋", "effect": "item", "item": "金币袋"},
    {"text": "突然！一群蝙蝠飞出来！生命值 -5", "effect": "damage", "value": 5},
    {"text": "墙上刻着古老的文字：'宝藏在流水的东方...' 似乎是一个线索！", "effect": "hint_east"},
    {"text": "山洞里空空如也，只有一些蝙蝠粪便。", "effect": "nothing"},
]

EMPTY_EVENTS = [
    {"text": "这里什么都没有，只有风吹过的声音。", "effect": "nothing"},
    {"text": "你发现了一个脚印，看起来已经很久了。", "effect": "nothing"},
    {"text": "天空很蓝，你继续前进。", "effect": "nothing"},
]


class AdventureGame:
    """冒险游戏核心类"""

    def __init__(self):
        self.game_id = None
        self.player_name = None
        self.hp = MAX_HP
        self.steps = 0
        self.items = []
        self.position = {"x": 0, "y": 0}
        self.explored = set()
        self.map = []
        self.game_over = False
        self.victory = False
        self.created_at = None
        self.last_action = None

    def generate_map(self):
        """生成随机地图，确保每个角落都有路径可到达"""
        # 创建空地图
        self.map = [[{"type": "empty", "revealed": False} for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]

        # 随机放置地形（约30%森林，15%河流，10%山洞）
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                if (x, y) == (0, 0):  # 起始点
                    continue
                roll = random.random()
                if roll < 0.30:
                    self.map[y][x]["type"] = "forest"
                elif roll < 0.45:
                    self.map[y][x]["type"] = "river"
                elif roll < 0.55:
                    self.map[y][x]["type"] = "cave"

        # 确保起点周围不是河流（避免开局被困）
        for dx, dy in [(0, 1), (1, 0), (1, 1)]:
            if dx < MAP_SIZE and dy < MAP_SIZE:
                if self.map[dy][dx]["type"] == "river":
                    self.map[dy][dx]["type"] = random.choice(["empty", "forest"])

        # 放置宝箱（在离起点较远的位置）
        while True:
            cx, cy = random.randint(2, MAP_SIZE-1), random.randint(2, MAP_SIZE-1)
            if self.map[cy][cx]["type"] != "river":
                self.map[cy][cx]["type"] = "chest"
                break

        # 标记起始点为已探索
        self.explored.add((0, 0))
        self.map[0][0]["revealed"] = True

    def save(self):
        """保存游戏状态"""
        data = {
            "game_id": self.game_id,
            "player_name": self.player_name,
            "hp": self.hp,
            "steps": self.steps,
            "items": self.items,
            "position": self.position,
            "explored": list(self.explored),
            "map": self.map,
            "game_over": self.game_over,
            "victory": self.victory,
            "created_at": self.created_at,
            "last_action": datetime.now().isoformat()
        }
        save_path = SAVE_DIR / f"{self.game_id}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, game_id):
        """加载游戏状态"""
        save_path = SAVE_DIR / f"{game_id}.json"
        if not save_path.exists():
            return None

        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        game = cls()
        game.game_id = data["game_id"]
        game.player_name = data["player_name"]
        game.hp = data["hp"]
        game.steps = data["steps"]
        game.items = data["items"]
        game.position = data["position"]
        game.explored = set(tuple(e) for e in data["explored"])
        game.map = data["map"]
        game.game_over = data["game_over"]
        game.victory = data["victory"]
        game.created_at = data["created_at"]
        game.last_action = data.get("last_action")
        return game

    def get_current_tile(self):
        """获取当前位置的格子信息"""
        return self.map[self.position["y"]][self.position["x"]]

    def can_move(self, direction):
        """检查是否可以向某个方向移动"""
        x, y = self.position["x"], self.position["y"]

        if direction == "up":
            y -= 1
        elif direction == "down":
            y += 1
        elif direction == "left":
            x -= 1
        elif direction == "right":
            x += 1
        else:
            return False, "无效的方向"

        if not (0 <= x < MAP_SIZE and 0 <= y < MAP_SIZE):
            return False, "那边是世界的边缘，无法前进！"

        target_tile = self.map[y][x]

        # 河流检查
        if target_tile["type"] == "river":
            if "小船" in self.items:
                return True, "你乘坐小船渡过了河流！"
            else:
                return False, "前方是湍急的河流，没有船无法通过！"

        return True, ""

    def move(self, direction):
        """移动玩家"""
        if self.game_over:
            return "游戏已结束，请开始新游戏。"

        can_move, message = self.can_move(direction)
        if not can_move:
            return f"❌ {message}"

        # 更新位置
        if direction == "up":
            self.position["y"] -= 1
        elif direction == "down":
            self.position["y"] += 1
        elif direction == "left":
            self.position["x"] -= 1
        elif direction == "right":
            self.position["x"] += 1

        self.steps += 1

        # 标记为已探索
        self.position_tuple = (self.position["x"], self.position["y"])
        self.explored.add(self.position_tuple)
        self.map[self.position["y"]][self.position["x"]]["revealed"] = True

        # 触发事件
        tile = self.get_current_tile()
        result = self.trigger_event(tile)

        # 检查胜利条件
        if tile["type"] == "chest":
            self.victory = True
            self.game_over = True
            result += "\n\n🎉🎉🎉 恭喜！你找到了传说中的宝藏！🎉🎉🎉"
            result += f"\n总步数：{self.steps} | 剩余生命：{self.hp}"

        # 检查失败条件
        if self.hp <= 0:
            self.game_over = True
            self.victory = False
            result += "\n\n💀 你倒下了...探险到此结束。"

        self.save()
        return result

    def trigger_event(self, tile):
        """触发格子事件"""
        tile_info = TILE_TYPES[tile["type"]]
        result = f"\n你来到了 {tile_info['emoji']} {tile_info['name']}\n"
        result += f"{tile_info['desc']}\n"

        if tile["type"] == "empty":
            event = random.choice(EMPTY_EVENTS)
        elif tile["type"] == "forest":
            event = random.choice(FOREST_EVENTS)
        elif tile["type"] == "river":
            event = random.choice(RIVER_EVENTS)
        elif tile["type"] == "cave":
            event = random.choice(CAVE_EVENTS)
        elif tile["type"] == "chest":
            return result + "你小心翼翼地打开宝箱..."

        result += f"\n{event['text']}"

        # 应用事件效果
        if event["effect"] == "heal":
            self.hp = min(MAX_HP, self.hp + event["value"])
        elif event["effect"] == "damage":
            self.hp -= event["value"]
            result += f"\n当前生命值：{self.hp}"
        elif event["effect"] == "item":
            if event["item"] not in self.items:
                self.items.append(event["item"])

        return result

    def render_map(self):
        """渲染地图"""
        result = "\n🗺️ 探险地图 🗺️\n\n"
        result += "   " + " ".join(str(i) for i in range(MAP_SIZE)) + "\n"

        for y in range(MAP_SIZE):
            result += f"{y}  "
            for x in range(MAP_SIZE):
                tile = self.map[y][x]
                px, py = self.position["x"], self.position["y"]

                # 显示玩家位置
                if x == px and y == py:
                    result += "🧑 "
                # 显示已探索的格子
                elif tile["revealed"]:
                    result += TILE_TYPES[tile["type"]]["emoji"] + " "
                # 未探索的格子
                else:
                    result += "⬛ "
            result += "\n"

        result += "\n图例：🧑玩家 🌲森林 🌊河流 ⛰️山洞 📦宝箱 ⬜空地 ⬛未探索"
        return result

    def get_status(self):
        """获取游戏状态"""
        if self.victory:
            status_icon = "🏆"
            status_text = "胜利！"
        elif self.hp <= 0:
            status_icon = "💀"
            status_text = "失败"
        elif self.game_over:
            status_icon = "⏹️"
            status_text = "已结束"
        else:
            status_icon = "🎮"
            status_text = "进行中"

        result = f"\n📊 游戏状态 - {self.player_name} {status_icon}\n"
        result += f"状态：{status_text}\n"
        result += f"生命值：{'❤️' * (self.hp // 20)}{'🖤' * (5 - self.hp // 20)} ({self.hp}/{MAX_HP})\n"
        result += f"步数：{self.steps}\n"
        result += f"位置：({self.position['x']}, {self.position['y']})\n"

        if self.items:
            result += f"物品：{' '.join(f'🎒{i}' for i in self.items)}\n"
        else:
            result += "物品：空空如也\n"

        tile = self.get_current_tile()
        result += f"当前位置：{TILE_TYPES[tile['type']]['emoji']} {TILE_TYPES[tile['type']]['name']}\n"

        if not self.game_over:
            result += f"\n已探索：{len(self.explored)}/{MAP_SIZE * MAP_SIZE} 个区域"

        return result

    def render_full_status(self):
        """渲染完整状态（地图+状态）"""
        return self.render_map() + "\n" + self.get_status()


def new_game(player_name):
    """开始新游戏"""
    game = AdventureGame()
    game.player_name = player_name
    game.game_id = f"adv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
    game.hp = MAX_HP
    game.steps = 0
    game.items = []
    game.position = {"x": 0, "y": 0}
    game.explored = set()
    game.game_over = False
    game.victory = False
    game.created_at = datetime.now().isoformat()

    game.generate_map()
    game.save()

    result = f"\n🏝️ 《菲菲探险记》🏝️\n"
    result += f"欢迎来到神秘岛屿，{player_name}！\n"
    result += f"游戏ID：{game.game_id}\n"
    result += f"目标：找到传说中的宝藏箱 📦\n"
    result += f"操作：上下左右移动，探索岛屿，小心危险！\n"

    result += game.render_full_status()

    result += f"\n💡 提示：保存好游戏ID [{game.game_id}]，后续操作需要使用！"

    return result


def show_status(game_id):
    """显示游戏状态"""
    game = AdventureGame.load(game_id)
    if not game:
        return f"❌ 找不到游戏 [{game_id}]，请检查游戏ID是否正确。"

    return game.render_full_status()


def move_player(game_id, direction):
    """移动玩家"""
    game = AdventureGame.load(game_id)
    if not game:
        return f"❌ 找不到游戏 [{game_id}]，请检查游戏ID是否正确。"

    direction_map = {
        "up": "⬆️ 上",
        "down": "⬇️ 下",
        "left": "⬅️ 左",
        "right": "➡️ 右",
        "w": "⬆️ 上",
        "s": "⬇️ 下",
        "a": "⬅️ 左",
        "d": "➡️ 右",
    }

    dir_name = direction_map.get(direction, direction)
    result = f"\n🚶 向{dir_name}移动..."
    result += game.move(direction)
    result += "\n" + game.render_full_status()

    return result


def show_map(game_id):
    """显示地图"""
    game = AdventureGame.load(game_id)
    if not game:
        return f"❌ 找不到游戏 [{game_id}]，请检查游戏ID是否正确。"

    return game.render_map()


def list_games():
    """列出所有存档"""
    save_files = list(SAVE_DIR.glob("adv_*.json"))
    if not save_files:
        return "\n📁 暂无存档，使用 --new 开始新游戏！"

    result = "\n📁 存档列表 📁\n\n"

    games = []
    for sf in save_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
            games.append({
                "id": sf.stem,
                "name": data.get("player_name", "未知"),
                "status": "🏆胜利" if data.get("victory") else ("💀失败" if data.get("hp", 0) <= 0 else "🎮进行中"),
                "steps": data.get("steps", 0),
                "hp": data.get("hp", 0),
                "date": data.get("created_at", "")[:10]
            })
        except:
            pass

    for g in sorted(games, key=lambda x: x["date"], reverse=True)[:10]:
        result += f"[{g['id']}] {g['name']} - {g['status']} (步数:{g['steps']} 生命:{g['hp']})\n"

    return result


def main():
    parser = ArgumentParser(description="《菲菲探险记》文字冒险游戏")
    parser.add_argument("--new", metavar="名字", help="开始新游戏")
    parser.add_argument("--status", metavar="游戏ID", help="查看游戏状态")
    parser.add_argument("--move", nargs=2, metavar=("游戏ID", "方向"), help="移动 (up/down/left/right)")
    parser.add_argument("--map", metavar="游戏ID", help="查看地图")
    parser.add_argument("--list", action="store_true", help="列出所有存档")

    args = parser.parse_args()

    if args.new:
        print(new_game(args.new))
    elif args.status:
        print(show_status(args.status))
    elif args.move:
        print(move_player(args.move[0], args.move[1]))
    elif args.map:
        print(show_map(args.map))
    elif args.list:
        print(list_games())
    else:
        parser.print_help()
        print("\n📖 快速开始：")
        print("  python3 adventure.py --new 菲菲")
        print("  python3 adventure.py --move adv_xxx up")
        print("  python3 adventure.py --status adv_xxx")


if __name__ == "__main__":
    main()
