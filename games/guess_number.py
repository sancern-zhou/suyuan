#!/usr/bin/env python3
"""
菲菲猜数字 - 双人互动猜数字游戏 + AI对战模式

游戏规则：
- 系统随机生成1-100之间的数字
- 两个玩家轮流猜数字
- 每次猜完后提示"大了"或"小了"
- 猜中的玩家获胜

模式：
1. 交互式双人模式（默认运行）
2. --auto: 自动对战模式（预设双方猜测列表）
3. --vs-ai-batch: 人机对战模式（你 vs 菲菲）
4. --interactive: 消息中间人交互模式（你 vs 菲菲，逐轮输入）
"""

import random
import sys

# ANSI颜色代码
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """打印彩色标题"""
    print(f"\n{Colors.BOLD}{Colors.OKCYAN}{'=' * 50}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{text:^50}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{'=' * 50}{Colors.ENDC}\n")

def print_success(text):
    """打印绿色成功信息"""
    print(f"{Colors.OKGREEN}{text}{Colors.ENDC}")

def print_warning(text):
    """打印黄色警告信息"""
    print(f"{Colors.WARNING}{text}{Colors.ENDC}")

def print_error(text):
    """打印红色错误信息"""
    print(f"{Colors.FAIL}{text}{Colors.ENDC}")

def print_info(text):
    """打印蓝色提示信息"""
    print(f"{Colors.OKBLUE}{text}{Colors.ENDC}")

def get_player_name(player_num):
    """获取玩家名称"""
    while True:
        name = input(f"请输入玩家{player_num}的名字: ").strip()
        if name:
            return name
        print_warning("名字不能为空，请重新输入！")

def get_guess(player_name):
    """获取玩家的猜测"""
    while True:
        try:
            guess = input(f"{Colors.BOLD}{player_name}{Colors.ENDC}, 请输入你猜的数字 (1-100): ").strip()
            if not guess:
                print_error("输入不能为空！")
                continue
            num = int(guess)
            if 1 <= num <= 100:
                return num
            else:
                print_warning("请输入1-100之间的数字！")
        except (ValueError, EOFError):
            print_error("无效输入，请输入一个数字！")

def print_history(history, player1_name, player2_name):
    """打印猜测历史"""
    print(f"\n{Colors.BOLD}{Colors.OKCYAN}{'猜测历史':^40}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}{'-' * 40}{Colors.ENDC}")
    for i, (name, guess, hint) in enumerate(history, 1):
        hint_color = Colors.OKGREEN if hint == "正确！" else Colors.WARNING
        print(f"第{i}轮: {name} 猜 {guess} - {hint_color}{hint}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}{'-' * 40}{Colors.ENDC}\n")

def play_round(player1_name, player2_name, round_num):
    """进行一轮游戏"""
    target = random.randint(1, 100)
    history = []
    current_player = 1
    guess_count = {player1_name: 0, player2_name: 0}

    print_header(f"第 {round_num} 轮开始！")
    print_info(f"系统已生成一个 1-100 之间的神秘数字...")
    print_info(f"看看谁能先猜中！\n")

    while True:
        player_name = player1_name if current_player == 1 else player2_name
        print(f"{Colors.BOLD}{Colors.WARNING}轮到 {player_name} 了！{Colors.ENDC}")

        guess = get_guess(player_name)
        guess_count[player_name] += 1

        if guess == target:
            history.append((player_name, guess, "正确！"))
            print_success(f"\n恭喜 {player_name} 猜对了！答案就是 {target}！")
            print_header(f"{player_name} 获胜！")
            break
        elif guess < target:
            hint = "小了"
            print_warning(f"{guess} 小了，再大一点！")
        else:
            hint = "大了"
            print_warning(f"{guess} 大了，再小一点！")

        history.append((player_name, guess, hint))
        print_history(history, player1_name, player2_name)

        # 切换玩家
        current_player = 2 if current_player == 1 else 1

    return player_name, guess_count, history

def print_statistics(player1_name, player2_name, wins, total_rounds):
    """打印统计信息"""
    print_header("游戏统计")
    print(f"总轮数: {total_rounds}")
    print(f"{Colors.BOLD}{player1_name}{Colors.ENDC}: 获胜 {wins[player1_name]} 次")
    print(f"{Colors.BOLD}{player2_name}{Colors.ENDC}: 获胜 {wins[player2_name]} 次")

    if wins[player1_name] > wins[player2_name]:
        print_success(f"\n最终冠军: {player1_name}！")
    elif wins[player2_name] > wins[player1_name]:
        print_success(f"\n最终冠军: {player2_name}！")
    else:
        print_info("\n平局！两位玩家旗鼓相当！")

