#!/bin/bash
# 知识库查询脚本
# 使用方法: ./query_knowledge_base.sh [command] [kb_id]

DB_HOST="180.184.30.94"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="weather_db"
DB_PASS="Xc13129092470"

QDRANT_HOST="180.184.30.94"
QDRANT_PORT="6333"
QDRANT_API_KEY="Xc13129092470"

# 设置PGPASSWORD环境变量（避免密码提示）
export PGPASSWORD="$DB_PASS"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# 显示帮助信息
show_help() {
    cat << EOF
知识库查询脚本

使用方法:
    ./query_knowledge_base.sh [command] [kb_id]

命令列表:
    list                    列出所有知识库
    info <kb_id>           显示知识库详细信息
    docs <kb_id>           列出知识库的所有文档
    stats                  显示存储统计信息
    qdrant                 列出Qdrant Collections
    delete <kb_id>         删除知识库（需要确认）
    clean                  清理孤立数据
    help                   显示此帮助信息

示例:
    ./query_knowledge_base.sh list
    ./query_knowledge_base.sh info abc-123-def
    ./query_knowledge_base.sh docs abc-123-def
    ./query_knowledge_base.sh stats

EOF
}

# 列出所有知识库
list_knowledge_bases() {
    print_header "所有知识库列表"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t << EOF | column -t -s '|'
SELECT
    SUBSTRING(id, 1, 8) AS kb_id,
    name,
    kb_type,
    document_count,
    chunk_count,
    pg_size_pretty(total_size) AS size,
    status,
    TO_CHAR(created_at, 'YYYY-MM-DD') AS created
FROM knowledge_bases
ORDER BY created_at DESC;
EOF

    echo ""
    print_info "提示: 使用 'info <kb_id>' 查看完整知识库ID和详细信息"
}

# 显示知识库详细信息
show_kb_info() {
    local kb_id="$1"

    if [ -z "$kb_id" ]; then
        print_error "请提供知识库ID"
        echo "使用方法: ./query_knowledge_base.sh info <kb_id>"
        return 1
    fi

    print_header "知识库详细信息: $kb_id"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << EOF
\set QUIET on
\pset format aligned
\pset border 2

SELECT
    id AS "知识库ID",
    name AS "名称",
    description AS "描述",
    kb_type AS "类型",
    embedding_model AS "嵌入模型",
    chunking_strategy AS "分块策略",
    chunk_size AS "分块大小",
    chunk_overlap AS "重叠大小",
    qdrant_collection AS "Qdrant集合",
    document_count AS "文档数",
    chunk_count AS "分块数",
    pg_size_pretty(total_size) AS "总大小",
    status AS "状态",
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS "创建时间",
    TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS "更新时间"
FROM knowledge_bases
WHERE id LIKE '%$kb_id%' OR name LIKE '%$kb_id%';
EOF

    echo ""
    print_success "查询完成"
}

# 列出知识库的所有文档
list_documents() {
    local kb_id="$1"

    if [ -z "$kb_id" ]; then
        print_error "请提供知识库ID"
        echo "使用方法: ./query_knowledge_base.sh docs <kb_id>"
        return 1
    fi

    print_header "知识库文档列表: $kb_id"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t << EOF | column -t -s '|'
SELECT
    SUBSTRING(doc.id, 1, 8) AS doc_id,
    doc.filename AS "文件名",
    pg_size_pretty(doc.file_size) AS "大小",
    doc.mime_type AS "类型",
    doc.chunk_count AS "分块数",
    TO_CHAR(doc.created_at, 'YYYY-MM-DD') AS "上传日期"
FROM documents doc
WHERE doc.knowledge_base_id IN (
    SELECT id FROM knowledge_bases
    WHERE id LIKE '%$kb_id%' OR name LIKE '%$kb_id%'
)
ORDER BY doc.created_at DESC;
EOF

    echo ""
    print_info "提示: 使用完整文档ID查看详细元数据"
}

