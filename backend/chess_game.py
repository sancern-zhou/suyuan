#!/usr/bin/env python3
"""
菲菲战棋 - 双人回合制对战游戏
5x5 棋盘，双人轮流移动，目标是占领对方基地或消灭对方。
"""

import json
import os
import random
import sys
import time

# 游戏状态文件路径
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_state.json")

# Unicode 符号
EMPTY = "⬜"       # 空地
FOREST = "🌲"      # 森林（减速）
ROCK = "⛰️"        # 岩石（不可通行）
BASE_P1 = "🏠"     # 玩家1基地（左上）
BASE_P2 = "🏰"     # 玩家2基地（右下）
PLAYER1 = "🟦"     # 蓝色棋子
PLAYER2 = "🟥"     # 红色棋子
PLAYER1_BASE = "🔵"  # 玩家1在基地
PLAYER2_BASE = "🔴"  # 玩家2在基地

# 棋盘大小
BOARD_SIZE = 5

# 方向映射
DIRECTIONS = {
    "w": (-1, 0),  # 上
    "s": (1, 0),   # 下
    "a": (0, -1),  # 左
    "d": (0, 1),   # 右
}

DIR_NAMES = {
    "w": "上",
    "s": "下",
    "a": "左",
    "d": "右",
}


def create_initial_state():
    """创建初始游戏状态"""
    # 生成地形（5x5网格）
    terrain = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

    # 随机放置地形（避开基地位置）
    for i in range(BOARD_SIZE):
        for j in range(BOARD_SIZE):
            if (i == 0 and j == 0) or (i == BOARD_SIZE - 1 and j == BOARD_SIZE - 1):
                continue  # 基地位置不放地形
            r = random.random()
            if r < 0.5:
                terrain[i][j] = EMPTY
            elif r < 0.75:
                terrain[i][j] = FOREST
            else:
                terrain[i][j] = ROCK

    state = {
        "terrain": terrain,
        "player1": {"pos": [0, 0], "hp": 5, "attack": 3, "name": "你"},
        "player2": {"pos": [BOARD_SIZE - 1, BOARD_SIZE - 1], "hp": 5, "attack": 3, "name": "菲菲"},
        "turn": 1,  # 1: 玩家1的回合, 2: 玩家2的回合
        "game_over": False,
        "winner": None,
        "move_count": 0,
        "battle_log": [],
    }
    return state


def load_state():
    """从文件加载游戏状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_state(state):
    """保存游戏状态到文件"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clear_screen():
    """清屏"""
    os.system("clear" if os.name == "posix" else "cls")


def get_board_display(state):
    """生成棋盘显示"""
    terrain = state["terrain"]
    p1_pos = tuple(state["player1"]["pos"])
    p2_pos = tuple(state["player2"]["pos"])
    p1_base = (0, 0)
    p2_base = (BOARD_SIZE - 1, BOARD_SIZE - 1)

    lines = []
    # 列标
    header = "     " + " ".join(f" {j} " for j in range(BOARD_SIZE))
    lines.append(header)
    lines.append("   " + "┌" + "───┬" * (BOARD_SIZE - 1) + "───┐")

    for i in range(BOARD_SIZE):
        row_cells = []
        for j in range(BOARD_SIZE):
            cell = terrain[i][j]

            # 检查是否有玩家在此格
            if (i, j) == p1_pos and (i, j) == p2_pos:
                cell = "⚔️"  # 战斗
            elif (i, j) == p1_pos:
                if (i, j) == p2_base:
                    cell = PLAYER1_BASE
                else:
                    cell = PLAYER1
            elif (i, j) == p2_pos:
                if (i, j) == p1_base:
                    cell = PLAYER2_BASE
                else:
                    cell = PLAYER2
            elif (i, j) == p1_base:
                cell = BASE_P1
            elif (i, j) == p2_base:
                cell = BASE_P2

            row_cells.append(f" {cell} ")

        row_str = f" {i} │" + "│".join(row_cells) + "│"
        lines.append(row_str)

        if i < BOARD_SIZE - 1:
            lines.append("   " + "├" + "───┼" * (BOARD_SIZE - 1) + "───┤")

    lines.append("   " + "└" + "───┴" * (BOARD_SIZE - 1) + "───┘")

    # 图例
    lines.append("")
    lines.append(f"  {BASE_P1} 你的基地  {BASE_P2} 菲菲基地  {PLAYER1} 你  {PLAYER2} 菲菲")
    lines.append(f"  {EMPTY} 空地  {FOREST} 森林(减速)  {ROCK} 岩石(不可通行)")

    return "\n".join(lines)