def auto_play(player1_name, player2_name, guesses_dict, target=None):
    """
    自动对战模式

    Args:
        player1_name: 玩家1名字
        player2_name: 玩家2名字
        guesses_dict: 字典，key为玩家名，value为该玩家要猜的数字列表（按顺序取）
        target: 可选的指定答案，用于测试

    Returns:
        结果字典:
        {
            "winner": 获胜者名字,
            "target": 正确答案,
            "total_rounds": 总轮数,
            "history": [[玩家名, 猜的数字, 提示], ...],
            "player1_guesses": 玩家1猜的次数,
            "player2_guesses": 玩家2猜的次数
        }
    """
    if target is None:
        target = random.randint(1, 100)

    history = []
    current_player = 1
    guess_count = {player1_name: 0, player2_name: 0}

    # 初始化猜测迭代器
    guess_iterators = {
        player1_name: iter(guesses_dict.get(player1_name, [])),
        player2_name: iter(guesses_dict.get(player2_name, []))
    }

    while True:
        player_name = player1_name if current_player == 1 else player2_name

        # 从预设列表中取下一个猜测
        try:
            guess = next(guess_iterators[player_name])
        except StopIteration:
            # 没有预设猜测了，该玩家输
            winner = player2_name if current_player == 1 else player1_name
            history.append([player_name, None, "无预设猜测，认输"])
            return {
                "winner": winner,
                "target": target,
                "total_rounds": len([h for h in history if h[2] in ["大了", "小了"]]) + 1,
                "history": history,
                "player1_guesses": guess_count[player1_name],
                "player2_guesses": guess_count[player2_name]
            }

        guess_count[player_name] += 1

        if guess == target:
            history.append([player_name, guess, "正确！"])
            return {
                "winner": player_name,
                "target": target,
                "total_rounds": len([h for h in history if h[2] in ["大了", "小了"]]) + 1,
                "history": history,
                "player1_guesses": guess_count[player1_name],
                "player2_guesses": guess_count[player2_name]
            }
        elif guess < target:
            hint = "小了"
        else:
            hint = "大了"

        history.append([player_name, guess, hint])
        current_player = 2 if current_player == 1 else 1

def vs_ai_batch(player_name, my_guesses, target=None):
    """
    人机对战模式：你 vs 菲菲（AI）

    你和菲菲轮流猜数字，你的猜测从预定义列表取，AI用二分法策略。

    Args:
        player_name: 你的名字
        my_guesses: 你的猜测列表（按顺序使用）
        target: 可选的指定答案，用于测试

    Returns:
        结果字典:
        {
            "winner": 获胜者名字,
            "target": 正确答案,
            "total_rounds": 总轮数,
            "history": [[玩家名, 猜的数字, 提示], ...],
            "player_guesses": 玩家猜的次数,
            "ai_guesses": AI猜的次数
        }
    """
    if target is None:
        target = random.randint(1, 100)

    ai_name = "菲菲"
    history = []
    current_player = 0  # 0=玩家, 1=AI
    guess_count = {player_name: 0, ai_name: 0}

    # AI的二分法范围
    ai_low, ai_high = 1, 100
    player_guess_iter = iter(my_guesses)

    while True:
        if current_player == 0:
            # 玩家回合
            try:
                guess = next(player_guess_iter)
            except StopIteration:
                # 玩家没有猜测了，AI获胜
                history.append([player_name, None, "无预设猜测，认输"])
                return {
                    "winner": ai_name,
                    "target": target,
                    "total_rounds": len([h for h in history if h[2] in ["大了", "小了"]]) + 1,
                    "history": history,
                    "player_guesses": guess_count[player_name],
                    "ai_guesses": guess_count[ai_name]
                }
            current_name = player_name
        else:
            # AI回合：二分法策略
            guess = (ai_low + ai_high) // 2
            current_name = ai_name

        guess_count[current_name] += 1

        if guess == target:
            history.append([current_name, guess, "正确！"])
            return {
                "winner": current_name,
                "target": target,
                "total_rounds": len([h for h in history if h[2] in ["大了", "小了"]]) + 1,
                "history": history,
                "player_guesses": guess_count[player_name],
                "ai_guesses": guess_count[ai_name]
            }
        elif guess < target:
            hint = "小了"
            if current_player == 1:
                # AI猜小了，更新下界
                ai_low = guess + 1
        else:
            hint = "大了"
            if current_player == 1:
                # AI猜大了，更新上界
                ai_high = guess - 1

        history.append([current_name, guess, hint])
        current_player = 1 - current_player  # 切换玩家

