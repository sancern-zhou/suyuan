#!/usr/bin/env python3
"""
《地牢探险》—— 回合制文字RPG
适合"消息中间人"模式：每次通过命令行参数执行一个操作，游戏状态保存在文件中。

用法：
    python3 dungeon.py --new          # 开始新游戏
    python3 dungeon.py --status       # 查看当前状态
    python3 dungeon.py --move up      # 向上移动
    python3 dungeon.py --move down    # 向下移动
    python3 dungeon.py --move left    # 向左移动
    python3 dungeon.py --move right   # 向右移动
    python3 dungeon.py --help         # 查看帮助
"""

import json
import os
import random
import sys

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_state.json")

# 地图符号
SYM_UNEXPLORED = "?"
SYM_EMPTY = "·"
SYM_MONSTER = "M"
SYM_TREASURE = "$"
SYM_EXIT = "E"
SYM_PLAYER = "@"
SYM_VISITED = "·"  # 已探索的空地

# 方向
DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

# 地图大小
MAP_SIZE = 3


def create_map():
    """生成随机3x3地图，保证有出口和至少一个怪物"""
    cells = [SYM_EMPTY] * 9

    # 放置出口（随机位置，不在(0,0)）
    exit_pos = random.randint(1, 8)
    cells[exit_pos] = SYM_EXIT

    # 放置怪物（1-2个，不与出口重叠）
    monster_count = random.randint(1, 2)
    monster_positions = random.sample(
        [i for i in range(9) if i != exit_pos and i != 0],
        monster_count
    )
    for pos in monster_positions:
        cells[pos] = SYM_MONSTER

    # 放置宝箱（1个，不与出口和怪物重叠）
    treasure_positions = [i for i in range(9) if i != exit_pos and i not in monster_positions and i != 0]
    if treasure_positions:
        treasure_pos = random.choice(treasure_positions)
        cells[treasure_pos] = SYM_TREASURE

    # 转换为3x3网格
    grid = [cells[i * MAP_SIZE:(i + 1) * MAP_SIZE] for i in range(MAP_SIZE)]
    return grid


def new_game():
    """初始化新游戏"""
    grid = create_map()
    state = {
        "player": {"x": 0, "y": 0},
        "hp": 20,
        "max_hp": 20,
        "atk": 5,
        "gold": 0,
        "grid": grid,
        "explored": {(0, 0)},  # 起始点已探索
        "monsters_defeated": 0,
        "game_over": False,
        "won": False,
        "message": "欢迎来到地牢！找到出口(E)即可通关。"
    }
    save_state(state)
    return state


def load_state():
    """从文件加载游戏状态"""
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    """保存游戏状态到文件"""
    # 将explored集合转为列表以便JSON序列化
    state_copy = state.copy()
    state_copy["explored"] = [list(pos) for pos in state["explored"]]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_copy, f, ensure_ascii=False, indent=2)


def load_state_with_set():
    """加载状态并将explored恢复为set"""
    state = load_state()
    if state:
        state["explored"] = {tuple(pos) for pos in state["explored"]}
    return state


def render_map(state):
    """渲染ASCII地图"""
    grid = state["grid"]
    explored = state["explored"]
    px, py = state["player"]["x"], state["player"]["y"]

    lines = []
    lines.append("┌───┬───┬───┐")
    for y in range(MAP_SIZE):
        row_cells = []
        for x in range(MAP_SIZE):
            if x == px and y == py:
                row_cells.append(f" {SYM_PLAYER} ")
            elif (x, y) in explored:
                cell = grid[y][x]
                row_cells.append(f" {cell} ")
            else:
                row_cells.append(f" {SYM_UNEXPLORED} ")
        lines.append("│" + "│".join(row_cells) + "│")
        if y < MAP_SIZE - 1:
            lines.append("├───┼───┼───┤")
    lines.append("└───┴───┴───┘")

    # 图例
    lines.append("")
    lines.append(f"  {SYM_PLAYER}=你  {SYM_EXIT}=出口  {SYM_MONSTER}=怪物  {SYM_TREASURE}=宝箱  {SYM_UNEXPLORED}=未探索  {SYM_EMPTY}=空地")

    return "\n".join(lines)


def render_status(state):
    """渲染状态信息"""
    hp_bar_len = 10
    hp_ratio = state["hp"] / state["max_hp"]
    filled = int(hp_bar_len * hp_ratio)
    hp_bar = "█" * filled + "░" * (hp_bar_len - filled)

    lines = [
        "═══════════════════════════════════",
        f"  ❤️  HP: {state['hp']}/{state['max_hp']}  [{hp_bar}]",
        f"  ⚔️  攻击力: {state['atk']}",
        f"  💰 金币: {state['gold']}",
        f"  👾 已击败怪物: {state['monsters_defeated']}",
        f"  📍 位置: ({state['player']['x']}, {state['player']['y']})",
        "═══════════════════════════════════",
    ]
    return "\n".join(lines)