# 显示存储统计信息
show_stats() {
    print_header "知识库存储统计"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << EOF
\set QUIET on
\pset format aligned
\pset border 2

-- 知识库总览
SELECT
    '知识库总数' AS "统计项",
    COUNT(*) AS "数量"
FROM knowledge_bases
UNION ALL
SELECT
    '文档总数',
    COUNT(*)
FROM documents
UNION ALL
SELECT
    '总文件大小',
    pg_size_pretty(SUM(file_size))
FROM documents
UNION ALL
SELECT
    '总分块数',
    SUM(chunk_count)
FROM documents;

-- 每个知识库的统计
SELECT
    kb.name AS "知识库名称",
    COUNT(doc.id) AS "文档数",
    pg_size_pretty(SUM(doc.file_size)) AS "总大小",
    SUM(doc.chunk_count) AS "总分块数",
    ROUND(AVG(doc.chunk_count)::numeric, 2) AS "平均分块/文档"
FROM knowledge_bases kb
LEFT JOIN documents doc ON kb.id = doc.knowledge_base_id
GROUP BY kb.id, kb.name
ORDER BY SUM(doc.file_size) DESC NULLS LAST;
EOF

    echo ""
    print_success "统计信息查询完成"
}

# 列出Qdrant Collections
list_qdrant_collections() {
    print_header "Qdrant Collections"

    curl -s -X GET "http://$QDRANT_HOST:$QDRANT_PORT/collections" \
        -H "api-key: $QDRANT_API_KEY" | python3 -m json.tool

    echo ""
    print_info "Qdrant Collections查询完成"
}

# 删除知识库
delete_kb() {
    local kb_id="$1"

    if [ -z "$kb_id" ]; then
        print_error "请提供知识库ID"
        echo "使用方法: ./query_knowledge_base.sh delete <kb_id>"
        return 1
    fi

    print_header "删除知识库: $kb_id"
    print_error "⚠️  此操作将永久删除知识库及其所有数据！"
    echo ""
    read -p "请输入知识库完整ID以确认删除: " confirm_id

    if [ "$confirm_id" != "$kb_id" ]; then
        print_error "ID不匹配，取消删除"
        return 1
    fi

    read -p "再次确认删除? (yes/no): " final_confirm

    if [ "$final_confirm" != "yes" ]; then
        print_info "取消删除"
        return 0
    fi

    # 使用Python脚本删除（确保数据一致性）
    python3 << EOF
import asyncio
import sys
sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.db.database import async_session
from app.knowledge_base.service import KnowledgeBaseService

async def delete_kb(kb_id: str):
    async with async_session() as db:
        service = KnowledgeBaseService(db=db)
        try:
            await service.delete_knowledge_base(kb_id)
            print(f"\n✓ 知识库 {kb_id} 已成功删除")
        except Exception as e:
            print(f"\n✗ 删除失败: {str(e)}")
            sys.exit(1)

asyncio.run(delete_kb("$kb_id"))
EOF
}

# 清理孤立数据
clean_orphaned_data() {
    print_header "清理孤立数据检查"

    print_info "检查孤立的Large Object..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << EOF
-- 查找孤立的Large Object
SELECT
    '孤立Large Object数量' AS "检查项",
    COUNT(*) AS "数量"
FROM pg_largeobject lo
LEFT JOIN documents doc ON doc.storage_path = lo.loid::text
WHERE doc.id IS NULL;
EOF

    echo ""
    print_info "如需清理孤立数据，请手动执行SQL删除命令"
}

# 主函数
main() {
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi

    case "$1" in
        list)
            list_knowledge_bases
            ;;
        info)
            show_kb_info "$2"
            ;;
        docs)
            list_documents "$2"
            ;;
        stats)
            show_stats
            ;;
        qdrant)
            list_qdrant_collections
            ;;
        delete)
            delete_kb "$2"
            ;;
        clean)
            clean_orphaned_data
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"

# 清理环境变量
unset PGPASSWORD