def interactive_vs_ai(player_name):
    """
    消息中间人交互模式：你 vs 菲菲（AI）

    一轮一轮地交互，适合通过微信等消息中间人进行游戏。
    你和菲菲轮流猜数字，你的猜测通过 input() 实时输入，AI用二分法策略。

    Args:
        player_name: 你的名字
    """
    target = random.randint(1, 100)
    ai_name = "菲菲"
    history = []
    current_player = 0  # 0=玩家, 1=AI
    guess_count = {player_name: 0, ai_name: 0}
    round_num = 1

    # AI的二分法范围
    ai_low, ai_high = 1, 100

    print_header("消息中间人交互模式")
    print_info(f"玩家: {player_name} vs {ai_name}")
    print_info(f"神秘数字已生成 (1-100)")
    print_info(f"每轮只需输入一个数字，输入 'q' 退出\n")

    while True:
        if current_player == 0:
            # 玩家回合
            print(f"\n{Colors.BOLD}{Colors.OKCYAN}[第{round_num}轮] 轮到你了！{Colors.ENDC}")
            print(f"{Colors.OKCYAN}{'=' * 45}{Colors.ENDC}")

            while True:
                try:
                    user_input = input(f"{Colors.BOLD}{player_name}, 请输入你的猜测 (1-100 或 q退出): {Colors.ENDC}").strip()

                    if user_input.lower() == 'q':
                        print_info(f"\n游戏退出！答案是 {target}")
                        return

                    if not user_input:
                        print_error("输入不能为空！")
                        continue

                    guess = int(user_input)
                    if 1 <= guess <= 100:
                        break
                    else:
                        print_warning("请输入1-100之间的数字！")
                except (ValueError, EOFError):
                    print_error("无效输入，请输入一个数字！")

            current_name = player_name
        else:
            # AI回合：二分法策略
            print(f"\n{Colors.BOLD}{Colors.OKBLUE}[第{round_num}轮] 轮到{ai_name}了！{Colors.ENDC}")
            print(f"{Colors.OKBLUE}{'=' * 45}{Colors.ENDC}")

            guess = (ai_low + ai_high) // 2
            current_name = ai_name
            print(f"{Colors.OKBLUE}  {ai_name} 思考中...{Colors.ENDC}")

        guess_count[current_name] += 1

        # 判断结果
        if guess == target:
            history.append([current_name, guess, "正确！"])
            print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'=' * 45}{Colors.ENDC}")
            print(f"{Colors.OKGREEN}  {current_name} 猜对了！答案是 {target}！{Colors.ENDC}")
            print(f"{Colors.OKGREEN}{'=' * 45}{Colors.ENDC}")

            # 显示统计
            print(f"\n{Colors.BOLD}本局统计:{Colors.ENDC}")
            print(f"  {player_name} 猜了 {guess_count[player_name]} 次")
            print(f"  {ai_name} 猜了 {guess_count[ai_name]} 次")

            if guess_count[player_name] < guess_count[ai_name]:
                print_success(f"\n  {player_name} 获胜！")
            elif guess_count[ai_name] < guess_count[player_name]:
                print_info(f"\n  {ai_name} 获胜！")
            else:
                print_warning(f"\n  平局！")

            return
        elif guess < target:
            hint = "小了"
            hint_color = Colors.WARNING
            if current_player == 1:
                # AI猜小了，更新下界
                ai_low = guess + 1
        else:
            hint = "大了"
            hint_color = Colors.OKBLUE
            if current_player == 1:
                # AI猜大了，更新上界
                ai_high = guess - 1

        history.append([current_name, guess, hint])

        # 输出本轮结果
        print(f"\n{Colors.BOLD}  结果:{Colors.ENDC} {current_name} 猜 {guess} -> {hint_color}{hint}{Colors.ENDC}")

        # 显示猜测历史摘要
        print(f"\n{Colors.BOLD}  历史摘要:{Colors.ENDC}")
        for i, (name, g, h) in enumerate(history[-5:], 1):  # 只显示最近5条
            h_color = Colors.OKGREEN if h == "正确！" else (Colors.WARNING if h == "小了" else Colors.OKBLUE)
            offset = len(history) - 5 if len(history) > 5 else 0
            print(f"    [{i + offset}] {name}: {g} ({h_color}{h}{Colors.ENDC})")

        if len(history) > 5:
            print(f"    ... (共{len(history)}条历史)")

        # 切换玩家
        current_player = 1 - current_player
        round_num += 1

def parse_guess_args(args):
    """
    解析自动对战模式的参数

    格式: "玩家名:数字1,数字2,数字3"
    例如: "你:60,45" -> {"你": [60, 45]}

    Returns:
        guesses_dict: {玩家名: [数字列表]}
    """
    guesses_dict = {}
    for arg in args:
        if ':' not in arg:
            print_error(f"无效参数格式: {arg}")
            print_info("正确格式: 玩家名:数字1,数字2")
            sys.exit(1)

        player_name, numbers_str = arg.split(':', 1)
        player_name = player_name.strip()

        try:
            numbers = [int(n.strip()) for n in numbers_str.split(',')]
        except ValueError:
            print_error(f"无效的数字列表: {numbers_str}")
            sys.exit(1)

        guesses_dict[player_name] = numbers

    return guesses_dict

