"""ORM 模型聚合导出。

建表依赖 ``Base.metadata``，因此必须在此处导入全部模型，
使 ``init_db()`` 能通过导入本包完成元数据注册。
"""

from app.db.base import Base
from app.models.knowledge import (
    DOC_STATUS_FAILED,
    DOC_STATUS_PENDING,
    DOC_STATUS_READY,
    IMPORT_STATUS_DONE,
    IMPORT_STATUS_FAILED,
    IMPORT_STATUS_PENDING,
    IMPORT_STATUS_RUNNING,
    PERM_DEPARTMENT,
    PERM_GLOBAL,
    PERM_ROLE,
    PERM_TYPES,
    PERM_USER,
    SOURCE_EXCEL,
    SOURCE_IMAGE,
    SOURCE_MD,
    SOURCE_PDF,
    SOURCE_PPT,
    SOURCE_TXT,
    SOURCE_WORD,
    SUPPORTED_SOURCE_TYPES,
    KbDocPerm,
    KbDocument,
    KbImportTask,
)
from app.models.ops import (
    FAQ_SOURCE_AUTO,
    FAQ_SOURCE_MANUAL,
    FAQ_STATUS_PENDING,
    FAQ_STATUS_PUBLISHED,
    FAQ_STATUS_REJECTED,
    GAP_TASK_DONE,
    GAP_TASK_OPEN,
    GAP_TASK_PROCESSING,
    KbAccessLog,
    KbFaq,
    KbFaqPerm,
    KbGapTask,
    KbKnowledgeGap,
)
from app.models.rbac import (
    MENU_TYPE_BUTTON,
    MENU_TYPE_DIR,
    MENU_TYPE_MENU,
    Dept,
    Menu,
    Role,
    User,
    sys_role_menu,
    sys_user_role,
)

__all__ = [
    "Base",
    # rbac
    "Dept", "Role", "Menu", "User", "sys_user_role", "sys_role_menu",
    "MENU_TYPE_DIR", "MENU_TYPE_MENU", "MENU_TYPE_BUTTON",
    # knowledge
    "KbDocument", "KbDocPerm", "KbImportTask",
    "PERM_GLOBAL", "PERM_DEPARTMENT", "PERM_ROLE", "PERM_USER", "PERM_TYPES",
    "DOC_STATUS_PENDING", "DOC_STATUS_READY", "DOC_STATUS_FAILED",
    "IMPORT_STATUS_PENDING", "IMPORT_STATUS_RUNNING", "IMPORT_STATUS_DONE", "IMPORT_STATUS_FAILED",
    "SOURCE_PDF", "SOURCE_WORD", "SOURCE_MD", "SOURCE_TXT", "SOURCE_PPT", "SOURCE_EXCEL", "SOURCE_IMAGE",
    "SUPPORTED_SOURCE_TYPES",
    # ops
    "KbAccessLog", "KbFaq", "KbFaqPerm", "KbKnowledgeGap", "KbGapTask",
    "FAQ_STATUS_PENDING", "FAQ_STATUS_PUBLISHED", "FAQ_STATUS_REJECTED",
    "FAQ_SOURCE_AUTO", "FAQ_SOURCE_MANUAL",
    "GAP_TASK_OPEN", "GAP_TASK_PROCESSING", "GAP_TASK_DONE",
]
