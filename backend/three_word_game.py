#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三人猜词大作战
玩家：用户（你）、菲菲（助理/裁判）、小智（AI子Agent）
"""

import json
import random
import os
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class Difficulty(Enum):
    EASY = (2, "⭐")
    MEDIUM = (3, "⭐⭐⭐")
    HARD = (5, "⭐⭐⭐⭐⭐")

    def __init__(self, points, stars):
        self.points = points
        self.stars = stars

    @property
    def label(self):
        labels = {self.EASY: "简单", self.MEDIUM: "中等", self.HARD: "困难"}
        return labels[self]


# 词库
WORD_LIBRARY = {
    Difficulty.EASY: [
        "苹果", "太阳", "月亮", "电脑", "书本", "椅子", "桌子", "水杯",
        "手机", "钥匙", "眼镜", "雨伞", "鞋子", "帽子", "手套", "袜子",
        "钱包", "书包", "铅笔", "橡皮", "剪刀", "纸巾", "牙膏", "毛巾",
        "西瓜", "香蕉", "橙子", "葡萄", "草莓", "蛋糕", "面包", "牛奶",
        "鸡蛋", "面条", "饺子", "米饭", "汤", "茶", "咖啡", "可乐",
        "花", "草", "树", "山", "河", "海", "云", "雨", "雪", "风",
        "猫", "狗", "鸟", "鱼", "兔子", "乌龟", "蝴蝶", "蜜蜂",
        "汽车", "飞机", "火车", "船", "自行车", "公交车", "地铁"
    ],
    Difficulty.MEDIUM: [
        "望远镜", "照相机", "自行车", "冰淇淋", "电视机", "微波炉",
        "洗衣机", "电冰箱", "空调", "风扇", "吸尘器", "电饭煲",
        "钢琴", "吉他", "小提琴", "笛子", "鼓", "手风琴",
        "足球", "篮球", "乒乓球", "羽毛球", "网球", "排球",
        "救护车", "消防车", "警车", "出租车", "卡车", "拖拉机",
        "长颈鹿", "大象", "狮子", "老虎", "熊猫", "袋鼠", "企鹅",
        "蜘蛛", "蜻蜓", "蚂蚁", "知了", "萤火虫", "蜗牛", "螃蟹",
        "蘑菇", "竹子", "仙人掌", "荷花", "向日葵", "玫瑰", "菊花",
        "彩虹", "流星", "彗星", "银河", "北斗星", "日食", "月食",
        "金字塔", "长城", "埃菲尔铁塔", "自由女神像", "比萨斜塔"
    ],
    Difficulty.HARD: [
        "海市蜃楼", "刻舟求剑", "守株待兔", "画蛇添足", "掩耳盗铃",
        "亡羊补牢", "井底之蛙", "盲人摸象", "拔苗助长", "杯弓蛇影",
        "对牛弹琴", "狐假虎威", "杞人忧天", "滥竽充数", "自相矛盾",
        "朝三暮四", "指鹿为马", "纸上谈兵", "草木皆兵", "破釜沉舟",
        "四面楚歌", "三顾茅庐", "空城计", "草船借箭", "完璧归赵",
        "负荆请罪", "毛遂自荐", "卧薪尝胆", "图穷匕见", "一字千金",
        "胸有成竹", "望梅止渴", "洛阳纸贵", "程门立雪", "闻鸡起舞",
        "悬梁刺股", "凿壁偷光", "囊萤映雪", "孟母三迁", "岳母刺字",
        "精卫填海", "愚公移山", "夸父追日", "女娲补天", "后羿射日",
        "嫦娥奔月", "牛郎织女", "白蛇传", "孟姜女", "梁山伯与祝英台"
    ]
}


# AI小智的描述库（用于出题）
AI_DESCRIPTIONS = {
    # 简单词描述
    "苹果": "一种圆圆的红色水果，皮很薄，肉很脆，很甜，医生说每天吃一个可以远离医院",
    "太阳": "天空中那个大大的、火热的、发光的天体，白天才能看到，没有它世界就会黑暗寒冷",
    "月亮": "夜晚天空中最亮的天体，圆圆的像盘子，有时弯弯的像小船，会跟着你走",
    "电脑": "一种电子设备，有屏幕和键盘，可以上网、打游戏、办公工作",
    "书本": "有很多页纸装订在一起的东西，里面有文字和图画，用来阅读学习",
    "椅子": "家具的一种，有四条腿和一个座位，还有靠背，用来坐的",
    "桌子": "平坦的家具，有四条腿，上面可以放东西，也可以吃饭写字",
    "水杯": "用来装水喝的容器，通常是圆柱形，有把手，可能是玻璃、塑料或金属做的",
    "手机": "小巧的电子设备，可以打电话、发信息、上网、拍照，几乎人人都有",
    "钥匙": "金属做的小东西，可以开门锁，通常和钥匙圈在一起",

    # 中等词描述
    "望远镜": "一种光学仪器，可以看到很远的东西，由两个镜筒组成，可以调节焦距，天文学家常用",
    "照相机": "用来拍照的设备，有镜头和快门，可以把美好的瞬间永久保存下来",
    "自行车": "两个轮子的交通工具，用脚踩踏板驱动，环保又健康，很多人用来通勤",
    "冰淇淋": "夏天最受欢迎的冷饮，用牛奶和糖做成，各种口味，放在冰箱里保存",
    "电视机": "有屏幕的家电，可以收看各种节目，新闻、电影、电视剧，家庭娱乐必备",
    "微波炉": "厨房电器，用微波加热食物，速度快，热牛奶很方便",
    "洗衣机": "洗衣服的机器，不用手搓，倒进洗衣粉和水就能自动洗干净",
    "电冰箱": "家电，用来保存食物，里面有冷藏和冷冻两个区域，夏天冰西瓜很爽",
    "钢琴": "键盘乐器，黑白相间的琴键，声音优美，可以弹奏各种乐曲",
    "吉他": "弦乐器，有六根弦，可以用手指或拨片弹奏，很多民谣歌手用它",

    # 困难词描述
    "海市蜃楼": "一种自然光学现象，在沙漠或海面上可以看到远处的景物像浮在空中一样，其实是光的折射造成的虚像",
    "刻舟求剑": "成语，讲一个人坐船时剑掉到水里，他在船边刻记号说等船靠岸了从刻记号的地方下水找剑，比喻拘泥成法，不知道变通",
    "守株待兔": "成语，讲一个农夫看到兔子撞死在树桩上，从此天天守在树桩旁等兔子，比喻不想努力而希望获得成功",
    "画蛇添足": "成语，讲比赛画蛇，一个人先画完又给蛇添上脚，结果反而输了，比喻做了多余的事反而不恰当",
    "掩耳盗铃": "成语，讲一个小偷偷钟怕别人听到，就捂住自己的耳朵，比喻自己欺骗自己",
    "亡羊补牢": "成语，讲羊丢了才修补羊圈，比喻出了问题及时补救还不晚",
    "井底之蛙": "成语，讲住在井底的青蛙以为天只有井口那么大，比喻见识短浅的人",
    "盲人摸象": "成语，讲几个盲人摸大象，摸到腿的说像柱子，摸到耳朵的说像扇子，比喻看问题不全面",
    "拔苗助长": "成语，讲农夫嫌禾苗长得慢，就把它们往上拔，结果禾苗都死了，比喻违反规律急于求成",
    "杯弓蛇影": "成语，讲一个人喝酒时看到杯子里有蛇的倒影，其实是墙上弓的影子，比喻疑神疑鬼"
}


# AI小智的猜测逻辑
class AIGuesser:
    """AI小智的猜词策略"""

    def __init__(self):
        self.guess_attempts = 0
        self.used_words = set()

    def guess_from_description(self, description: str, difficulty: Difficulty) -> Optional[str]:
        """根据描述猜词"""
        self.guess_attempts += 1

        # 简单的猜测策略
        candidates = []

        # 先从描述中提取关键词
        desc_lower = description.lower()

        # 根据关键词匹配词库
        for word in WORD_LIBRARY[difficulty]:
            if word in self.used_words:
                continue

            # 检查描述中是否有相关提示
            for key_word, desc in AI_DESCRIPTIONS.items():
                if key_word == word:
                    continue
                # 简单的关键词匹配
                if any(kw in description for kw in desc.split()[:5]):
                    candidates.append(word)

        # 如果有候选词，返回最相关的
        if candidates:
            guess = random.choice(candidates)
            self.used_words.add(guess)
            return guess

        # 否则从词库中随机猜一个没用过的词
        available = [w for w in WORD_LIBRARY[difficulty] if w not in self.used_words]
        if available:
            guess = random.choice(available)
            self.used_words.add(guess)
            return guess

        # 最后手段：随机猜测
        all_words = list(WORD_LIBRARY[difficulty])
        guess = random.choice(all_words)
        self.used_words.add(guess)
        return guess

    def reset(self):
        """重置猜测状态"""
        self.guess_attempts = 0
        self.used_words.clear()


@dataclass
class Player:
    name: str
    score: int = 0
    emoji: str = ""


@dataclass
class GameState:
    round_number: int = 1
    players: Dict[str, Player] = None
    current_questioner: str = ""  # 当前出题人
    current_word: str = ""  # 当前题目词
    current_difficulty: str = ""  # 当前难度
    current_description: str = ""  # 当前描述
    user_guess: str = ""  # 用户猜测
    ai_guess: str = ""  # AI猜测
    used_words: List[str] = None
    game_over: bool = False
    winner: Optional[str] = None
    phase: str = "start"  # start, describing, guessing, result

    def __post_init__(self):
        if self.players is None:
            self.players = {
                "user": Player("你", 0, "🟦"),
                "feifei": Player("菲菲", 0, "🟥"),
                "xiaozhi": Player("小智", 0, "🟩")
            }
        if self.used_words is None:
            self.used_words = []

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        players = {
            k: Player(**v) if isinstance(v, dict) else v
            for k, v in data["players"].items()
        }
        data["players"] = players
        return cls(**data)


class GameRenderer:
    """游戏界面渲染器"""

    @staticmethod
    def clear_screen():
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def draw_header(state: GameState):
        """绘制标题"""
        user = state.players["user"]
        feifei = state.players["feifei"]
        xiaozhi = state.players["xiaozhi"]

        print("╔" + "═" * 63 + "╗")
        print("║" + " " * 15 + "🎯 三人猜词大作战" + " " * 30 + "║")
        print("║" + " " * 8 + f"第 {state.round_number} 轮  |  {user.emoji} 你 {user.score} : "
              f"{xiaozhi.emoji} 小智 {xiaozhi.score}  : {feifei.emoji} 菲菲 {feifei.score} (裁判)" + " " * 3 + "║")
        print("╚" + "═" * 63 + "╝")
        print()

    @staticmethod
    def draw_questioner_info(state: GameState):
        """绘制出题人信息"""
        questioner = state.players[state.current_questioner]
        print(f"┌─ 本轮出题人：{questioner.emoji} {questioner.name}")
        print(f"├─ 题目难度：{state.current_difficulty}")
        print(f"└─ " + "─" * 58)
        print()

    @staticmethod
    def draw_description_area(state: GameState):
        """绘制描述区域"""
        if state.current_description:
            desc = state.current_description
            if state.current_questioner == "xiaozhi":
                print(f"🟩 小智的描述：")
                print(f"   {desc}")
            else:
                print(f"📝 描述：")
                print(f"   {desc}")
        else:
            print("📝 描述：________________")
        print()

    @staticmethod
    def draw_guess_area(state: GameState):
        """绘制猜测区域"""
        print("─" * 63)
        print()

        if state.current_questioner != "user":
            if state.user_guess:
                print(f"🟦 你猜：{state.user_guess}")
            else:
                print(f"🟦 你猜：________________")
        else:
            print(f"   （你是出题人，等待其他人猜）")

        print()

        if state.current_questioner != "xiaozhi":
            if state.ai_guess:
                print(f"🟩 小智猜：{state.ai_guess}")
            else:
                print(f"🟩 小智猜：________________")
        else:
            print(f"   （小智是出题人，等待其他人猜）")

        print()

    @staticmethod
    def draw_help():
        """绘制帮助信息"""
        print("─" * 63)
        print("📖 可用指令：")
        print("   • 开始游戏 - 开始新游戏")
        print("   • 出题：[描述] - 作为出题人给出描述")
        print("   • 猜：[答案] - 作为猜词人给出答案")
        print("   • 状态 - 查看当前状态")
        print("   • 帮助 - 显示此帮助")
        print("   • 退出 - 退出游戏")
        print("─" * 63)

    @staticmethod
    def draw_result(state: GameState, message: str):
        """绘制结果"""
        print()
        print("┌" + "─" * 61 + "┐")
        print(f"│ {message:^61} │")
        print("└" + "─" * 61 + "┘")
        print()

    @staticmethod
    def draw_game_over(state: GameState):
        """绘制游戏结束"""
        winner = state.players[state.winner]
        print()
        print("╔" + "═" * 63 + "╗")
        print("║" + " " * 18 + "🏆 游戏结束 🏆" + " " * 26 + "║")
        print("║" + " " * 12 + f"🎉 {winner.emoji} {winner.name} 获胜！🎉" + " " * 21 + "║")
        print("╚" + "═" * 63 + "╝")
        print()


class GameEngine:
    """游戏引擎"""

    STATE_FILE = "/home/xckj/suyuan/backend/three_word_state.json"
    WINNING_SCORE = 8

    def __init__(self):
        self.state = self._load_state()
        self.ai_guesser = AIGuesser()
        self.renderer = GameRenderer()

    def _load_state(self) -> GameState:
        """加载游戏状态"""
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return GameState.from_dict(data)
            except:
                pass
        return GameState()

    def _save_state(self):
        """保存游戏状态"""
        with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)

    def _select_random_word(self) -> Tuple[str, Difficulty]:
        """随机选择一个词"""
        # 简单词50%，中等词30%，困难词20%
        rand = random.random()
        if rand < 0.5:
            difficulty = Difficulty.EASY
        elif rand < 0.8:
            difficulty = Difficulty.MEDIUM
        else:
            difficulty = Difficulty.HARD

        words = [w for w in WORD_LIBRARY[difficulty] if w not in self.state.used_words]
        if not words:
            # 如果词用完了，重置
            self.state.used_words = []
            words = WORD_LIBRARY[difficulty]

        word = random.choice(words)
        self.state.used_words.append(word)
        return word, difficulty

    def _select_questioner(self) -> str:
        """选择出题人（轮换制）"""
        order = ["user", "xiaozhi", "feifei"]
        idx = (self.state.round_number - 1) % 3
        return order[idx]

    def start_new_game(self):
        """开始新游戏"""
        self.state = GameState()
        self.state.phase = "describing"
        self._start_new_round()
        self._save_state()

    def _start_new_round(self):
        """开始新一轮"""
        self.state.current_questioner = self._select_questioner()
        self.state.current_word, difficulty = self._select_random_word()
        self.state.current_difficulty = f"{difficulty.stars}（{difficulty.label}，{difficulty.points}分）"
        self.state.current_description = ""
        self.state.user_guess = ""
        self.state.ai_guess = ""
        self.ai_guesser.reset()

        # 如果是AI出题，自动生成描述
        if self.state.current_questioner == "xiaozhi":
            self._generate_ai_description()

    def _generate_ai_description(self):
        """AI生成描述"""
        word = self.state.current_word
        if word in AI_DESCRIPTIONS:
            self.state.current_description = AI_DESCRIPTIONS[word]
        else:
            # 生成通用描述
            self.state.current_description = f"这是一个关于'{word}'的谜题，请根据这个词的含义和特点来猜"

        self.state.phase = "guessing"
        self._save_state()

    def process_user_description(self, description: str):
        """处理用户描述"""
        if self.state.current_questioner != "user":
            return "现在不是你出题的回合！"

        # 验证描述（检查是否包含题目词）
        word = self.state.current_word
        if any(char in description for char in word):
            return f"描述中不能包含题目词'{word}'中的任何字！"

        self.state.current_description = description
        self.state.phase = "guessing"

        # AI自动猜测
        self._ai_make_guess()

        self._save_state()
        return None

    def _ai_make_guess(self):
        """AI进行猜测"""
        difficulty = self._get_difficulty_from_string(self.state.current_difficulty)
        guess = self.ai_guesser.guess_from_description(
            self.state.current_description,
            difficulty
        )
        self.state.ai_guess = guess

    def _get_difficulty_from_string(self, diff_str: str) -> Difficulty:
        """从难度字符串获取难度枚举"""
        if "简单" in diff_str:
            return Difficulty.EASY
        elif "困难" in diff_str:
            return Difficulty.HARD
        else:
            return Difficulty.MEDIUM

    def process_user_guess(self, guess: str) -> str:
        """处理用户猜测"""
        if self.state.current_questioner == "user":
            return "你是出题人，不能猜！"

        self.state.user_guess = guess.strip()

        # 检查是否猜对
        if self.state.user_guess == self.state.current_word:
            return self._handle_correct_guess("user")
        elif self.state.ai_guess == self.state.current_word:
            return self._handle_correct_guess("xiaozhi")
        else:
            # 都没猜对，显示结果
            result = self._show_round_result(False, None)
            self._next_round()
            return result

    def _handle_correct_guess(self, winner_id: str) -> str:
        """处理猜对情况"""
        difficulty = self._get_difficulty_from_string(self.state.current_difficulty)
        points = difficulty.points

        self.state.players[winner_id].score += points
        winner = self.state.players[winner_id]

        message = f"✅ 答对了！答案是「{self.state.current_word}」，{winner.emoji} {winner.name} 获得 {points} 分！"

        # 检查是否获胜
        if self.state.players[winner_id].score >= self.WINNING_SCORE:
            self.state.game_over = True
            self.state.winner = winner_id
            self._save_state()
            return message + " 🎉 游戏结束！"

        result = self._show_round_result(True, winner_id)
        self._next_round()
        return message + "\n" + result

    def _show_round_result(self, correct: bool, winner_id: Optional[str]) -> str:
        """显示本轮结果"""
        if correct and winner_id:
            winner = self.state.players[winner_id]
            return f"📊 本轮结果：{winner.emoji} {winner.name} 猜对了！"
        else:
            word = self.state.current_word
            user_guess = self.state.user_guess or "未猜测"
            ai_guess = self.state.ai_guess or "未猜测"
            return (f"❌ 都没猜对！答案是「{word}」\n"
                   f"   🟦 你猜：{user_guess}\n"
                   f"   🟩 小智猜：{ai_guess}")

    def _next_round(self):
        """进入下一轮"""
        self.state.round_number += 1
        self._start_new_round()
        self._save_state()

    def get_status(self) -> str:
        """获取游戏状态"""
        user = self.state.players["user"]
        xiaozhi = self.state.players["xiaozhi"]
        feifei = self.state.players["feifei"]

        status = f"""
