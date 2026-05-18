#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《猜词传递》游戏
小智（AI出题）→ 菲菲（传递）→ 用户（猜词）
"""

import json
import random
import os
import sys
from pathlib import Path


# 词库与描述库
WORD_LIBRARY = {
    "simple": [  # 2分
        {"word": "苹果", "desc": "一种圆形的水果，通常是红色或绿色的，口感脆甜", "hints": ["长在树上", "白雪公主吃了之后睡着了"]},
        {"word": "太阳", "desc": "天空中最亮的星，给地球带来光和热", "hints": ["东升西落", "它是恒星"]},
        {"word": "月亮", "desc": "夜空中最亮的天体，形状会变化", "hints": ["中秋节的象征", "上面住着嫦娥"]},
        {"word": "电脑", "desc": "一种电子设备，可以上网、玩游戏、办公", "hints": ["有键盘和显示器", "需要通电才能用"]},
        {"word": "书本", "desc": "记录知识的载体，有很多页", "hints": ["用纸做的", "可以阅读"]},
        {"word": "水杯", "desc": "用来装水的容器", "hints": ["通常是圆柱形", "有把手"]},
        {"word": "钥匙", "desc": "用来开门的小金属片", "hints": ["挂在钥匙扣上", "可以锁门"]},
        {"word": "眼镜", "desc": "戴在眼睛上帮助看清东西", "hints": ["有镜片和镜框", "近视的人需要"]},
        {"word": "手表", "desc": "戴在手腕上看时间", "hints": ["有时针分针", "会滴答滴答响"]},
        {"word": "铅笔", "desc": "用来写字的文具，可以擦掉", "hints": ["有橡皮擦", "需要削尖"]},
        {"word": "椅子", "desc": "用来坐的家具", "hints": ["有四条腿", "有靠背"]},
        {"word": "鞋子", "desc": "穿在脚上走路", "hints": ["有鞋带", "分左右脚"]},
        {"word": "雨伞", "desc": "下雨时用来挡雨", "hints": ["可以折叠", "打开是圆形的"]},
        {"word": "书包", "desc": "学生用来装书的包", "hints": ["背在背上", "有拉链"]},
        {"word": "牙刷", "desc": "早上用来刷牙的工具", "hints": ["有刷毛", "配合牙膏使用"]},
        {"word": "毛巾", "desc": "用来擦脸或擦手", "hints": ["通常是棉质的", "洗脸后用"]},
        {"word": "冰箱", "desc": "用来冷藏食物的电器", "hints": ["可以制冰", "门可以打开"]},
        {"word": "电视", "desc": "用来看节目的电器", "hints": ["有遥控器", "可以换台"]},
        {"word": "手机", "desc": "可以打电话上网的设备", "hints": ["触摸屏幕", "随身携带"]},
        {"word": "西瓜", "desc": "夏天吃的大水果，外绿内红", "hints": ["有很多籽", "口感清甜"]},
    ],
    "medium": [  # 3分
        {"word": "望远镜", "desc": "用来看远处物体的光学仪器", "hints": ["有两个镜筒", "可以调节焦距"]},
        {"word": "照相机", "desc": "用来拍照的设备", "hints": ["有镜头", "可以保存照片"]},
        {"word": "自行车", "desc": "两个轮子的交通工具", "hints": ["需要脚蹬", "有链条"]},
        {"word": "冰淇淋", "desc": "夏天吃的冷饮甜品", "hints": ["通常是甜的", "会融化"]},
        {"word": "钢琴", "desc": "有黑白键的大型乐器", "hints": ["有88个键", "可以弹奏乐曲"]},
        {"word": "足球", "desc": "两队各11人踢的球类运动", "hints": ["用脚踢", "不能用手"]},
        {"word": "羽毛球", "desc": "用拍子打的白色小球", "hints": ["有羽毛", "需要网"]},
        {"word": "电梯", "desc": "在楼房里垂直运输的工具", "hints": ["有按钮", "可以上下楼"]},
        {"word": "红绿灯", "desc": "指挥交通的信号灯", "hints": ["有三种颜色", "红停绿行"]},
        {"word": "打印机", "desc": "把电脑里的文件打印出来的设备", "hints": ["需要墨水或墨粉", "有纸张"]},
        {"word": "计算器", "desc": "用来计算的电子工具", "hints": ["有数字键", "可以加减乘除"]},
        {"word": "微波炉", "desc": "用来快速加热食物的电器", "hints": ["会产生微波", "不能放金属"]},
        {"word": "洗衣机", "desc": "用来洗衣服的电器", "hints": ["有滚筒", "需要水和洗衣粉"]},
        {"word": "空调", "desc": "调节室内温度的电器", "hints": ["可以制冷制热", "有遥控器"]},
        {"word": "热水器", "desc": "用来烧热水的设备", "hints": ["连接水龙头", "洗澡前开"]},
    ],
    "hard": [  # 5分
        {"word": "海市蜃楼", "desc": "一种大气光学现象，远处景物看起来在空中", "hints": ["沙漠常见", "是虚幻的影像"]},
        {"word": "刻舟求剑", "desc": "比喻死守教条，不知变通", "hints": ["是一个成语", "源于《吕氏春秋》"]},
        {"word": "守株待兔", "desc": "比喻妄想不劳而获", "hints": ["是一个成语", "关于农夫和兔子"]},
        {"word": "画蛇添足", "desc": "比喻做了多余的事", "hints": ["是一个成语", "蛇本来没有脚"]},
        {"word": "掩耳盗铃", "desc": "比喻自己欺骗自己", "hints": ["是一个成语", "偷铃铛捂住耳朵"]},
        {"word": "井底之蛙", "desc": "比喻见识短浅的人", "hints": ["是一个成语", "关于青蛙"]},
        {"word": "狐假虎威", "desc": "比喻借别人的威势吓唬人", "hints": ["是一个成语", "狐狸和老虎"]},
        {"word": "拔苗助长", "desc": "比喻急于求成反而坏事", "hints": ["是一个成语", "关于农夫和禾苗"]},
        {"word": "亡羊补牢", "desc": "比喻出了问题及时补救", "hints": ["是一个成语", "羊丢了修羊圈"]},
        {"word": "杯弓蛇影", "desc": "比喻疑神疑鬼自相惊扰", "hints": ["是一个成语", "把弓影当成蛇"]},
        {"word": "胸有成竹", "desc": "比喻做事之前已经有计划", "hints": ["是一个成语", "关于画竹子"]},
        {"word": "指鹿为马", "desc": "比喻故意颠倒黑白", "hints": ["是一个成语", "赵高的故事"]},
        {"word": "程门立雪", "desc": "比喻尊敬师长", "hints": ["是一个成语", "学生站在雪中等老师"]},
        {"word": "卧薪尝胆", "desc": "比喻刻苦自励", "hints": ["是一个成语", "越王勾践的故事"]},
        {"word": "三顾茅庐", "desc": "比喻诚心诚意邀请", "hints": ["是一个成语", "刘备请诸葛亮"]},
        {"word": "闻鸡起舞", "desc": "比喻有志报国及时奋起", "hints": ["是一个成语", "听到鸡叫就练剑"]},
        {"word": "悬梁刺股", "desc": "形容刻苦学习", "hints": ["是一个成语", "古人读书提神的方法"]},
        {"word": "磨杵成针", "desc": "比喻只要有恒心就能成功", "hints": ["是一个成语", "要把铁棒磨成针"]},
        {"word": "盲人摸象", "desc": "比喻看问题不全面", "hints": ["是一个成语", "盲人摸大象"]},
        {"word": "朝三暮四", "desc": "比喻反复无常", "hints": ["是一个成语", "猴子分栗子"]},
    ]
}

SCORES = {"simple": 2, "medium": 3, "hard": 5}
WINNING_SCORE = 8
STATE_FILE = Path("/home/xckj/suyuan/backend/guess_state.json")


class GameState:
    def __init__(self):
        self.score = 0
        self.round_num = 1
        self.current_word = None
        self.current_difficulty = None
        self.current_hints_used = 0
        self.wrong_guesses = []
        self.game_over = False
        self.used_words = set()

    def to_dict(self):
        return {
            "score": self.score,
            "round_num": self.round_num,
            "current_word": self.current_word,
            "current_difficulty": self.current_difficulty,
            "current_hints_used": self.current_hints_used,
            "wrong_guesses": self.wrong_guesses,
            "game_over": self.game_over,
            "used_words": list(self.used_words)
        }

    @classmethod
    def from_dict(cls, data):
        state = cls()
        state.score = data.get("score", 0)
        state.round_num = data.get("round_num", 1)
        state.current_word = data.get("current_word")
        state.current_difficulty = data.get("current_difficulty")
        state.current_hints_used = data.get("current_hints_used", 0)
        state.wrong_guesses = data.get("wrong_guesses", [])
        state.game_over = data.get("game_over", False)
        state.used_words = set(data.get("used_words", []))
        return state

    def save(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls):
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        return cls()

    def delete(self):
        if STATE_FILE.exists():
            STATE_FILE.unlink()


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def draw_header(state):
    """绘制游戏顶部标题栏"""
    print("╔" + "═" * 63 + "╗")
    print("║" + " " * 20 + "🎯 猜词传递" + " " * 29 + "║")
    round_info = f"第 {state.round_num} 轮  |  得分：🟦 你 {state.score} / {WINNING_SCORE}"
    print("║" + " " * 15 + round_info + " " * (63 - len(round_info) - 15) + "║")
    print("╚" + "═" * 63 + "╝")
    print()


def draw_description(word_data, hints_used):
    """绘制小智的描述区域"""
    print("🟩 小智的描述：")
    print("─" * 63)
    print(word_data["desc"])
    print("─" * 63)
    print()

    if hints_used > 0:
        print("💡 提示：")
        for i in range(min(hints_used, len(word_data["hints"]))):
            print(f"   {i + 1}. {word_data['hints'][i]}")
        print()


def draw_wrong_guesses(wrong_guesses):
    """绘制错误猜测"""
    if wrong_guesses:
        print("❌ 错误猜测：" + "、".join(wrong_guesses))
        print()


def draw_input_prompt():
    """绘制输入提示"""
    print("🟦 请输入你的答案：", end="", flush=True)


def draw_commands():
    """绘制可用命令提示"""
    print()
    print("💬 可用命令：")
    print("   • 直接输入答案进行猜词")
    print("   • '提示' - 获取更多提示")
    print("   • '跳过' - 跳过当前词")
    print("   • '状态' - 查看当前得分")
    print("   • '退出' - 退出游戏")
    print()


def select_random_word(state):
    """随机选择一个词"""
    all_words = []
    for difficulty, words in WORD_LIBRARY.items():
        for word_data in words:
            if word_data["word"] not in state.used_words:
                all_words.append((difficulty, word_data))

    if not all_words:
        return None, None

    difficulty, word_data = random.choice(all_words)
    return difficulty, word_data


def process_guess(user_input, current_word):
    """处理用户猜测"""
    # 去除空格和标点
    guess = user_input.strip()
    return guess == current_word


def show_victory(state):
    """显示胜利画面"""
    clear_screen()
    print("╔" + "═" * 63 + "╗")
    print("║" + " " * 18 + "🎉 恭喜你获胜！🎉" + " " * 21 + "║")
    print("║" + " " * 23 + f"最终得分：{state.score}" + " " * 22 + "║")
    print("╚" + "═" * 63 + "╝")
    print()
    print("🎊 太棒了！你已经猜对了足够的词语！")
    print()
    input("按回车键继续...")


def show_word_reveal(word_data, difficulty):
    """显示答案揭晓"""
    score = SCORES[difficulty]
    print(f"✅ 正确！答案是：『{word_data['word']}』")
    print(f"   +{score} 分！")
    print()


def show_skip(word_data):
    """显示跳过信息"""
    print(f"⏭️  已跳过。答案是：『{word_data['word']}』")
    print()


def main():
    # 加载或创建游戏状态
    state = GameState.load()

    if state.game_over or state.score >= WINNING_SCORE:
        state.delete()
        state = GameState()

    if state.current_word is None:
        # 选择新词
        difficulty, word_data = select_random_word(state)
        if difficulty is None:
            print("🎊 恭喜！你已经猜完了所有词语！")
            return
        state.current_difficulty = difficulty
        state.current_word = word_data
        state.current_hints_used = 0
        state.wrong_guesses = []
        state.used_words.add(word_data["word"])

    while True:
        clear_screen()
        draw_header(state)

        if state.score >= WINNING_SCORE:
            show_victory(state)
            state.delete()
            break

        # 绘制当前词的描述
        word_data = state.current_word
        draw_description(word_data, state.current_hints_used)
        draw_wrong_guesses(state.wrong_guesses)
        draw_input_prompt()

        # 读取用户输入
        user_input = input().strip()

        # 处理命令
        if user_input in ["退出", "exit", "quit", "q"]:
            state.save()
            print()
            print("👋 游戏已保存，下次继续！")
            break

        elif user_input in ["状态", "status"]:
            print()
            print(f"📊 当前得分：{state.score} / {WINNING_SCORE}")
            print(f"🔢 当前轮数：第 {state.round_num} 轮")
            print(f"📝 已猜词数：{len(state.used_words)}")
            input("按回车键继续...")

        elif user_input in ["提示", "hint", "h"]:
            max_hints = len(word_data["hints"])
            if state.current_hints_used < max_hints:
                state.current_hints_used += 1
                print()
                print(f"💡 已显示提示 {state.current_hints_used}/{max_hints}")
            else:
                print()
                print("⚠️  没有更多提示了！")
            input("按回车键继续...")

        elif user_input in ["跳过", "skip", "s"]:
            show_skip(word_data)
            state.round_num += 1
            state.current_word = None
            state.current_difficulty = None
            state.current_hints_used = 0
            state.wrong_guesses = []
            state.save()

            # 选择新词
            difficulty, new_word_data = select_random_word(state)
            if difficulty is None:
                print("🎊 恭喜！你已经猜完了所有词语！")
                input("按回车键退出...")
                break
            state.current_difficulty = difficulty
            state.current_word = new_word_data
            state.current_hints_used = 0
            state.wrong_guesses = []
            state.used_words.add(new_word_data["word"])
            state.save()

        elif user_input:
            # 处理猜测
            # 移除 "猜：" 前缀
            guess = user_input
            if guess.startswith("猜:") or guess.startswith("猜："):
                guess = guess[2:].strip()

            if process_guess(guess, word_data["word"]):
                # 猜对了
                show_word_reveal(word_data, state.current_difficulty)
                state.score += SCORES[state.current_difficulty]
                state.round_num += 1
                state.current_word = None
                state.current_difficulty = None
                state.current_hints_used = 0
                state.wrong_guesses = []
                state.save()

                if state.score >= WINNING_SCORE:
                    state.delete()
                    show_victory(state)
                    break

                # 选择新词
                difficulty, new_word_data = select_random_word(state)
                if difficulty is None:
                    print("🎊 恭喜！你已经猜完了所有词语！")
                    input("按回车键退出...")
                    break
                state.current_difficulty = difficulty
                state.current_word = new_word_data
                state.current_hints_used = 0
                state.wrong_guesses = []
                state.used_words.add(new_word_data["word"])
                state.save()

                input("按回车键继续下一轮...")
            else:
                # 猜错了
                if guess not in state.wrong_guesses:
                    state.wrong_guesses.append(guess)
                state.save()
                print()
                print("❌ 不对哦，再想想！")
                input("按回车键继续...")


if __name__ == "__main__":
    main()
