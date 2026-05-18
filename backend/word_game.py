#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菲菲猜词大作战 - 实时双人猜词对战游戏
"""

import os
import json
import random
import time
import sys
from pathlib import Path


class WordGame:
    """猜词游戏主类"""

    # 词库 - 按难度分类（75个词）
    WORD_LIBRARY = {
        "simple": [  # 2分 - 25个
            "苹果", "太阳", "月亮", "电脑", "书本",
            "桌子", "椅子", "杯子", "手机", "电视",
            "足球", "篮球", "钢琴", "吉他", "画笔",
            "眼镜", "手表", "雨伞", "书包", "钱包",
            "钥匙", "门", "窗户", "冰箱", "洗衣机"
        ],
        "medium": [  # 3分 - 25个
            "望远镜", "照相机", "自行车", "冰淇淋",
            "蛋糕", "比萨", "汉堡", "薯条", "可乐",
            "咖啡", "牛奶", "面包", "香蕉", "西瓜",
            "草莓", "葡萄", "樱桃", "芒果", "榴莲",
            "长颈鹿", "企鹅", "熊猫", "袋鼠", "考拉"
        ],
        "hard": [  # 5分 - 25个
            "海市蜃楼", "刻舟求剑", "守株待兔", "画蛇添足",
            "掩耳盗铃", "拔苗助长", "井底之蛙", "狐假虎威",
            "亡羊补牢", "杞人忧天", "邯郸学步", "东施效颦",
            "滥竽充数", "自相矛盾", "南辕北辙", "杯弓蛇影",
            "指鹿为马", "纸上谈兵", "草木皆兵", "四面楚歌",
            "破釜沉舟", "卧薪尝胆", "三顾茅庐", "负荆请罪"
        ]
    }

    # 预设描述（用于AI出题）
    DESCRIPTIONS = {
        # 简单词
        "苹果": "一种红色的水果，医生远离我",
        "太阳": "天上挂着的，白天发光发热的球体",
        "月亮": "晚上天上挂着的，有时圆有时缺",
        "电脑": "用来工作和娱乐的电子设备",
        "书本": "用来阅读的，有很多页纸",
        "桌子": "放东西的家具，有四条腿",
        "椅子": "用来坐的家具",
        "杯子": "用来喝水的容器",
        "手机": "可以打电话的便携设备",
        "电视": "可以看节目的屏幕",
        "足球": "用脚踢的球类运动",
        "篮球": "用手投篮的球类运动",
        "钢琴": "黑白键的乐器，按下去会响",
        "吉他": "有六根弦的乐器",
        "画笔": "用来画画的工具",
        "眼镜": "戴在眼睛上，帮助看清东西",
        "手表": "戴在手腕上，用来看时间",
        "雨伞": "下雨时用来挡雨的工具",
        "书包": "用来装书和文具的包",
        "钱包": "用来装钱和卡片的小包",
        "钥匙": "用来开门的小金属片",
        "门": "房子的出入口",
        "窗户": "墙上用来采光通风的开口",
        "冰箱": "用来保鲜食物的电器",
        "洗衣机": "用来洗衣服的电器",
        # 中等词
        "望远镜": "用来观察远处物体的光学仪器",
        "照相机": "用来拍照的设备",
        "自行车": "两个轮子，用脚蹬的交通工具",
        "冰淇淋": "夏天吃的冰凉甜品",
        "蛋糕": "过生日时吃的甜点",
        "比萨": "圆形的，上面有奶酪和配料的意大利美食",
        "汉堡": "两片面包夹肉饼的快餐",
        "薯条": "炸的长条土豆",
        "可乐": "黑色的碳酸饮料",
        "咖啡": "棕色提神饮品，苦味的",
        "牛奶": "白色的营养饮品",
        "面包": "烤箱烤出来的主食",
        "香蕉": "黄色弯曲的水果",
        "西瓜": "夏天吃的大个圆形水果，红瓤绿皮",
        "草莓": "红色的小水果，表面有籽",
        "葡萄": "一串串的紫色小圆果",
        "樱桃": "红色的小圆水果，有梗",
        "芒果": "热带黄色水果，里面有核",
        "榴莲": "有刺外壳，味道浓郁的热带水果",
        "长颈鹿": "脖子最长的动物",
        "企鹅": "不会飞的黑白鸟，住在南极",
        "熊猫": "黑白相间的熊，爱吃竹子",
        "袋鼠": "肚子上有育儿袋的动物",
        "考拉": "澳大利亚的可爱动物，睡在桉树上",
        # 困难词（成语）
        "海市蜃楼": "大气中由于光线的折射产生的一种自然现象",
        "刻舟求剑": "比喻拘泥成法，不知道变通",
        "守株待兔": "比喻不想努力而希望获得成功",
        "画蛇添足": "比喻做多余的事，反而不恰当",
        "掩耳盗铃": "比喻自己欺骗自己",
        "拔苗助长": "比喻违反事物发展规律，急于求成",
        "井底之蛙": "比喻见识狭窄的人",
        "狐假虎威": "比喻借助别人的威势来吓唬人",
        "亡羊补牢": "比喻出了问题及时补救",
        "杞人忧天": "比喻不必要的忧虑",
        "邯郸学步": "模仿别人却迷失自己",
        "东施效颦": "盲目模仿别人，效果更差",
        "滥竽充数": "没有真才实学的人混在行家里面",
        "自相矛盾": "言行不一致，前后抵触",
        "南辕北辙": "行动和目的相反",
        "杯弓蛇影": "疑神疑鬼，自相惊扰",
        "指鹿为马": "故意颠倒黑白",
        "纸上谈兵": "空谈理论，不能解决实际问题",
        "草木皆兵": "形容惊慌时疑神疑鬼",
        "四面楚歌": "比喻陷入四面受敌的孤立境地",
        "破釜沉舟": "下定决心，不顾一切",
        "卧薪尝胆": "刻苦自励，发愤图强",
        "三顾茅庐": "诚心诚意邀请人才",
        "负荆请罪": "主动认错赔罪"
    }

    DIFFICULTY_CONFIG = {
        "simple": {"score": 2, "stars": "⭐", "name": "简单"},
        "medium": {"score": 3, "stars": "⭐⭐⭐", "name": "中等"},
        "hard": {"score": 5, "stars": "⭐⭐⭐⭐⭐", "name": "困难"}
    }

    WINNING_SCORE = 10
    SAVE_FILE = "/home/xckj/suyuan/backend/word_state.json"

    def __init__(self):
        """初始化游戏状态"""
        self.state = {
            "round": 1,
            "player_score": 0,
            "feifei_score": 0,
            "current_role": "describer",  # describer 或 guesser
            "current_player": "player",   # player 或 feifei
            "current_word": None,
            "current_difficulty": None,
            "used_words": [],
            "game_over": False,
            "winner": None,
            "consecutive_wins": 0  # 连续猜对次数
        }

    def clear_screen(self):
        """清屏"""
        os.system('clear' if os.name == 'posix' else 'cls')

    def save_state(self):
        """保存游戏状态到文件"""
        with open(self.SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def load_state(self):
        """从文件加载游戏状态"""
        if os.path.exists(self.SAVE_FILE):
            with open(self.SAVE_FILE, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
                return True
        return False

    def delete_save(self):
        """删除存档文件"""
        if os.path.exists(self.SAVE_FILE):
            os.remove(self.SAVE_FILE)

    def select_random_word(self):
        """随机选择一个词语"""
        # 随机选择难度（加权：简单40%，中等40%，困难20%）
        difficulty = random.choices(
            ["simple", "medium", "hard"],
            weights=[0.4, 0.4, 0.2]
        )[0]

        # 获取该难度下未使用的词语
        available_words = [
            word for word in self.WORD_LIBRARY[difficulty]
            if word not in self.state["used_words"]
        ]

        # 如果该难度下的词语都用完了，重置已使用列表
        if not available_words:
            # 只重置该难度的已使用词语
            self.state["used_words"] = [
                w for w in self.state["used_words"]
                if w not in self.WORD_LIBRARY[difficulty]
            ]
            available_words = self.WORD_LIBRARY[difficulty]

        word = random.choice(available_words)
        self.state["current_word"] = word
        self.state["current_difficulty"] = difficulty
        self.state["used_words"].append(word)

        return word, difficulty

    def check_description_valid(self, description):
        """检查描述是否包含题目词中的字"""
        if not self.state["current_word"]:
            return True, ""

        forbidden_chars = set(self.state["current_word"])
        found_chars = []

        for char in forbidden_chars:
            if char in description:
                found_chars.append(char)

        if found_chars:
            return False, f"描述中不能包含题目词中的字：{', '.join(found_chars)}"
        return True, ""

    def get_similarity(self, guess, target):
        """计算猜测与目标的相似度"""
        if guess == target:
            return 100

        # 简单的相似度计算：相同字的数量
        common_chars = set(guess) & set(target)
        if common_chars:
            return len(common_chars) * 20
        return 0

    def draw_header(self):
        """绘制游戏头部"""
        return f"""
