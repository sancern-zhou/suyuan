#!/bin/bash

echo "============================================================"
echo "图表模式配置验证"
echo "============================================================"

FAILED=0

# 测试 1: 检查 charts 目录
echo ""
echo "============================================================"
echo "测试 1: Charts 目录"
echo "============================================================"

CHARTS_DIR="/home/xckj/suyuan/backend_data_registry/charts"

if [ -d "$CHARTS_DIR" ]; then
    echo "✅ Charts 目录存在: $CHARTS_DIR"
    if [ -w "$CHARTS_DIR" ]; then
        echo "✅ Charts 目录可写"
    else
        echo "❌ Charts 目录不可写"
        FAILED=$((FAILED + 1))
    fi
else
    echo "❌ Charts 目录不存在"
    FAILED=$((FAILED + 1))
fi

# 测试 2: 检查 chart_prompt.py 文件
echo ""
echo "============================================================"
echo "测试 2: chart_prompt.py 文件"
echo "============================================================"

CHART_PROMPT_FILE="/home/xckj/suyuan/backend/app/agent/prompts/chart_prompt.py"

if [ -f "$CHART_PROMPT_FILE" ]; then
    echo "✅ chart_prompt.py 文件存在"

    # 检查关键内容
    KEYWORDS=(
        "数据可视化专家"
        "read_data_registry"
        "execute_python"
        "CHART_SAVED"
        "matplotlib.use('Agg')"
        "build_chart_prompt"
    )

    for keyword in "${KEYWORDS[@]}"; do
        if grep -q "$keyword" "$CHART_PROMPT_FILE"; then
            echo "✅ 包含关键词: $keyword"
        else
            echo "❌ 缺少关键词: $keyword"
            FAILED=$((FAILED + 1))
        fi
    done
else
    echo "❌ chart_prompt.py 文件不存在"
    FAILED=$((FAILED + 1))
fi

# 测试 3: 检查 tool_registry.py 中的 CHART_TOOLS
echo ""
echo "============================================================"
echo "测试 3: tool_registry.py 中的 CHART_TOOLS"
echo "============================================================"

TOOL_REGISTRY_FILE="/home/xckj/suyuan/backend/app/agent/prompts/tool_registry.py"

if [ -f "$TOOL_REGISTRY_FILE" ]; then
    echo "✅ tool_registry.py 文件存在"

    # 检查 CHART_TOOLS 定义
    if grep -q "CHART_TOOLS = {" "$TOOL_REGISTRY_FILE"; then
        echo "✅ CHART_TOOLS 已定义"

        # 检查关键工具
        CHART_TOOLS_KEYWORDS=(
            "query_gd_suncere_city_hour"
            "query_gd_suncere_city_day_new"
            "read_data_registry"
            "execute_python"
            "read_file"
            "write_file"
        )

        for tool in "${CHART_TOOLS_KEYWORDS[@]}"; do
            if grep -q "\"$tool\"" "$TOOL_REGISTRY_FILE"; then
                echo "✅ 包含工具: $tool"
            else
                echo "❌ 缺少工具: $tool"
                FAILED=$((FAILED + 1))
            fi
        done
    else
        echo "❌ CHART_TOOLS 未定义"
        FAILED=$((FAILED + 1))
    fi

    # 检查 get_tools_by_mode 函数是否支持 chart
    if grep -q 'mode == "chart"' "$TOOL_REGISTRY_FILE"; then
        echo "✅ get_tools_by_mode 支持 chart 模式"
    else
        echo "❌ get_tools_by_mode 不支持 chart 模式"
        FAILED=$((FAILED + 1))
    fi
else
    echo "❌ tool_registry.py 文件不存在"
    FAILED=$((FAILED + 1))
fi

# 测试 4: 检查 prompt_builder.py 是否支持图表模式
echo ""
echo "============================================================"
echo "测试 4: prompt_builder.py 图表模式支持"
echo "============================================================"

PROMPT_BUILDER_FILE="/home/xckj/suyuan/backend/app/agent/prompts/prompt_builder.py"

