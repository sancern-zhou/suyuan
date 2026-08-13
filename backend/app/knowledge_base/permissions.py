"""
知识库权限管理

实现公共/个人知识库的权限检查和访问控制。

当前策略：保留PUBLIC/PRIVATE概念；读取沿用全员可见策略，管理仅限 owner/admin。
"""

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import KnowledgeBase, KnowledgeBaseStatus, KnowledgeBaseStorageScope
from .storage_scope import get_local_knowledge_scope

logger = structlog.get_logger()


def _storage_scope(kb: KnowledgeBase) -> str:
    """Handle transient ORM objects before SQLAlchemy applies column defaults."""
    scope = getattr(kb, "vector_store_scope", None)
    return getattr(scope, "value", scope) or "local"


def _is_visible_in_current_scope(kb: KnowledgeBase) -> bool:
    if _storage_scope(kb) == "shared":
        return True
    # New rows always carry a scope. Keeping unsaved legacy ORM objects visible
    # preserves internal call sites until they are persisted.
    return not kb.local_scope or kb.local_scope == get_local_knowledge_scope()


def local_visibility_filter():
    """Shared knowledge is global; local knowledge is visible only in its scope."""
    return or_(
        KnowledgeBase.vector_store_scope == KnowledgeBaseStorageScope.SHARED,
        and_(
            KnowledgeBase.vector_store_scope == KnowledgeBaseStorageScope.LOCAL,
            KnowledgeBase.local_scope == get_local_knowledge_scope(),
        ),
    )


class KnowledgeBasePermissions:
    """知识库权限管理"""

    @staticmethod
    async def get_accessible_knowledge_bases(
        db: AsyncSession,
        user_id: str | None = None,
        include_public: bool = True,
        status: KnowledgeBaseStatus | None = None,
    ) -> list[KnowledgeBase]:
        """
        获取用户可访问的知识库列表

        当前规则（临时措施）:
        - 所有知识库都可访问（PUBLIC + PRIVATE）
        - 不检查user_id
        - 保留PUBLIC/PRIVATE类型标识，仅用于显示区分

        Args:
            db: 数据库会话
            user_id: 用户ID（暂不使用）
            include_public: 是否包含公共知识库
            status: 状态过滤

        Returns:
            可访问的知识库列表
        """
        # 构建查询：获取所有知识库
        query = select(KnowledgeBase).where(local_visibility_filter())

        # 状态过滤
        if status:
            query = query.where(KnowledgeBase.status == status)

        # 排序：默认在前，然后按创建时间倒序
        query = query.order_by(KnowledgeBase.is_default.desc(), KnowledgeBase.created_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def can_manage(kb: KnowledgeBase, user_id: str, is_admin: bool = False) -> bool:
        """
        检查用户是否有管理权限

        当前规则：管理员或知识库所有者可管理。

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）
            is_admin: 是否为管理员（暂不使用）

        Returns:
            是否有管理权限
        """
        return bool(
            _is_visible_in_current_scope(kb)
            and (is_admin or (user_id and kb.owner_id == user_id))
        )

    @staticmethod
    def can_manage_documents(
        kb: KnowledgeBase, user_id: str | None, is_admin: bool = False
    ) -> bool:
        """Check whether a user may delete or replace documents in a knowledge base.

        A shared index is published centrally and must never be changed by an
        arbitrary project branch. Public local knowledge bases retain the
        existing authenticated-user behaviour.
        """
        is_authenticated = bool(user_id)
        if _storage_scope(kb) == "shared":
            return bool(is_admin)
        if kb.is_public:
            return is_authenticated
        return bool(is_admin or (is_authenticated and kb.owner_id == user_id))

    @staticmethod
    def can_search(kb: KnowledgeBase, user_id: str | None = None) -> bool:
        """
        检查用户是否有检索权限

        当前规则（临时措施）: 所有人可检索所有知识库

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）

        Returns:
            是否有检索权限
        """
        return _is_visible_in_current_scope(kb)

    @staticmethod
    def can_upload(kb: KnowledgeBase, user_id: str | None = None, is_admin: bool = False) -> bool:
        """
        检查用户是否有上传文档权限

        共享库由中心管理员发布；本地库沿用既有上传规则。

        Args:
            kb: 知识库对象
            user_id: 用户ID（暂不使用）
            is_admin: 是否为管理员（暂不使用）

        Returns:
            是否有上传权限
        """
        if _storage_scope(kb) == "shared":
            return bool(is_admin)
        return True

    @staticmethod
    async def filter_accessible_ids(
        db: AsyncSession, knowledge_base_ids: list[str], user_id: str | None = None
    ) -> list[str]:
        """
        过滤出用户可访问的知识库ID

        当前规则（临时措施）: 返回所有传入的知识库ID，不进行过滤

        Args:
            db: 数据库会话
            knowledge_base_ids: 待检查的知识库ID列表
            user_id: 用户ID（暂不使用）

        Returns:
            可访问的知识库ID列表
        """
        if not knowledge_base_ids:
            return []

        result = await db.execute(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id.in_(knowledge_base_ids),
                local_visibility_filter(),
            )
        )
        return list(result.scalars().all())