def main():
    """主游戏循环"""
    print_header("菲菲猜数字")
    print_info("欢迎来到双人猜数字游戏！")
    print_info("两个玩家轮流猜数字，看谁先猜中神秘数字！\n")

    # 获取玩家名称
    player1_name = get_player_name(1)
    player2_name = get_player_name(2)

    print_info(f"\n欢迎 {player1_name} 和 {player2_name}！")
    print_info("游戏即将开始...\n")

    wins = {player1_name: 0, player2_name: 0}
    round_num = 0

    while True:
        round_num += 1
        winner, guess_count, history = play_round(player1_name, player2_name, round_num)
        wins[winner] += 1

        # 显示本轮统计
        print(f"\n{Colors.BOLD}本轮统计:{Colors.ENDC}")
        print(f"{player1_name} 猜了 {guess_count[player1_name]} 次")
        print(f"{player2_name} 猜了 {guess_count[player2_name]} 次")

        # 询问是否继续
        print(f"\n{Colors.BOLD}是否继续游戏？{Colors.ENDC}")
        choice = input(f"输入 {Colors.OKGREEN}y{Colors.ENDC} 继续，其他键退出: ").strip().lower()

        if choice != 'y':
            break

    # 显示最终统计
    print_statistics(player1_name, player2_name, wins, round_num)

    print(f"\n{Colors.OKGREEN}感谢游玩菲菲猜数字！再见！{Colors.ENDC}\n")

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--auto":
            # 自动对战模式
            if len(sys.argv) < 4:
                print("用法: python3 guess_number.py --auto \"玩家1:数字1,数字2\" \"玩家2:数字1,数字2\"")
                print("例如: python3 guess_number.py --auto \"你:60,45\" \"菲菲:50,55\"")
                sys.exit(1)

            guesses_dict = parse_guess_args(sys.argv[2:4])

            if len(guesses_dict) < 2:
                print_error("需要至少两个玩家！")
                sys.exit(1)

            player_names = list(guesses_dict.keys())
            player1_name = player_names[0]
            player2_name = player_names[1]

            result = auto_play(player1_name, player2_name, guesses_dict)

            # 简洁文本输出（无颜色码）
            print(f"获胜者: {result['winner']}")
            print(f"正确答案: {result['target']}")
            print(f"总轮数: {result['total_rounds']}")
            print(f"{player1_name}猜测次数: {result['player1_guesses']}")
            print(f"{player2_name}猜测次数: {result['player2_guesses']}")
            print("猜测历史:")
            for i, (name, guess, hint) in enumerate(result['history'], 1):
                print(f"  第{i}轮: {name} 猜 {guess} - {hint}")

        elif len(sys.argv) > 1 and sys.argv[1] == "--vs-ai-batch":
            # 人机对战模式
            if len(sys.argv) < 3:
                print("用法: python3 guess_number.py --vs-ai-batch \"你的名字\" 数字1 数字2 数字3 ...")
                print("例如: python3 guess_number.py --vs-ai-batch \"小明\" 60 45 50")
                sys.exit(1)

            player_name = sys.argv[2]

            try:
                my_guesses = [int(n) for n in sys.argv[3:]]
            except ValueError:
                print_error("无效的数字列表")
                sys.exit(1)

            if not my_guesses:
                print_error("至少需要提供一个猜测数字")
                sys.exit(1)

            result = vs_ai_batch(player_name, my_guesses)

            # 简洁文本输出（无颜色码）
            print(f"获胜者: {result['winner']}")
            print(f"正确答案: {result['target']}")
            print(f"总轮数: {result['total_rounds']}")
            print(f"{player_name}猜测次数: {result['player_guesses']}")
            print(f"菲菲猜测次数: {result['ai_guesses']}")
            print("猜测历史:")
            for i, (name, guess, hint) in enumerate(result['history'], 1):
                print(f"  第{i}轮: {name} 猜 {guess} - {hint}")

        elif len(sys.argv) > 1 and sys.argv[1] == "--interactive":
            # 消息中间人交互模式
            if len(sys.argv) < 3:
                print("用法: python3 guess_number.py --interactive \"你的名字\"")
                print("例如: python3 guess_number.py --interactive \"小明\"")
                sys.exit(1)

            player_name = sys.argv[2]
            interactive_vs_ai(player_name)

        else:
            main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}游戏已中断。再见！{Colors.ENDC}\n")
        sys.exit(0)
