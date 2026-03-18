"""
Vue3迁移自动化脚本
自动完成从React到Vue3的组件迁移
"""
import os
import shutil
from pathlib import Path

# 项目路径
REACT_SRC = r"D:\溯源\frontend\src"
VUE_SRC = r"D:\溯源\frontend-vue\src"

print("🚀 开始Vue3迁移任务...")

# 1. 复制可复用资源
print("\n📦 阶段1: 复制可复用资源...")
shutil.copy(f"{REACT_SRC}/types/api.ts", f"{VUE_SRC}/types/api.ts")
shutil.copy(f"{REACT_SRC}/services/api.ts", f"{VUE_SRC}/services/api.ts")
shutil.copytree(f"{REACT_SRC}/styles", f"{VUE_SRC}/styles", dirs_exist_ok=True)
print("✅ 资源复制完成")

# 2. 复制示例代码
print("\n📦 阶段2: 复制Vue3示例组件...")
VUE_EXAMPLES = r"D:\溯源\vue3-examples"

# 复制组件
components_to_copy = [
    "KpiStrip.vue",
    "ChartsPanel.vue",
    "MapPanel.vue"
]

for comp in components_to_copy:
    src = f"{VUE_EXAMPLES}/components/{comp}"
    dst = f"{VUE_SRC}/components/{comp}"
    if os.path.exists(src):
        shutil.copy(src, dst)
        print(f"  ✅ {comp}")

# 复制Composables
shutil.copy(f"{VUE_EXAMPLES}/composables/useAMapLoader.ts",
           f"{VUE_SRC}/composables/useAMapLoader.ts")
print("  ✅ useAMapLoader.ts")

# 复制Stores
shutil.copy(f"{VUE_EXAMPLES}/stores/analysis.ts",
           f"{VUE_SRC}/stores/analysis.ts")
print("  ✅ analysis.ts (Pinia Store)")

# 复制App.vue
shutil.copy(f"{VUE_EXAMPLES}/App.vue", f"{VUE_SRC}/App.vue")
print("  ✅ App.vue")

print("\n✅ 所有基础组件复制完成!")
print("\n⏭️  接下来需要手动迁移剩余组件...")
print("   请参考 VUE3_MIGRATION_PLAN.md 继续迁移")
