"""
使用Playwright Codegen - 证书问题解决版

由于直接运行codegen会报证书错误，我们用脚本方式
"""
import subprocess
import sys

# 方案1: 忽略证书的命令
cmd = [
    "playwright",
    "codegen",
    "--channel=chrome",
    "--lang=python",
    "http://10.10.10.158"
]

# 设置环境变量忽略证书
import os
os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
os.environ["NODE_SKIP_TLS_VALIDATION"] = "1"

print("启动 Playwright Codegen (忽略证书)...")
print("如果仍然失败，请使用以下方法：")
print("")
print("方法1: 手动打开浏览器后附加")
print("  1. 先用Chrome打开 http://10.10.10.158")
print("  2. 点击'高级' -> '继续访问'")
print("  3. 然后运行: playwright codegen --channel=chrome --connect-existing http://10.10.10.158")
print("")
print("方法2: 使用临时脚本")
print("  python run_codegen.py")
print("")

try:
    subprocess.run(cmd, check=True)
except subprocess.CalledProcessError as e:
    print(f"\n错误: {e}")
    print("\n建议使用方法1（手动打开后附加）")