if [ -f "$PROMPT_BUILDER_FILE" ]; then
    echo "✅ prompt_builder.py 文件存在"

    # 检查导入 chart_prompt
    if grep -q "from .chart_prompt import" "$PROMPT_BUILDER_FILE"; then
        echo "✅ 导入 chart_prompt"
    else
        echo "❌ 未导入 chart_prompt"
        FAILED=$((FAILED + 1))
    fi

    # 检查 AgentMode 包含 chart
    if grep -q '"chart"' "$PROMPT_BUILDER_FILE" || grep -q "'chart'" "$PROMPT_BUILDER_FILE"; then
        echo "✅ AgentMode 包含 'chart'"
    else
        echo "❌ AgentMode 不包含 'chart'"
        FAILED=$((FAILED + 1))
    fi

    # 检查 build_react_system_prompt 支持 chart
    if grep -q 'mode == "chart"' "$PROMPT_BUILDER_FILE"; then
        echo "✅ build_react_system_prompt 支持 chart 模式"
    else
        echo "❌ build_react_system_prompt 不支持 chart 模式"
        FAILED=$((FAILED + 1))
    fi
else
    echo "❌ prompt_builder.py 文件不存在"
    FAILED=$((FAILED + 1))
fi

# 测试 5: 检查 execute_python_tool.py 的图表支持
echo ""
echo "============================================================"
echo "测试 5: execute_python_tool.py 图表支持"
echo "============================================================"

EXECUTE_PYTHON_FILE="/home/xckj/suyuan/backend/app/tools/utility/execute_python_tool.py"

if [ -f "$EXECUTE_PYTHON_FILE" ]; then
    echo "✅ execute_python_tool.py 文件存在"

    # 检查 CHARTS_DIR 定义
    if grep -q "CHARTS_DIR" "$EXECUTE_PYTHON_FILE"; then
        echo "✅ CHARTS_DIR 已定义"
    else
        echo "❌ CHARTS_DIR 未定义"
        FAILED=$((FAILED + 1))
    fi

    # 检查 _extract_chart_paths 方法
    if grep -q "_extract_chart_paths" "$EXECUTE_PYTHON_FILE"; then
        echo "✅ _extract_chart_paths 方法存在"
    else
        echo "❌ _extract_chart_paths 方法不存在"
        FAILED=$((FAILED + 1))
    fi

    # 检查 ImageCache 集成
    if grep -q "from app.services.image_cache import ImageCache" "$EXECUTE_PYTHON_FILE"; then
        echo "✅ ImageCache 已导入"
    else
        echo "❌ ImageCache 未导入"
        FAILED=$((FAILED + 1))
    fi

    # 检查目录创建
    if grep -q 'os.makedirs(self.CHARTS_DIR, exist_ok=True)' "$EXECUTE_PYTHON_FILE"; then
        echo "✅ CHARTS_DIR 自动创建已实现"
    else
        echo "❌ CHARTS_DIR 自动创建未实现"
        FAILED=$((FAILED + 1))
    fi
else
    echo "❌ execute_python_tool.py 文件不存在"
    FAILED=$((FAILED + 1))
fi

# 测试 6: 检查前端集成
echo ""
echo "============================================================"
echo "测试 6: 前端集成"
echo "============================================================"

REACT_STORE_FILE="/home/xckj/suyuan/frontend/src/stores/reactStore.js"

if [ -f "$REACT_STORE_FILE" ]; then
    echo "✅ reactStore.js 文件存在"

    # 检查 chart 模式
    if grep -q "chart:" "$REACT_STORE_FILE"; then
        echo "✅ reactStore.js 包含 chart 模式"
    else
        echo "❌ reactStore.js 不包含 chart 模式"
        FAILED=$((FAILED + 1))
    fi
else
    echo "⚠️  reactStore.js 文件不存在（前端可能未构建）"
fi

AGENT_MODE_SELECTOR="/home/xckj/suyuan/frontend/src/components/AgentModeSelector.vue"

if [ -f "$AGENT_MODE_SELECTOR" ]; then
    echo "✅ AgentModeSelector.vue 文件存在"

    # 检查图表模式按钮
    if grep -q "图表" "$AGENT_MODE_SELECTOR"; then
        echo "✅ AgentModeSelector.vue 包含图表按钮"
    else
        echo "❌ AgentModeSelector.vue 不包含图表按钮"
        FAILED=$((FAILED + 1))
    fi
else
    echo "⚠️  AgentModeSelector.vue 文件不存在（前端可能未构建）"
fi

# 汇总结果
echo ""
echo "============================================================"
echo "测试结果汇总"
echo "============================================================"

if [ $FAILED -eq 0 ]; then
    echo "🎉 所有配置验证通过！图表模式已正确集成。"
    echo ""
    echo "下一步："
    echo "1. 重启后端服务（如果正在运行）"
    echo "2. 在前端测试图表模式功能"
    echo "3. 验证 ReAct 循环和图表生成"
    exit 0
else
    echo "⚠️  发现 $FAILED 个配置问题，需要修复。"
    exit 1
fi
