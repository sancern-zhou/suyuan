#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菲菲打字大作战 - 双人实时打字竞技游戏
"""

import os
import sys
import json
import time
import random
from datetime import datetime
from pathlib import Path


# 游戏文字库（10段以上中英文混合）
TEXTS = [
    "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
    "The quick brown fox jumps over the lazy dog.",
    "春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。",
    "Programming is thinking, not typing.",
    "海内存知己，天涯若比邻。",
    "Success is not final, failure is not fatal.",
    "落霞与孤鹜齐飞，秋水共长天一色。",
    "The best way to predict the future is to create it.",
    "会当凌绝顶，一览众山小。",
    "In the middle of difficulty lies opportunity.",
    "众里寻他千百度，蓦然回首，那人却在灯火阑珊处。",
    "Stay hungry, stay foolish.",
    "长风破浪会有时，直挂云帆济沧海。",
    "Life is what happens when you're busy making other plans.",
    "路漫漫其修远兮，吾将上下而求索。",
    "Code is like humor. When you have to explain it, it's bad.",
]


class GameState:
    """游戏状态管理"""

    def __init__(self, save_file):
        self.save_file = Path(save_file)
        self.state = self.load_state()

    def load_state(self):
        """加载游戏状态"""
        if self.save_file.exists():
            try:
                with open(self.save_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'current_round': 1,
            'total_rounds': 3,
            'player_score': 0,
            'feifei_score': 0,
            'history': [],
            'current_turn': 'player',  # 'player' or 'feifei'
            'used_texts': []
        }

    def save_state(self):
        """保存游戏状态"""
        self.save_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.save_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def reset(self):
        """重置游戏"""
        self.state = {
            'current_round': 1,
            'total_rounds': 3,
            'player_score': 0,
            'feifei_score': 0,
            'history': [],
            'current_turn': 'player',
            'used_texts': []
        }
        self.save_state()


class TypingGame:
    """打字游戏主类"""

    def __init__(self):
        self.state = GameState('/home/xckj/suyuan/backend/backend_data_registry/typing_state.json')
        self.box_width = 50

    def clear_screen(self):
        """清屏"""
        os.system('clear' if os.name != 'nt' else 'cls')

    def draw_box(self, title, content_lines):
        """绘制精美的游戏界面"""
        lines = []

        # 顶部边框
        lines.append("╔" + "═" * (self.box_width - 2) + "╗")

        # 标题行
        if title:
            title_padding = (self.box_width - 2 - len(title)) // 2
            lines.append("║" + " " * title_padding + title + " " * (self.box_width - 2 - title_padding - len(title)) + "║")
            lines.append("╠" + "═" * (self.box_width - 2) + "╣")

        # 内容行
        for line in content_lines:
            if len(line) > self.box_width - 4:
                # 长行自动换行
                words = line.split()
                current_line = ""
                for word in words:
                    if len(current_line) + len(word) + 1 > self.box_width - 4:
                        lines.append("║ " + current_line.ljust(self.box_width - 4) + " ║")
                        current_line = word + " "
                    else:
                        current_line += word + " "
                if current_line:
                    lines.append("║ " + current_line.ljust(self.box_width - 4) + " ║")
            else:
                lines.append("║ " + line.ljust(self.box_width - 4) + " ║")

        # 底部边框
        lines.append("╚" + "═" * (self.box_width - 2) + "╝")

        return "\n".join(lines)

    def show_welcome(self):
        """显示欢迎界面"""
        self.clear_screen()

        art = [
            "   ⌨️  菲菲打字大作战  ⌨️   ",
            "",
            "  双人实时打字竞技游戏",
            "",
            "  规则：",
            "  • 你和菲菲轮流挑战打字",
            "  • 比拼速度和准确率",
            "  • 3轮后总分高者获胜",
            "",
            "  准确率 × 速度(字/秒) = 得分",
        ]

        print(self.draw_box("", art))
        print()

        if self.state.state['current_round'] > 1:
            choice = input("  [C] 继续游戏  [N] 新游戏  [Q] 退出: ").strip().upper()
            if choice == 'C':
                return True
            elif choice == 'N':
                self.state.reset()
                return True
            elif choice == 'Q':
                return False
        else:
            choice = input("  [Enter] 开始游戏  [Q] 退出: ").strip().upper()
            if choice == 'Q':
                return False

        self.state.reset()
        return True

    def get_random_text(self):
        """获取随机文字（避免重复）"""
        available = [t for t in TEXTS if t not in self.state.state['used_texts']]
        if not available:
            self.state.state['used_texts'] = []
            available = TEXTS

        text = random.choice(available)
        self.state.state['used_texts'].append(text)
        return text

    def calculate_accuracy(self, original, typed):
        """计算准确率"""
        if not typed:
            return 0.0

        correct = sum(1 for a, b in zip(original, typed) if a == b)
        length_diff = abs(len(original) - len(typed))
        total = max(len(original), len(typed))

        accuracy = (correct - length_diff) / total * 100
        return max(0.0, min(100.0, accuracy))

    def player_turn(self):
        """玩家回合"""
        text = self.get_random_text()

        self.clear_screen()

        # 显示游戏界面
        header = f"第 {self.state.state['current_round']}/{self.state.state['total_rounds']} 轮  |  你 {self.state.state['player_score']:.1f} : {self.state.state['feifei_score']:.1f} 菲菲"

        content = [
            f"轮到：{'🟦 你' if self.state.state['current_turn'] == 'player' else '🟩 菲菲'}",
            "",
            "请打出下面这句话（按回车提交）：",
            "",
            "─" * 40,
            "",
            text,
            "",
            "─" * 40,
            "",
        ]

        print(self.draw_box(header, content))

        # 计时开始
        start_time = time.time()
        user_input = input("  你的输入：> ")
        end_time = time.time()

        # 计算结果
        elapsed = end_time - start_time
        accuracy = self.calculate_accuracy(text, user_input)
        speed = len(text) / elapsed if elapsed > 0 else 0
        score = accuracy * speed / 10

        # 更新状态
        self.state.state['player_score'] += score
        self.state.state['history'].append({
            'round': self.state.state['current_round'],
            'player': 'user',
            'text': text[:30] + "..." if len(text) > 30 else text,
            'accuracy': round(accuracy, 1),
            'speed': round(speed, 1),
            'score': round(score, 1)
        })

        # 显示结果
        self.clear_screen()
        result_content = [
            "✨ 你的成绩 ✨",
            "",
            f"准确率：{accuracy:.1f}%",
            f"速度：{speed:.1f} 字/秒",
            f"本轮得分：{score:.1f}",
            "",
            f"原文：{text[:40]}..." if len(text) > 40 else f"原文：{text}",
            f"你的输入：{user_input[:40]}..." if len(user_input) > 40 else f"你的输入：{user_input}",
        ]

        print(self.draw_box(header, result_content))
        input("\n  按回车继续...")

    def feifei_turn(self):
        """菲菲回合（模拟AI）"""
        text = self.get_random_text()

        self.clear_screen()

        header = f"第 {self.state.state['current_round']}/{self.state.state['total_rounds']} 轮  |  你 {self.state.state['player_score']:.1f} : {self.state.state['feifei_score']:.1f} 菲菲"

        content = [
            "轮到：🟩 菲菲",
            "",
            "菲菲正在打字中...",
            "",
            "─" * 40,
            "",
            text,
            "",
            "─" * 40,
        ]

        print(self.draw_box(header, content))

        # 模拟菲菲打字效果
        base_time = random.uniform(0.15, 0.25)  # 每个字符0.15-0.25秒
        total_time = len(text) * base_time + random.uniform(1, 3)

        # 进度条动画
        steps = 20
        for i in range(steps + 1):
            progress = "█" * i + "░" * (steps - i)
            percent = int(i / steps * 100)
            print(f"\r  进度：[{progress}] {percent}%", end="", flush=True)
            time.sleep(total_time / steps)

        print()

        # 菲菲的表现（模拟：较高准确率，适中速度）
        accuracy = random.uniform(85, 98)
        speed = len(text) / total_time
        score = accuracy * speed / 10

        # 更新状态
        self.state.state['feifei_score'] += score
        self.state.state['history'].append({
            'round': self.state.state['current_round'],
            'player': 'feifei',
            'text': text[:30] + "..." if len(text) > 30 else text,
            'accuracy': round(accuracy, 1),
            'speed': round(speed, 1),
            'score': round(score, 1)
        })

        # 显示结果
        self.clear_screen()
        result_content = [
            "🎀 菲菲的成绩 🎀",
            "",
            f"准确率：{accuracy:.1f}%",
            f"速度：{speed:.1f} 字/秒",
            f"本轮得分：{score:.1f}",
        ]

        print(self.draw_box(header, result_content))
        input("\n  按回车继续...")

    def show_round_result(self):
        """显示回合结果"""
        self.clear_screen()

        p_score = self.state.state['player_score']
        f_score = self.state.state['feifei_score']

        header = f"第 {self.state.state['current_round']} 轮结束"

        content = [
            "📊 当前比分 📊",
            "",
            f"  你：{'█' * int(min(p_score, 50) / 5)} {p_score:.1f} 分",
            f"  菲菲：{'█' * int(min(f_score, 50) / 5)} {f_score:.1f} 分",
            "",
            f"  差距：{abs(p_score - f_score):.1f} 分",
        ]

        if p_score > f_score:
            content.append("")
            content.append("  🎉 你领先了！")
        elif f_score > p_score:
            content.append("")
            content.append("  💪 菲菲领先，加油！")

        print(self.draw_box(header, content))
        input("\n  按回车继续...")

    def show_final_result(self):
        """显示最终结果"""
        self.clear_screen()

        p_score = self.state.state['player_score']
        f_score = self.state.state['feifei_score']

        if p_score > f_score:
            winner = "🏆 恭喜你获胜！🏆"
            emoji = "🎉"
        elif f_score > p_score:
            winner = "😢 菲菲获胜了"
            emoji = "🥀"
        else:
            winner = "🤝 平局！"
            emoji = "👏"

        header = "🎮 游戏结束 🎮"

        content = [
            f"{winner}",
            "",
            "━━━━━━━━━━━━━━━━━━",
            f"  你的总分：{p_score:.1f}",
            f"  菲菲总分：{f_score:.1f}",
            "━━━━━━━━━━━━━━━━━━",
            "",
            emoji,
            "",
            "历史记录：",
        ]

        for record in self.state.state['history'][-6:]:
            player_name = "你" if record['player'] == 'user' else "菲菲"
            content.append(f"  第{record['round']}轮 {player_name}: {record['score']:.1f}分")

        print(self.draw_box(header, content))
        print()
        print("  " + "─" * 46)
        print()

    def run(self):
        """运行游戏"""
        if not self.show_welcome():
            self.clear_screen()
            print("  👋 再见！")
            return

        while self.state.state['current_round'] <= self.state.state['total_rounds']:
            # 玩家回合
            self.state.state['current_turn'] = 'player'
            self.player_turn()
            self.state.save_state()

            # 菲菲回合
            self.state.state['current_turn'] = 'feifei'
            self.feifei_turn()
            self.state.save_state()

            # 显示回合结果
            self.show_round_result()

            # 下一轮
            self.state.state['current_round'] += 1
            self.state.save_state()

        # 游戏结束
        self.show_final_result()

        # 更新统计
        if not self.state.save_file.parent.joinpath('typing_stats.json').exists():
            stats = {'games_played': 0, 'player_wins': 0}
        else:
            with open(self.state.save_file.parent / 'typing_stats.json', 'r') as f:
                stats = json.load(f)

        stats['games_played'] += 1
        if self.state.state['player_score'] > self.state.state['feifei_score']:
            stats['player_wins'] += 1

        with open(self.state.save_file.parent / 'typing_stats.json', 'w') as f:
            json.dump(stats, f)

        # 清理游戏状态
        self.state.save_file.unlink(missing_ok=True)

        input("\n  按回车退出...")
        self.clear_screen()
        print("  👋 再见！")


if __name__ == "__main__":
    try:
        game = TypingGame()
        game.run()
    except KeyboardInterrupt:
        os.system('clear' if os.name != 'nt' else 'cls')
        print("\n  👋 游戏已退出")
        sys.exit(0)
