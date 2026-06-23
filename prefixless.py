from __future__ import annotations

import re
from typing import Any

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


class PrefixlessCommandDispatcher:
    COMMAND_ALIASES = {
        "群管帮助": "群管帮助",
        "QQ管理帮助": "群管帮助",
        "qq群管帮助": "群管帮助",
        "禁言": "禁言",
        "解禁": "解禁",
        "踢": "踢",
        "拉黑": "拉黑",
        "删除总黑名单": "删除总黑名单",
        "移除总黑名单": "删除总黑名单",
        "移出总黑名单": "删除总黑名单",
        "删除退群黑名单": "删除退群黑名单",
        "移除退群黑名单": "删除退群黑名单",
        "移出退群黑名单": "删除退群黑名单",
        "撤回": "撤回",
        "禁词禁言": "禁词禁言",
        "设置禁词": "设置禁词",
        "禁词": "设置禁词",
        "违禁词": "设置禁词",
        "内置禁词": "内置禁词",
        "刷屏禁言": "刷屏禁言",
        "开启宵禁": "开启宵禁",
        "关闭宵禁": "关闭宵禁",
        "进群审核": "进群审核",
        "进群白词": "进群白词",
        "进群黑词": "进群黑词",
        "未命中驳回": "未命中驳回",
        "进群等级": "进群等级",
        "进群次数": "进群次数",
        "进群黑名单": "进群黑名单",
        "批准": "批准",
        "同意进群": "批准",
        "驳回": "驳回",
        "拒绝进群": "驳回",
        "不批准": "驳回",
        "进群禁言": "进群禁言",
        "进群欢迎": "进群欢迎",
        "退群通知": "退群通知",
        "退群拉黑": "退群拉黑",
        "群友信息": "群友信息",
        "群管配置": "群管配置",
        "群管设置": "群管配置",
        "群管重置": "群管重置",
    }

    def __init__(self, plugin: Any):
        self.plugin = plugin

    async def handle(self, event: AiocqhttpMessageEvent) -> bool:
        command, tail = self._match(event.message_str)
        if not command:
            return False

        if str(event.get_sender_id()) not in self.plugin.cfg.admins_id:
            event.stop_event()
            return True

        await self._execute(command, event, tail)
        event.stop_event()
        return True

    def _match(self, text: str) -> tuple[str, str]:
        raw = str(text or "").strip()
        if not raw or raw.startswith(("/", "／")):
            return "", ""

        for command in sorted(self.COMMAND_ALIASES, key=len, reverse=True):
            if raw == command:
                return self.COMMAND_ALIASES[command], ""
            if raw.startswith(command):
                return self.COMMAND_ALIASES[command], raw[len(command) :].strip()
        return "", ""

    @staticmethod
    def _first_int(text: str) -> int | None:
        parts = str(text or "").strip().split(maxsplit=1)
        if parts and re.fullmatch(r"-?\d+", parts[0]):
            return int(parts[0])
        return None

    @staticmethod
    def _first_text(text: str) -> str | None:
        value = str(text or "").strip()
        return value or None

    @staticmethod
    def _two_text_args(text: str) -> tuple[str | None, str | None]:
        parts = str(text or "").strip().split(maxsplit=1)
        first = parts[0] if parts else None
        second = parts[1] if len(parts) > 1 else None
        return first, second

    async def _send_results(
        self,
        event: AiocqhttpMessageEvent,
        command_result: Any,
    ) -> None:
        if hasattr(command_result, "__aiter__"):
            async for item in command_result:
                if item is not None:
                    await event.send(item)
            return
        if hasattr(command_result, "__await__"):
            await command_result

    async def _execute(
        self,
        command: str,
        event: AiocqhttpMessageEvent,
        tail: str,
    ) -> None:
        plugin = self.plugin
        if command == "群管帮助":
            await event.send(event.plain_result(plugin._help_text()))
        elif command == "禁言":
            await self._send_results(
                event,
                plugin.set_group_ban(event, self._first_int(tail)),
            )
        elif command == "解禁":
            await self._send_results(event, plugin.cancel_group_ban(event))
        elif command == "踢":
            await self._send_results(event, plugin.set_group_kick(event))
        elif command == "拉黑":
            await self._send_results(event, plugin.set_group_block(event))
        elif command == "删除总黑名单":
            await self._send_results(event, plugin.remove_global_block(event))
        elif command == "删除退群黑名单":
            await self._send_results(event, plugin.remove_leave_block(event))
        elif command == "撤回":
            await self._send_results(event, plugin.delete_msg(event))
        elif command == "禁词禁言":
            await self._send_results(
                event,
                plugin.handle_word_ban_time(event, self._first_int(tail)),
            )
        elif command == "设置禁词":
            await self._send_results(event, plugin.handle_builtin_ban_words(event))
        elif command == "内置禁词":
            await self._send_results(
                event,
                plugin.handle_ban_words(event, self._first_text(tail)),
            )
        elif command == "刷屏禁言":
            await self._send_results(
                event,
                plugin.handle_spamming_ban_time(event, self._first_int(tail)),
            )
        elif command == "开启宵禁":
            start_time, end_time = self._two_text_args(tail)
            await self._send_results(
                event,
                plugin.start_curfew(event, start_time, end_time),
            )
        elif command == "关闭宵禁":
            await self._send_results(event, plugin.stop_curfew(event))
        elif command == "进群审核":
            await self._send_results(
                event,
                plugin.handle_join_review(event, self._first_text(tail)),
            )
        elif command == "进群白词":
            await self._send_results(event, plugin.handle_accept_words(event))
        elif command == "进群黑词":
            await self._send_results(event, plugin.handle_reject_words(event))
        elif command == "未命中驳回":
            await self._send_results(
                event,
                plugin.handle_no_match_reject(event, self._first_text(tail)),
            )
        elif command == "进群等级":
            await self._send_results(
                event,
                plugin.handle_join_min_level(event, self._first_int(tail)),
            )
        elif command == "进群次数":
            await self._send_results(
                event,
                plugin.handle_join_max_time(event, self._first_int(tail)),
            )
        elif command == "进群黑名单":
            await self._send_results(event, plugin.handle_reject_ids(event))
        elif command == "批准":
            await self._send_results(event, plugin.agree_add_group(event, tail))
        elif command == "驳回":
            await self._send_results(event, plugin.refuse_add_group(event, tail))
        elif command == "进群禁言":
            await self._send_results(
                event,
                plugin.handle_join_ban(event, self._first_int(tail)),
            )
        elif command == "进群欢迎":
            await self._send_results(event, plugin.handle_join_welcome(event))
        elif command == "退群通知":
            await self._send_results(
                event,
                plugin.handle_leave_notify(event, self._first_text(tail)),
            )
        elif command == "退群拉黑":
            await self._send_results(
                event,
                plugin.handle_leave_block(event, self._first_text(tail)),
            )
        elif command == "群友信息":
            await self._send_results(event, plugin.get_group_member_list(event))
        elif command == "群管配置":
            await self._send_results(event, plugin.set_config(event))
        elif command == "群管重置":
            await self._send_results(
                event,
                plugin.reset_config(event, self._first_text(tail)),
            )
