from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger

from .config import PluginConfig
from .data import QQAdminDB
from .group_info_cache import QQGroupInfoCache


@dataclass(frozen=True)
class KickCandidate:
    index: int
    group_id: str
    group_name: str
    bot_role: str
    target_role: str
    can_kick: bool
    reason: str = ""

    @property
    def label(self) -> str:
        return f"{self.group_name}({self.group_id})"


@dataclass(frozen=True)
class PendingKickTask:
    task_id: str
    user_id: str
    candidates: list[KickCandidate]
    origin_group_name: str = ""
    current_group_result: str = ""
    created_at: float = 0.0


class GlobalBlacklistService:
    _PENDING_TTL_SECONDS = 1800
    _SHORT_ALL_REPLIES = {
        "是",
        "确认",
        "确定",
        "好",
        "all",
        "全部",
        "所有",
        "yes",
        "y",
    }
    _pending_kick_tasks: dict[str, PendingKickTask] = {}

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

    def remove_global_ids(self, user_ids: list[str]) -> list[str]:
        target_ids = set(self.clean_ids(user_ids))
        if not target_ids:
            return []

        current = set(self.get_global_ids())
        removed = current & target_ids
        if not removed:
            return []

        current -= removed
        self.cfg.global_block_ids = self.clean_ids(current)
        self.cfg.save_config()
        return self.clean_ids(removed)

    def replace_global_ids(self, user_ids: list[str]) -> list[str]:
        old_ids = set(self.get_global_ids())
        new_ids = set(self.clean_ids(user_ids))
        self.cfg.global_block_ids = self.clean_ids(new_ids)
        self.cfg.save_config()
        return self.clean_ids(new_ids - old_ids)

    async def create_pending_kick_task(
        self,
        user_id: str,
        *,
        notice_group_id: str | None = None,
        origin_group_name: str = "",
        current_group_result: str = "",
        fallback_client: Any | None = None,
    ) -> str:
        cleaned = self.clean_ids([user_id])
        if not cleaned:
            return ""

        self._expire_pending_tasks()
        uid = cleaned[0]
        candidates = await self._scan_user_groups(uid)
        task_id = self._new_task_id(uid) if any(item.can_kick for item in candidates) else ""
        task = PendingKickTask(
            task_id=task_id,
            user_id=uid,
            candidates=candidates,
            origin_group_name=origin_group_name,
            current_group_result=current_group_result,
            created_at=time.monotonic(),
        )
        if task_id:
            self._pending_kick_tasks[task_id] = task

        message = self._format_pending_task(task)
        if message:
            await self.send_super_notice(
                message,
                notice_group_id=notice_group_id,
                fallback_client=fallback_client,
            )
        return message

    async def execute_pending_kick(
        self,
        task_id: str | None,
        selection: str | None,
        *,
        fallback_client: Any | None = None,
    ) -> str:
        self._expire_pending_tasks()
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return "请提供待处理任务ID"

        task = self._pending_kick_tasks.get(normalized_task_id)
        if task is None:
            return "任务不存在或已过期"

        selected, skipped = self._select_candidates(task, selection)
        if not selected:
            lines = ["没有可执行的群聊"]
            if skipped:
                lines.extend(skipped)
            return "\n".join(lines)

        success: list[str] = []
        failed: list[str] = []
        for candidate in selected:
            client = self.group_cache.get_client_for_group(candidate.group_id)
            if client is None:
                client = fallback_client
            if client is None:
                failed.append(f"{candidate.index}. {candidate.label}：找不到可用客户端")
                continue

            try:
                await client.set_group_kick(
                    group_id=int(candidate.group_id),
                    user_id=int(task.user_id),
                    reject_add_request=True,
                )
                success.append(f"{candidate.index}. {candidate.label}")
            except Exception as exc:
                failed.append(
                    f"{candidate.index}. {candidate.label}：{self._brief_error(exc)}"
                )

        self._pending_kick_tasks.pop(normalized_task_id, None)
        lines = ["【踢除执行结果】", f"任务：{normalized_task_id}", f"QQ：{task.user_id}"]
        lines.append("成功：")
        lines.extend(success or ["无"])
        lines.append("失败：")
        lines.extend(failed or ["无"])
        if skipped:
            lines.append("跳过：")
            lines.extend(skipped)
        return "\n".join(lines)

    def cancel_pending_kick(self, task_id: str | None) -> str:
        self._expire_pending_tasks()
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return "请提供待处理任务ID"
        if self._pending_kick_tasks.pop(normalized_task_id, None) is None:
            return "任务不存在或已过期"
        return f"已取消任务：{normalized_task_id}"

    async def execute_latest_short_reply(
        self,
        text: str,
        *,
        fallback_client: Any | None = None,
    ) -> str | None:
        selection = self._parse_short_reply(text)
        if selection is None:
            return None

        task_id = self._latest_pending_task_id()
        if task_id is None:
            return None

        return await self.execute_pending_kick(
            task_id,
            selection,
            fallback_client=fallback_client,
        )

    async def send_super_notice(
        self,
        message: str,
        *,
        notice_group_id: str | None = None,
        fallback_client: Any | None = None,
    ) -> bool:
        recipients = self.clean_ids(self.cfg.admins_id)
        if not recipients:
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
                logger.warning("发送总黑名单待处理任务给 %s 失败: %s", user_id, exc)
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

    async def _scan_user_groups(self, user_id: str) -> list[KickCandidate]:
        groups = await self.group_cache.list_groups_with_bot_roles(force_bot_roles=True)
        candidates: list[KickCandidate] = []
        index = 1

        for group in groups:
            group_id = str(group.get("group_id", "")).strip()
            if not group_id.isdigit():
                continue

            client = self.group_cache.get_client_for_group(group_id)
            if client is None:
                continue

            try:
                member_result = await client.get_group_member_info(
                    group_id=int(group_id),
                    user_id=int(user_id),
                    no_cache=True,
                )
            except Exception:
                continue

            member_info = self._extract_object(member_result)
            if not member_info:
                continue

            bot_role = self._normalize_role(group.get("bot_role"))
            target_role = self._normalize_role(member_info.get("role"))
            can_kick, reason = self._kick_capability(bot_role, target_role)
            candidates.append(
                KickCandidate(
                    index=index,
                    group_id=group_id,
                    group_name=self._group_name(group),
                    bot_role=bot_role,
                    target_role=target_role,
                    can_kick=can_kick,
                    reason=reason,
                )
            )
            index += 1

        return candidates

    def _format_pending_task(self, task: PendingKickTask) -> str:
        lines = ["【总黑名单跨群处理】", f"QQ：{task.user_id}"]
        if task.origin_group_name:
            lines.append(f"发起位置：{task.origin_group_name}")
        if task.current_group_result:
            lines.append(f"当前群处理：{task.current_group_result}")

        if not task.candidates:
            lines.append("未在机器人加入的其他群中发现该用户。")
            return "\n".join(lines)

        can_kick = [item for item in task.candidates if item.can_kick]
        cannot_kick = [item for item in task.candidates if not item.can_kick]

        lines.append("可踢群聊：")
        lines.extend([f"{item.index}. {item.label}" for item in can_kick] or ["无"])
        lines.append("不可踢群聊：")
        lines.extend(
            [f"{item.index}. {item.label}：{item.reason}" for item in cannot_kick]
            or ["无"]
        )

        if task.task_id:
            lines.extend(
                [
                    "",
                    "直接回复 是 或 all 可踢除全部可踢群",
                    "直接回复 1,3 可踢除指定序号",
                    f"也可回复 /取消踢除 {task.task_id} 取消任务",
                ]
            )
        else:
            lines.append("没有可由机器人继续踢除的群聊，无需确认。")
        return "\n".join(lines)

    def _select_candidates(
        self,
        task: PendingKickTask,
        selection: str | None,
    ) -> tuple[list[KickCandidate], list[str]]:
        normalized = str(selection or "").strip().lower()
        candidates_by_index = {item.index: item for item in task.candidates}
        selected: list[KickCandidate] = []
        skipped: list[str] = []

        if not normalized:
            return [], ["请提供 all 或群序号，例如：all 或 1,3"]

        if normalized in {"all", "全部", "所有"}:
            return [item for item in task.candidates if item.can_kick], skipped

        indexes: list[int] = []
        for token in re.split(r"[\s,，、]+", normalized):
            if not token:
                continue
            if not token.isdigit():
                skipped.append(f"{token}：不是有效序号")
                continue
            index = int(token)
            if index not in indexes:
                indexes.append(index)

        for index in indexes:
            candidate = candidates_by_index.get(index)
            if candidate is None:
                skipped.append(f"{index}：序号不存在")
                continue
            if not candidate.can_kick:
                skipped.append(f"{index}. {candidate.label}：{candidate.reason}")
                continue
            selected.append(candidate)

        return selected, skipped

    def _expire_pending_tasks(self) -> None:
        now = time.monotonic()
        expired = [
            task_id
            for task_id, task in self._pending_kick_tasks.items()
            if now - task.created_at > self._PENDING_TTL_SECONDS
        ]
        for task_id in expired:
            self._pending_kick_tasks.pop(task_id, None)

    def _latest_pending_task_id(self) -> str | None:
        self._expire_pending_tasks()
        if not self._pending_kick_tasks:
            return None

        latest = max(
            self._pending_kick_tasks.values(),
            key=lambda task: task.created_at,
        )
        return latest.task_id or None

    def _parse_short_reply(self, text: str) -> str | None:
        normalized = str(text or "").strip().lower()
        if normalized in self._SHORT_ALL_REPLIES:
            return "all"
        if re.fullmatch(r"\d+(?:[\s,，、]+\d+)*", normalized):
            return normalized
        return None

    def _new_task_id(self, user_id: str) -> str:
        for _ in range(10):
            task_id = f"{user_id[-4:]}-{secrets.token_hex(2)}"
            if task_id not in self._pending_kick_tasks:
                return task_id
        return f"{user_id[-4:]}-{int(time.time())}"

    @staticmethod
    def _kick_capability(bot_role: str, target_role: str) -> tuple[bool, str]:
        if bot_role not in {"owner", "admin"}:
            return False, "机器人不是群主或管理员"
        if target_role == "owner":
            return False, "目标是群主"
        if bot_role == "admin" and target_role == "admin":
            return False, "目标是管理员，机器人无权移除"
        return True, ""

    @staticmethod
    def _normalize_role(value: Any) -> str:
        role = str(value or "").strip().lower()
        if role in {"owner", "admin", "member"}:
            return role
        return "unknown"

    @staticmethod
    def _extract_object(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                return data
            return result
        return {}

    @staticmethod
    def _group_name(group: dict[str, Any]) -> str:
        group_id = str(group.get("group_id", "")).strip()
        return str(group.get("group_name", "")).strip() or f"群 {group_id}"

    @staticmethod
    def _brief_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:100]