╔═══════════════════════════════════════════════════════════╗
║         🎯 菲菲猜词大作战                                  ║
║    第 {self.state['round']:2d} 轮  |  你 {self.state['player_score']:2d} : {self.state['feifei_score']:2d} 菲菲    先到{self.WINNING_SCORE}分获胜  ║
╚═══════════════════════════════════════════════════════════╝"""

    def draw_role_info(self):
        """绘制当前角色信息"""
        if self.state["current_player"] == "player":
            player_display = "🟦 你"
        else:
            player_display = "🟩 菲菲"

        if self.state["current_role"] == "describer":
            role_display = "出题人"
        else:
            role_display = "猜词人"

        return f"当前角色：{player_display} → {role_display}"

    def draw_difficulty_info(self):
        """绘制难度信息"""
        if self.state["current_difficulty"]:
            config = self.DIFFICULTY_CONFIG[self.state["current_difficulty"]]
            return f"题目难度：{config['stars']}（{config['name']}，{config['score']}分）"
        return ""

    def draw_game_screen(self, messages=None, input_prompt="", show_progress=False):
        """绘制游戏界面

        Args:
            messages: 要显示的消息列表，每个元素是 (content, type) 元组
                     type可以是: 'info', 'success', 'error', 'warning'
            input_prompt: 输入提示
            show_progress: 是否显示进度条
        """
        self.clear_screen()
        print(self.draw_header())
        print()
        print(self.draw_role_info())

        difficulty_info = self.draw_difficulty_info()
        if difficulty_info:
            print(difficulty_info)

        if show_progress and self.state["consecutive_wins"] > 0:
            print(f"🔥 连续猜对：{self.state['consecutive_wins']} 次")

        print()
        print("─" * 58)
        print()

        # 显示消息
        if messages:
            for content, msg_type in messages:
                prefix = {
                    'info': '💬',
                    'success': '✅',
                    'error': '❌',
                    'warning': '⚠️',
                    'hint': '💡',
                    'feifei': '🐱'
                }.get(msg_type, '  ')
                print(f"{prefix} {content}")

        print()

        if input_prompt:
            print(input_prompt, end='', flush=True)

    def feifei_guess(self, description, word):
        """菲菲猜词（AI）

        Args:
            description: 玩家的描述
            word: 正确答案
        """
        difficulty = self.state["current_difficulty"]

        # 基础猜对概率
        base_chance = {"simple": 0.7, "medium": 0.5, "hard": 0.3}
        chance = base_chance[difficulty]

        # 连续猜对增加难度
        if self.state["consecutive_wins"] > 0:
            chance -= 0.1 * self.state["consecutive_wins"]

        # 模拟思考时间
        time.sleep(1)

        # 判断是否猜对
        if random.random() < chance:
            self.state["consecutive_wins"] += 1
            return word, True
        else:
            self.state["consecutive_wins"] = 0
            # 生成错误答案
            all_words = (self.WORD_LIBRARY["simple"] +
                        self.WORD_LIBRARY["medium"] +
                        self.WORD_LIBRARY["hard"])
            wrong_guesses = [w for w in all_words if w != word]

            # 有概率返回相似的字（增加游戏趣味性）
            if random.random() < 0.3 and word:
                # 返回一个包含相同字的不同词
                same_char_words = [w for w in wrong_guesses
                                 if any(c in w for c in word)]
                if same_char_words:
                    return random.choice(same_char_words), False

            return random.choice(wrong_guesses), False

    def player_describe_turn(self):
        """玩家出题回合"""
        word, difficulty = self.select_random_word()
        score = self.DIFFICULTY_CONFIG[difficulty]["score"]

        while True:
            self.draw_game_screen(
                messages=[
                    (f"你的题目是：【{word}】", "info"),
                    ("请用文字描述这个词，但不能说出词中的任何一个字！", "warning"),
                    ("菲菲会根据你的描述来猜词", "hint")
                ],
                input_prompt="你的描述："
            )

            description = input().strip()

            if not description:
                self.draw_game_screen(
                    messages=[("描述不能为空！", "error")],
                    input_prompt="按回车继续..."
                )
                input()
                continue

            # 检查是否包含题目词中的字
            valid, msg = self.check_description_valid(description)
            if not valid:
                self.draw_game_screen(
                    messages=[(msg, "error")],
                    input_prompt="按回车重试..."
                )
                input()
                continue

            # 菲菲猜词
            self.draw_game_screen(
                messages=[
                    (f"你的描述：{description}", "info"),
                    ("菲菲正在思考...", "feifei")
                ]
            )

            guess, is_correct = self.feifei_guess(description, word)

            if is_correct:
                self.state["player_score"] += score
                self.draw_game_screen(
                    messages=[
                        (f"菲菲猜对了：【{guess}】", "success"),
                        (f"你获得 {score} 分！", "success"),
                        (f"当前比分：你 {self.state['player_score']} : {self.state['feifei_score']} 菲菲", "info")
                    ],
                    input_prompt="按回车继续..."
                )
                input()

                # 检查是否获胜
                if self.check_game_over():
                    return

                # 继续出题
                word, difficulty = self.select_random_word()
                score = self.DIFFICULTY_CONFIG[difficulty]["score"]
            else:
                self.draw_game_screen(
                    messages=[
                        (f"菲菲猜：【{guess}】", "feifei"),
                        ("猜错了！", "error"),
                        (f"正确答案是：【{word}】", "info"),
                        ("换角色，现在轮到菲菲出题了！", "warning")
                    ],
                    input_prompt="按回车继续..."
                )
                input()

                # 换角色
                self.state["current_role"] = "guesser"
                self.state["current_player"] = "player"
                self.state["consecutive_wins"] = 0
                break

        self.save_state()

    def player_guess_turn(self):
        """玩家猜词回合"""
        # 菲菲出题
        word, difficulty = self.select_random_word()
        score = self.DIFFICULTY_CONFIG[difficulty]["score"]

        # 获取预设描述，如果没有则生成通用描述
        if word in self.DESCRIPTIONS:
            description = self.DESCRIPTIONS[word]
        else:
            # 生成通用描述
            char_count = len(word)
            description = f"这是一个{char_count}个字的词语"
            if difficulty == "hard":
                description += "，是一个成语"

        max_attempts = 3
        attempts = 0

        while attempts < max_attempts:
            remaining = max_attempts - attempts
            self.draw_game_screen(
                messages=[
                    ("菲菲出题啦！", "feifei"),
                    (f"菲菲的描述：{description}", "info"),
                    (f"难度：{self.DIFFICULTY_CONFIG[difficulty]['name']}", "hint"),
                    (f"分值：{score}分", "hint"),
                    (f"剩余机会：{remaining} 次", "warning")
                ],
                show_progress=True
            )

            if attempts > 0:
                print("─" * 58)
                print()

            guess = input("你的猜测：").strip()
            attempts += 1

            if not guess:
                attempts -= 1
                continue

            if guess == word:
                self.state["player_score"] += score
                self.state["consecutive_wins"] += 1

                self.draw_game_screen(
                    messages=[
                        (f"猜对了！答案是：【{word}】", "success"),
                        (f"你获得 {score} 分！", "success"),
                        (f"当前比分：你 {self.state['player_score']} : {self.state['feifei_score']} 菲菲", "info")
                    ],
                    input_prompt="按回车继续...",
                    show_progress=True
                )
                input()

                # 检查是否获胜
                if self.check_game_over():
                    return

                # 继续猜词
                word, difficulty = self.select_random_word()
                score = self.DIFFICULTY_CONFIG[difficulty]["score"]

                if word in self.DESCRIPTIONS:
                    description = self.DESCRIPTIONS[word]
                else:
                    char_count = len(word)
                    description = f"这是一个{char_count}个字的词语"
                    if difficulty == "hard":
                        description += "，是一个成语"

                attempts = 0
            else:
                # 计算相似度，给出提示
                similarity = self.get_similarity(guess, word)

                if attempts < max_attempts:
                    if similarity > 0:
                        hint_msg = f"接近了！有一些字是对的"
                    else:
                        hint_msg = "再想想，完全不对哦"

                    self.draw_game_screen(
                        messages=[
                            (f"你的猜测：【{guess}】", "info"),
                            ("猜错了！", "error"),
                            (hint_msg, "hint")
                        ],
                        input_prompt="按回车继续..."
                    )
                    input()
                else:
                    self.draw_game_screen(
                        messages=[
                            (f"你的猜测：【{guess}】", "info"),
                            ("次数用尽！", "error"),
                            (f"正确答案是：【{word}】", "info"),
                            ("换角色，现在轮到你出题了！", "warning")
                        ],
                        input_prompt="按回车继续..."
                    )
                    input()

                    # 换角色
                    self.state["current_role"] = "describer"
                    self.state["current_player"] = "player"
                    self.state["consecutive_wins"] = 0
                    break

        self.save_state()

    def check_game_over(self):
        """检查游戏是否结束"""
        if self.state["player_score"] >= self.WINNING_SCORE:
            self.state["game_over"] = True
            self.state["winner"] = "player"
            return True
        elif self.state["feifei_score"] >= self.WINNING_SCORE:
            self.state["game_over"] = True
            self.state["winner"] = "feifei"
            return True
        return False

    def show_game_over(self):
        """显示游戏结束画面"""
        self.clear_screen()
        print(self.draw_header())
        print()
        print("─" * 58)
        print()

        if self.state["winner"] == "player":
            print("🏆🏆🏆 恭喜你！你赢了！🏆🏆🏆")
            print()
            print("     你真厉害！菲菲甘拜下风！")
        else:
            print("😢😢😢 很遗憾，菲菲赢了！😢😢😢")
            print()
            print("     别灰心，再来一局吧！")

        print()
        print(f"最终比分：你 {self.state['player_score']} : {self.state['feifei_score']} 菲菲")
        print(f"总轮数：{self.state['round']} 轮")
        print()
        print("─" * 58)
        print()
        print("感谢游玩《菲菲猜词大作战》！")
        print()

    def show_main_menu(self):
        """显示主菜单"""
        while True:
            self.clear_screen()
            print()
            print("╔═══════════════════════════════════════════════════════════╗")
            print("║         🎯 菲菲猜词大作战                                  ║")
            print("║                                                            ║")
            print("║         一个有趣的双人猜词对战游戏                         ║")
            print("║                                                            ║")
            print("╚═══════════════════════════════════════════════════════════╝")
            print()
            print("─────────────────────────────────────────────────────────────")
            print()
            print("  📖 游戏规则：")
            print("     • 出题人：看到题目词，用文字描述（不能说出词中的字）")
            print("     • 猜词人：根据描述猜词")
            print("     • 猜对得分，猜错换人出题")
            print("     • 先到 10 分者获胜")
            print()
            print("─────────────────────────────────────────────────────────────")
            print()
            print("  🎮 主菜单：")
            print("     1. 开始新游戏")
            print("     2. 继续游戏（如果有存档）")
            print("     3. 退出")
            print()
            print("─────────────────────────────────────────────────────────────")
            print()

            choice = input("请选择 (1-3): ").strip()

            if choice == "1":
                return "new"
            elif choice == "2":
                if os.path.exists(self.SAVE_FILE):
                    return "continue"
                else:
                    print("⚠️ 没有找到存档文件！")
                    time.sleep(1.5)
            elif choice == "3":
                return "exit"
            else:
                print("⚠️ 无效的选择，请重新输入！")
                time.sleep(1)

    def start_new_game(self):
        """开始新游戏"""
        self.state = {
            "round": 1,
            "player_score": 0,
            "feifei_score": 0,
            "current_role": "describer",
            "current_player": "player",
            "current_word": None,
            "current_difficulty": None,
            "used_words": [],
            "game_over": False,
            "winner": None,
            "consecutive_wins": 0
        }
        self.save_state()
        self.run()

    def run(self):
        """运行游戏主循环"""
        while not self.state["game_over"]:
            if self.state["current_player"] == "player":
                if self.state["current_role"] == "describer":
                    self.player_describe_turn()
                else:
                    self.player_guess_turn()

            # 检查游戏是否结束
            if self.check_game_over():
                self.show_game_over()
                self.delete_save()
                break

            # 增加轮数
            self.state["round"] += 1
            self.save_state()


def main():
    """主函数"""
    game = WordGame()

    while True:
        action = game.show_main_menu()

        if action == "exit":
            print("再见！")
            break
        elif action == "new":
            game.start_new_game()
        elif action == "continue":
            game.load_state()
            if game.state["game_over"]:
                game.show_game_over()
                game.delete_save()
            else:
                print(f"继续游戏：第{game.state['round']}轮")
                print(f"当前比分：你{game.state['player_score']}:{game.state['feifei_score']}菲菲")
                time.sleep(1.5)
                game.run()


if __name__ == "__main__":
    main()
