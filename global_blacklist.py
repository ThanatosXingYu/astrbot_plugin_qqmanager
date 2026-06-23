from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .config import PluginConfig
from .data import QQAdminDB
from .group_info_cache import QQGroupInfoCache


class GlobalBlacklistService:
    def __init__(
        self,
        cfg: PluginConfig,
        db: QQAdminDB,
        group_cache: QQGroupInfoCache,
    ):
        self.cfg = cfg
        self.db = db
        self.group_cache = group_cache

    @staticmethod
    def clean_ids(ids: list[Any] | set[Any] | tuple[Any, ...] | None) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in ids or []:
            user_id = str(item).strip()
            if not user_id.isdigit() or user_id in seen:
                continue
            cleaned.append(user_id)
            seen.add(user_id)
        return sorted(cleaned, key=lambda value: int(value))

    def get_global_ids(self) -> list[str]:
        return self.clean_ids(getattr(self.cfg, "global_block_ids", []))

    def add_global_ids(self, user_ids: list[str]) -> list[str]:
        current = set(self.get_global_ids())
        added = [
            user_id for user_id in self.clean_ids(user_ids) if user_id not in current
        ]
        if not added:
            return []

        current.update(added)
        self.cfg.global_block_ids = self.clean_ids(current)
        self.cfg.save_config()
        return added

    def replace_global_ids(self, user_ids: list[str]) -> list[str]:
        old_ids = set(self.get_global_ids())
        new_ids = set(self.clean_ids(user_ids))
        self.cfg.global_block_ids = self.clean_ids(new_ids)
        self.cfg.save_config()
        return self.clean_ids(new_ids - old_ids)

    async def sweep_users(
        self,
        user_ids: list[str],
        *,
        notice_group_id: str | None = None,
        origin_group_name: str = "",
        fallback_client: Any | None = None,
    ) -> str:
        sections: list[str] = []
        for user_id in self.clean_ids(user_ids):
            sections.append(
                await self._sweep_user(
                    user_id,
                    origin_group_name=origin_group_name,
                )
            )

        message = "\n\n".join(sections)
        if message:
            await self.send_owner_notice(
                message,
                notice_group_id=notice_group_id,
                fallback_client=fallback_client,
            )
        return message

    async def send_owner_notice(
        self,
        message: str,
        *,
        notice_group_id: str | None = None,
        fallback_client: Any | None = None,
    ) -> bool:
        recipients = self._notice_recipients(notice_group_id)
        if not recipients:
            return False

        client = fallback_client or self.group_cache.get_any_client()
        if client is None:
            return False

        sent = False
        for user_id in recipients:
            try:
                await client.send_private_msg(user_id=int(user_id), message=message)
                sent = True
            except Exception as exc:
                logger.warning("发送总黑名单汇总给 %s 失败: %s", user_id, exc)
        return sent

    def _notice_recipients(self, group_id: str | None) -> list[str]:
        owner_ids: list[str] = []
        if group_id:
            owner_ids = self.clean_ids(
                self.db.get_group_snapshot(group_id).get("owner_ids", [])
            )
        if not owner_ids:
            owner_ids = self.clean_ids(self.cfg.default.get("owner_ids", []))
        if not owner_ids:
            owner_ids = self.clean_ids(self.cfg.admins_id)
        return owner_ids

    async def _sweep_user(self, user_id: str, *, origin_group_name: str = "") -> str:
        groups = await self.group_cache.list_groups_with_bot_roles(force_bot_roles=True)
        found: list[str] = []
        kicked: list[str] = []
        failed: list[str] = []

        for group in groups:
            group_id = str(group.get("group_id", "")).strip()
            if not group_id.isdigit():
                continue

            client = self.group_cache.get_client_for_group(group_id)
            if client is None:
                continue

            try:
                member_info = await client.get_group_member_info(
                    group_id=int(group_id),
                    user_id=int(user_id),
                    no_cache=True,
                )
            except Exception:
                continue

            if not member_info:
                continue

            label = self._group_label(group)
            found.append(label)
            bot_role = str(group.get("bot_role", "unknown")).lower()
            if bot_role not in {"owner", "admin"}:
                failed.append(f"{label}：机器人不是群主或管理员")
                continue

            try:
                await client.set_group_kick(
                    group_id=int(group_id),
                    user_id=int(user_id),
                    reject_add_request=True,
                )
                kicked.append(label)
            except Exception as exc:
                failed.append(f"{label}：{self._brief_error(exc)}")

        lines = ["【全局拉黑处理结果】", f"QQ：{user_id}"]
        if origin_group_name:
            lines.append(f"发起位置：{origin_group_name}")
        lines.append(f"检测到所在群：{self._join_or_empty(found)}")
        lines.append(f"踢出成功：{self._join_or_empty(kicked)}")
        lines.append(f"踢出失败：{self._join_or_empty(failed)}")
        return "\n".join(lines)

    @staticmethod
    def _group_label(group: dict[str, Any]) -> str:
        group_id = str(group.get("group_id", "")).strip()
        group_name = str(group.get("group_name", "")).strip() or f"群 {group_id}"
        return f"{group_name}({group_id})"

    @staticmethod
    def _join_or_empty(items: list[str]) -> str:
        return "、".join(items) if items else "无"

    @staticmethod
    def _brief_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:100]
