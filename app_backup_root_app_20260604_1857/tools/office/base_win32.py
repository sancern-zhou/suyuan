"""
Win32 COM 基类

提供 Office 自动化的通用功能：
- 进程管理（启动/关闭）
- 异常处理
- 文件操作封装
"""

import os
import time
import pythoncom
from typing import Optional, Any, List
from abc import ABC, abstractmethod
import structlog

logger = structlog.get_logger()


class Win32Base(ABC):
    """
    Win32 COM 基类

    负责管理 Office 应用程序的生命周期和通用操作
    """

    # Office 应用程序常量
    APP_WORD = "Word.Application"
    APP_EXCEL = "Excel.Application"
    APP_POWERPOINT = "PowerPoint.Application"

    def __init__(
        self,
        app_name: str,
        visible: bool = False,
        display_alerts: bool = False
    ):
        """
        初始化 Win32 COM 基类

        Args:
            app_name: Office 应用程序名称
            visible: 是否显示窗口
            display_alerts: 是否显示警告对话框
        """
        self.app_name = app_name
        self.visible = visible
        self.display_alerts = display_alerts
        self.app = None
        self._initialized = False

    def _init_app(self) -> Any:
        """
        初始化 Office 应用程序

        Returns:
            Office 应用程序对象
        """
        try:
            # 初始化 COM
            pythoncom.CoInitialize()

            # 创建应用程序实例
            import win32com.client as win32
            self.app = win32.Dispatch(self.app_name)

            # 配置应用程序
            self.app.Visible = self.visible
            self.app.DisplayAlerts = 0 if not self.display_alerts else True

            self._initialized = True

            logger.info(
                "win32_app_initialized",
                app=self.app_name,
                visible=self.visible,
                display_alerts=self.display_alerts
            )

            return self.app

        except Exception as e:
            logger.error(
                "win32_app_init_failed",
                app=self.app_name,
                error=str(e)
            )
            raise

    def ensure_initialized(self):
        """确保应用程序已初始化"""
        if not self._initialized or self.app is None:
            self._init_app()

    def close_app(self):
        """关闭 Office 应用程序"""
        if self.app:
            try:
                # 退出应用程序
                self.app.Quit()
                logger.info("win32_app_closed", app=self.app_name)
            except Exception as e:
                logger.warning(
                    "win32_app_close_warning",
                    app=self.app_name,
                    error=str(e)
                )
            finally:
                self.app = None
                self._initialized = False

        # 释放 COM
        try:
            pythoncom.CoUninitialize()
        except:
            pass

    def __enter__(self):
        """上下文管理器入口"""
        self.ensure_initialized()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close_app()
        return False

    def safe_execute(self, func, *args, **kwargs):
        """
        安全执行函数，自动处理异常

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果，失败返回 None
        """
        try:
            self.ensure_initialized()
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(
                "win32_execute_failed",
                app=self.app_name,
                function=func.__name__,
                error=str(e)
            )
            return None

    def check_file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        if not os.path.exists(file_path):
            logger.error("file_not_found", path=file_path)
            return False
        return True

    def get_absolute_path(self, file_path: str) -> str:
        """
        获取文件绝对路径

        Args:
            file_path: 文件路径（支持相对路径和绝对路径）

        Returns:
            绝对路径（Windows 格式，使用反斜杠）
        """
        from pathlib import Path

        logger.info("get_absolute_path_input", path=file_path)

        # 如果已经是绝对路径，标准化后返回
        if os.path.isabs(file_path):
            result = os.path.normpath(file_path)
            logger.info("get_absolute_path_absolute", result=result)
            return result

        # 获取项目根目录
        # 优先使用环境变量
        project_root_str = os.environ.get('PROJECT_ROOT')
        if project_root_str:
            project_root = Path(project_root_str)
        else:
            # 智能推断：向上查找包含特定目录/文件的位置
            current_file = Path(__file__)

            # 方法1：查找 backend 目录，其父目录就是项目根目录
            # 适用于：溯源/backend/...
            temp = current_file
            while temp.parent != temp:  # 避免到达根目录
                if temp.name == 'backend':
                    project_root = temp.parent
                    break
                temp = temp.parent
            else:
                # 方法2：如果找不到 backend，使用固定层级（向上 5 级）
                # 适用于：Docker 等特殊环境
                project_root = current_file.parent.parent.parent.parent.parent

        # 标准化路径分隔符
        normalized = file_path.replace('\\', '/')

        # 自动适配：移除项目名称前缀（如果存在）
        # 例如：溯源/报告模板/... → 报告模板/...
        parts = normalized.split('/')
        if parts and parts[0] == project_root.name:
            normalized = '/'.join(parts[1:])

        # 基于项目根目录解析相对路径
        abs_path = (project_root / normalized).resolve()

        # 返回 Windows 标准路径格式（使用反斜杠）
        result = os.path.normpath(str(abs_path))
        logger.info("get_absolute_path_relative", project_root=str(project_root), normalized=normalized, result=result)
        return result

    @abstractmethod
    def open_document(self, file_path: str):
        """
        打开文档（子类实现）

        Args:
            file_path: 文件路径
        """
        pass

    @abstractmethod
    def save_document(self, doc, file_path: str):
        """
        保存文档（子类实现）

        Args:
            doc: 文档对象
            file_path: 保存路径
        """
        pass

    @abstractmethod
    def close_document(self, doc):
        """
        关闭文档（子类实现）

        Args:
            doc: 文档对象
        """
        pass

    def disable_screen_updating(self):
        """
        禁用屏幕更新的上下文管理器（性能优化）

        在执行批量操作时使用，可以显著提升性能（20-50%）
        参考：https://stackoverflow.com/questions/17670085/how-to-disable-screen-update-in-long-running-word-macro

        Usage:
            with self.disable_screen_updating():
                # 执行耗时操作
                find.Execute(Replace=2)
        """
        class ScreenUpdatingContext:
            def __init__(self, app):
                self.app = app
                self.original_value = None

            def __enter__(self):
                if self.app and hasattr(self.app, 'ScreenUpdating'):
                    self.original_value = self.app.ScreenUpdating
                    self.app.ScreenUpdating = False
                    logger.debug("screen_updating_disabled")
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.app and hasattr(self.app, 'ScreenUpdating') and self.original_value is not None:
                    self.app.ScreenUpdating = self.original_value
                    logger.debug("screen_updating_restored", value=self.original_value)
                return False

        return ScreenUpdatingContext(self.app)