📊 当前游戏状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔢 轮次：第 {self.state.round_number} 轮
🎯 出题人：{self.state.players[self.state.current_questioner].emoji} {self.state.players[self.state.current_questioner].name}
⭐ 难度：{self.state.current_difficulty}

📊 得分：
   {user.emoji} 你：{user.score} 分
   {xiaozhi.emoji} 小智：{xiaozhi.score} 分
   {feifei.emoji} 菲菲：{feifei.score} 分（裁判，不参与猜词）

🎮 胜利条件：先到 {self.WINNING_SCORE} 分者获胜

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return status


def main():
    """主函数"""
    engine = GameEngine()
    renderer = GameRenderer()

    # 游戏主循环
    while True:
        renderer.clear_screen()

        # 绘制界面
        renderer.draw_header(engine.state)

        if engine.state.game_over:
            renderer.draw_game_over(engine.state)
            print("输入 '开始游戏' 开始新游戏，或 '退出' 退出：")
            cmd = input("> ").strip()
            if cmd == "退出":
                print("👋 感谢游玩，再见！")
                break
            elif cmd == "开始游戏":
                engine.start_new_game()
            continue

        if engine.state.phase == "start" or not engine.state.current_word:
            print("欢迎来到《三人猜词大作战》！")
            print()
            print("游戏规则：")
            print("  • 三人轮流当出题人和猜词人")
            print("  • 出题人看到题目词，用文字描述（不能说出词中的字）")
            print("  • 猜词人根据描述猜词")
            print("  • 猜对得分，先到8分者获胜")
            print("  • 菲菲（助理）只负责裁判，不参与猜词")
            print()
            print("输入 '开始游戏' 开始：")
            cmd = input("> ").strip()
            if cmd == "开始游戏":
                engine.start_new_game()
            elif cmd == "退出":
                print("👋 感谢游玩，再见！")
                break
            continue

        # 绘制出题人信息
        renderer.draw_questioner_info(engine.state)

        # 绘制描述区域
        renderer.draw_description_area(engine.state)

        # 绘制猜测区域
        renderer.draw_guess_area(engine.state)

        # 绘制帮助
        renderer.draw_help()

        # 获取用户输入
        print()
        cmd = input("🟦 请输入指令：").strip()

        if not cmd:
            continue

        if cmd == "退出":
            print("👋 感谢游玩，再见！")
            break

        elif cmd == "帮助":
            continue

        elif cmd == "状态":
            status = engine.get_status()
            print(status)
            input("按回车继续...")

        elif cmd == "开始游戏":
            engine.start_new_game()

        elif cmd.startswith("出题："):
            if engine.state.phase == "describing" and engine.state.current_questioner == "user":
                description = cmd[3:].strip()
                error = engine.process_user_description(description)
                if error:
                    renderer.draw_result(engine.state, f"❌ {error}")
                    input("按回车继续...")
            else:
                renderer.draw_result(engine.state, "❌ 现在不是你出题的回合！")
                input("按回车继续...")

        elif cmd.startswith("猜："):
            if engine.state.phase == "guessing" and engine.state.current_questioner != "user":
                guess = cmd[2:].strip()
                result = engine.process_user_guess(guess)
                renderer.draw_result(engine.state, result)
                input("按回车继续...")
            else:
                renderer.draw_result(engine.state, "❌ 现在不是猜词阶段！")
                input("按回车继续...")

        else:
            renderer.draw_result(engine.state, f"❌ 未知指令：{cmd}")
            input("按回车继续...")


if __name__ == "__main__":
    main()