def handle_move(state, direction):
    """处理移动"""
    if state["game_over"]:
        return state, "游戏已结束！输入 --new 重新开始。"

    dx, dy = DIRECTIONS.get(direction)
    if dx is None:
        return state, f"无效方向：{direction}，可用：up/down/left/right"

    px, py = state["player"]["x"], state["player"]["y"]
    nx, ny = px + dx, py + dy

    # 边界检查
    if nx < 0 or nx >= MAP_SIZE or ny < 0 or ny >= MAP_SIZE:
        return state, "🛑 前方是墙壁，无法通过！"

    # 移动玩家
    state["player"]["x"] = nx
    state["player"]["y"] = ny
    state["explored"].add((nx, ny))

    cell = state["grid"][ny][nx]
    messages = [f"你移动到了 ({nx}, {ny})"]

    if cell == SYM_EXIT:
        state["won"] = True
        state["game_over"] = True
        messages.append("🎉🎉🎉 你找到了出口！通关成功！🎉🎉🎉")
        messages.append(f"最终战绩：金币 {state['gold']}，击败怪物 {state['monsters_defeated']} 只")
        save_state(state)
        return state, "\n".join(messages)

    elif cell == SYM_MONSTER:
        result = handle_combat(state)
        messages.append(result)
        # 战斗后格子变为已探索空地
        state["grid"][ny][nx] = SYM_VISITED

    elif cell == SYM_TREASURE:
        gold_found = random.randint(5, 15)
        state["gold"] += gold_found
        state["grid"][ny][nx] = SYM_VISITED
        messages.append(f"💎 你发现了一个宝箱！获得 {gold_found} 金币！")

    elif cell == SYM_EMPTY or cell == SYM_VISITED:
        messages.append("这里什么也没有。继续前进吧。")

    # 检查是否死亡
    if state["hp"] <= 0:
        state["game_over"] = True
        messages.append("💀 你倒在了地牢中...游戏结束！输入 --new 重新开始。")

    save_state(state)
    return state, "\n".join(messages)


def handle_combat(state):
    """处理战斗，返回战斗描述"""
    monster_hp = random.randint(10, 20)
    monster_atk = random.randint(3, 7)
    monster_name = random.choice(["哥布林", "骷髅兵", "蝙蝠怪", "史莱姆", "地精"])
    
    lines = [f"⚔️ 遭遇 {monster_name}！(HP:{monster_hp} ATK:{monster_atk})"]
    
    turn = 1
    while monster_hp > 0 and state["hp"] > 0:
        # 玩家攻击
        player_dmg = max(1, state["atk"] + random.randint(-2, 3))
        monster_hp -= player_dmg
        lines.append(f"  ▶ 回合{turn}：你造成 {player_dmg} 点伤害！怪物剩余 HP:{max(0, monster_hp)}")
        
        if monster_hp <= 0:
            gold_reward = random.randint(3, 8)
            state["gold"] += gold_reward
            state["monsters_defeated"] += 1
            lines.append(f"  ✅ 击败了{monster_name}！获得 {gold_reward} 金币！")
            break
        
        # 怪物反击
        monster_dmg = max(1, monster_atk + random.randint(-2, 2))
        state["hp"] -= monster_dmg
        lines.append(f"  ◀ 回合{turn}：{monster_name}反击造成 {monster_dmg} 点伤害！你剩余 HP:{max(0, state['hp'])}")
        
        turn += 1
    
    return "\n".join(lines)


def cmd_new():
    """处理 --new 命令"""
    state = new_game()
    output = [
        "🏰═══════════════════════════════🏰",
        "        《地牢探险》",
        "  在3x3地牢中找到出口(E)！",
        "🏰═══════════════════════════════🏰",
        "",
        render_map(state),
        "",
        render_status(state),
        "",
        f"📖 {state['message']}",
        "",
        "💡 使用 --move up/down/left/right 移动",
    ]
    return "\n".join(output)


def cmd_status():
    """处理 --status 命令"""
    state = load_state_with_set()
    if state is None:
        return "❌ 没有进行中的游戏。使用 --new 开始新游戏。"
    
    output = [
        render_map(state),
        "",
        render_status(state),
    ]
    
    if state["game_over"]:
        if state["won"]:
            output.append("")
            output.append("🎉 恭喜通关！使用 --new 再来一次。")
        else:
            output.append("")
            output.append("💀 你已阵亡。使用 --new 重新开始。")
    
    return "\n".join(output)


def cmd_move(direction):
    """处理 --move 命令"""
    state = load_state_with_set()
    if state is None:
        return "❌ 没有进行中的游戏。使用 --new 开始新游戏。"
    
    state, message = handle_move(state, direction)
    
    output = [
        render_map(state),
        "",
        render_status(state),
        "",
        f"📖 {message}",
    ]
    return "\n".join(output)


def cmd_help():
    """显示帮助信息"""
    return """🏰═══════════════════════════════🏰
        《地牢探险》- 帮助
🏰═══════════════════════════════🏰

📋 命令列表：
  python3 dungeon.py --new             开始新游戏
  python3 dungeon.py --status          查看当前状态
  python3 dungeon.py --move up         向上移动
  python3 dungeon.py --move down       向下移动
  python3 dungeon.py --move left       向左移动
  python3 dungeon.py --move right      向右移动
  python3 dungeon.py --help            显示此帮助

🎮 游戏规则：
  • 3x3 地牢，找到出口(E)即可通关
  • 遇到怪物(M)会自动进入战斗
  • 宝箱($)可获得金币
  • 未探索区域显示为 ?
  • 你在地图上显示为 @

💡 提示：
  适合通过微信等聊天工具发送指令，
  由中间人/助理代为操作。
"""


def main():
    if len(sys.argv) < 2:
        print(cmd_help())
        return

    command = sys.argv[1]

    if command == "--new":
        print(cmd_new())
    elif command == "--status":
        print(cmd_status())
    elif command == "--move":
        if len(sys.argv) < 3:
            print("❌ 请指定方向：up/down/left/right")
            return
        direction = sys.argv[2]
        print(cmd_move(direction))
    elif command == "--help":
        print(cmd_help())
    else:
        print(f"❌ 未知命令：{command}")
        print("使用 --help 查看帮助")


if __name__ == "__main__":
    main()