def get_status_bar(state):
    """生成状态栏"""
    p1 = state["player1"]
    p2 = state["player2"]
    turn = state["turn"]

    lines = []
    lines.append("=" * 50)
    lines.append(f"  🟦 你    HP: {p1['hp']}  攻击: {p1['attack']}  位置: ({p1['pos'][0]},{p1['pos'][1]})")
    lines.append(f"  🟥 菲菲  HP: {p2['hp']}  攻击: {p2['attack']}  位置: ({p2['pos'][0]},{p2['pos'][1]})")
    lines.append(f"  回合: {state['move_count'] + 1}")
    lines.append("=" * 50)

    if state["game_over"]:
        lines.append(f"  🏆 游戏结束！{state['winner']} 获胜！")
    else:
        current = p1 if turn == 1 else p2
        icon = PLAYER1 if turn == 1 else PLAYER2
        lines.append(f"  轮到：{icon} {current['name']} (玩家{turn})")

    if state["battle_log"]:
        lines.append(f"  ⚔️  {state['battle_log'][-1]}")

    lines.append("=" * 50)
    return "\n".join(lines)


def is_valid_move(state, player_num, direction):
    """检查移动是否合法"""
    player = state["player1"] if player_num == 1 else state["player2"]
    x, y = player["pos"]
    dx, dy = DIRECTIONS.get(direction, (0, 0))

    if dx == 0 and dy == 0:
        return False, "无效方向"

    nx, ny = x + dx, y + dy

    # 检查边界
    if nx < 0 or nx >= BOARD_SIZE or ny < 0 or ny >= BOARD_SIZE:
        return False, "超出棋盘边界"

    # 检查岩石
    if state["terrain"][nx][ny] == ROCK:
        return False, "前方是岩石，无法通行"

    return True, ""


def move_player(state, player_num, direction):
    """移动玩家，返回移动结果"""
    player = state["player1"] if player_num == 1 else state["player2"]
    x, y = player["pos"]
    dx, dy = DIRECTIONS[direction]
    nx, ny = x + dx, y + dy

    # 检查目标格地形
    cell_type = state["terrain"][nx][ny]
    cost = 2 if cell_type == FOREST else 1

    # 移动
    player["pos"] = [nx, ny]

    result = {
        "moved": True,
        "from": (x, y),
        "to": (nx, ny),
        "terrain": cell_type,
        "cost": cost,
        "battle": False,
        "base_capture": False,
    }

    # 检查是否到达对方基地
    p1_base = (0, 0)
    p2_base = (BOARD_SIZE - 1, BOARD_SIZE - 1)

    if player_num == 1 and (nx, ny) == p2_base:
        result["base_capture"] = True
        result["winner"] = "你"
    elif player_num == 2 and (nx, ny) == p1_base:
        result["base_capture"] = True
        result["winner"] = "菲菲"

    # 检查是否相遇（战斗）
    other = state["player2"] if player_num == 1 else state["player1"]
    if [nx, ny] == other["pos"]:
        result["battle"] = True
        result["battle_result"] = resolve_battle(state, player_num)

    return result


def resolve_battle(state, attacker_num):
    """解决战斗"""
    p1 = state["player1"]
    p2 = state["player2"]

    attacker = p1 if attacker_num == 1 else p2
    defender = p2 if attacker_num == 1 else p1

    log = f"{attacker['name']}(攻击力{attacker['attack']}) vs {defender['name']}(攻击力{defender['attack']})"

    if attacker["attack"] > defender["attack"]:
        # 攻击者获胜
        state["game_over"] = True
        state["winner"] = attacker["name"]
        log += f" → {attacker['name']}获胜！"
    elif defender["attack"] > attacker["attack"]:
        # 防御者获胜
        state["game_over"] = True
        state["winner"] = defender["name"]
        log += f" → {defender['name']}获胜！"
    else:
        # 平局，各扣1HP
        p1["hp"] -= 1
        p2["hp"] -= 1
        log += " → 平局！双方各损失1点HP"
        if p1["hp"] <= 0:
            state["game_over"] = True
            state["winner"] = p2["name"]
            log += f" → {p2['name']}获胜！"
        elif p2["hp"] <= 0:
            state["game_over"] = True
            state["winner"] = p1["name"]
            log += f" → {p1['name']}获胜！"

    state["battle_log"].append(log)
    return log


