# 《菲菲探险记》使用说明

## 游戏简介
一个文字冒险探索游戏，玩家在神秘岛屿上寻找宝藏。适合通过微信等"消息中间人"模式游玩。

## 快速开始

### 1. 开始新游戏
```bash
python3 /home/xckj/suyuan/games/adventure.py --new 玩家名字
```

### 2. 移动角色
```bash
python3 /home/xckj/suyuan/games/adventure.py --move 游戏ID up
python3 /home/xckj/suyuan/games/adventure.py --move 游戏ID down
python3 /home/xckj/suyuan/games/adventure.py --move 游戏ID left
python3 /home/xckj/suyuan/games/adventure.py --move 游戏ID right
```

### 3. 查看状态
```bash
python3 /home/xckj/suyuan/games/adventure.py --status 游戏ID
```

### 4. 查看地图
```bash
python3 /home/xckj/suyuan/games/adventure.py --map 游戏ID
```

### 5. 列出所有存档
```bash
python3 /home/xckj/suyuan/games/adventure.py --list
```

## 游戏元素

| 图标 | 名称 | 说明 |
|------|------|------|
| 🧑 | 玩家 | 你的当前位置 |
| 🌲 | 森林 | 可能遇到友好动物或找到浆果 |
| 🌊 | 河流 | 需要"小船"物品才能通过 |
| ⛰️ | 山洞 | 可能发现宝藏或危险 |
| 📦 | 宝箱 | 传说中的宝藏，找到即胜利！ |
| ⬜ | 空地 | 安全的空地 |
| ⬛ | 未探索 | 尚未探索的区域 |

## 游戏提示

1. **河流阻挡**：没有"小船"无法通过河流，需要在森林或山洞中寻找
2. **随机事件**：每个格子首次进入会触发随机事件
3. **生命值**：某些事件会扣除生命值，生命值归零则游戏失败
4. **胜利条件**：找到宝箱即可获胜

## 存档位置
`/home/xckj/suyuan/games/saves/游戏ID.json`
