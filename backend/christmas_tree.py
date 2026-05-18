#!/usr/bin/env python3
"""打印一棵圣诞树"""

def print_christmas_tree(height=10):
    """打印一棵ASCII圣诞树"""
    # 树冠
    for i in range(height):
        spaces = ' ' * (height - i - 1)
        stars = '*' * (2 * i + 1)
        print(spaces + stars)

    # 树干
    trunk_width = 3
    trunk_height = 3
    trunk_spaces = ' ' * (height - trunk_width // 2 - 1)
    for _ in range(trunk_height):
        print(trunk_spaces + '|' * trunk_width)

    # 树根装饰
    root_spaces = ' ' * (height - 2)
    print(root_spaces + '~' * 3)

if __name__ == '__main__':
    print_christmas_tree(12)