def render(state):
    """渲染完整游戏界面"""
    clear_screen()
    print("")
    print("  🎮 菲菲战棋 - 双人回合制对战")
    print(get_status_bar(state))
    print("")
    print(get_board_display(state))
    print("")


def process_turn(state, direction):
    """处理一个回合的移动"""
    if state["game_over"]:
        return False

    player_num = state["turn"]

    # 验证移动
    valid, msg = is_valid_move(state, player_num, direction)
    if not valid:
        print(f"  ❌ {msg}")
        time.sleep(1)
        return False

    # 执行移动
    result = move_player(state, player_num, direction)

    # 更新回合
    state["turn"] = 3 - player_num  # 1->2, 2->1
    state["move_count"] += 1

    # 检查游戏结束
    if result["base_capture"]:
        state["game_over"] = True
        state["winner"] = result["winner"]

    # 保存状态
    save_state(state)
    return True


def show_menu():
    """显示主菜单"""
    clear_screen()
    print("")
    print("  ╔══════════════════════════════╗")
    print("  ║      🎮 菲菲战棋             ║")
    print("  ║    双人回合制对战游戏         ║")
    print("  ╚══════════════════════════════╝")
    print("")
    print("  1. 🆕 开始新游戏")
    print("  2. 📂 继续上次游戏")
    print("  3. ❌ 退出")
    print("")


def new_game():
    """开始新游戏"""
    state = create_initial_state()
    save_state(state)
    return state


def main():
    """主函数"""
    state = None

    while True:
        show_menu()
        choice = input("  请选择 (1/2/3): ").strip()

        if choice == "1":
            state = new_game()
            break
        elif choice == "2":
            loaded = load_state()
            if loaded and not loaded.get("game_over", False):
                state = loaded
                print("  ✅ 已恢复上次游戏")
                time.sleep(1)
                break
            else:
                print("  ❌ 没有可恢复的游戏或游戏已结束")
                time.sleep(1.5)
                continue
        elif choice == "3":
            print("  👋 再见！")
            sys.exit(0)
        else:
            print("  ❌ 无效选择")
            time.sleep(1)

    # 游戏主循环
    while not state["game_over"]:
        render(state)

        p1 = state["player1"]
        p2 = state["player2"]
        current = p1 if state["turn"] == 1 else p2
        icon = PLAYER1 if state["turn"] == 1 else PLAYER2

        print(f"  轮到：{icon} {current['name']}")
        print(f"  输入命令 (w上/s下/a左/d右/q退出): ", end="", flush=True)

        cmd = input().strip().lower()

        if cmd == "q":
            print("  👋 游戏已保存，下次可继续。再见！")
            save_state(state)
            sys.exit(0)

        if cmd not in DIRECTIONS:
            print("  ❌ 无效命令，请使用 w/s/a/d")
            time.sleep(1)
            continue

        success = process_turn(state, cmd)
        if not success:
            continue

    # 游戏结束
    render(state)
    print(f"  🏆 {state['winner']} 获胜！")
    print("")
    print("  1. 🔄 再来一局")
    print("  2. ❌ 退出")
    print("")

    while True:
        choice = input("  请选择 (1/2): ").strip()
        if choice == "1":
            # 删除旧状态，重新开始
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            main()  # 重新开始
            return
        elif choice == "2":
            print("  👋 再见！")
            sys.exit(0)
        else:
            print("  ❌ 无效选择")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  👋 游戏已保存，下次可继续。再见！")
        # 尝试保存当前状态
        try:
            if 'state' in locals() and state and not state.get('game_over', True):
                save_state(state)
        except Exception:
            pass
        sys.exit(0)
