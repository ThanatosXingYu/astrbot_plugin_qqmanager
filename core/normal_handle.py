import asyncio
import re

from astrbot.core.message.components import At, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..data import QQAdminDB
from ..global_blacklist import GlobalBlacklistService
from ..utils import get_ats, get_nickname


class NormalHandle:
    def __init__(self, config: PluginConfig, db: QQAdminDB):
        self.cfg = config
        self.db = db

    async def set_group_ban(
        self,
        event: AiocqhttpMessageEvent,
        ban_time: int | None = None,
    ):
        """禁言 60 @user"""
        group_config = self.db.get_group_snapshot(event.get_group_id())
        ban_time = self.cfg.get_ban_time_with_range(
            group_config.get("random_ban_time"), ban_time
        )

        for tid in get_ats(event):
            try:
                await event.bot.set_group_ban(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    duration=ban_time,
                )
            except Exception:
                pass
        event.stop_event()

    async def cancel_group_ban(self, event: AiocqhttpMessageEvent):
        """解禁@user"""
        for tid in get_ats(event):
            await event.bot.set_group_ban(
                group_id=int(event.get_group_id()), user_id=int(tid), duration=0
            )
        event.stop_event()

    async def set_group_kick(self, event: AiocqhttpMessageEvent):
        """踢 @user"""
        for tid in get_ats(event):
            target_name = await get_nickname(event, user_id=tid)
            await event.bot.set_group_kick(
                group_id=int(event.get_group_id()),
                user_id=int(tid),
                reject_add_request=False,
            )
            await event.send(event.plain_result(f"已将【{tid}-{target_name}】踢出本群"))

    @staticmethod
    def _extract_target_ids(event: AiocqhttpMessageEvent) -> list[str]:
        target_ids = get_ats(event)
        raw = event.message_str.partition(" ")[2]
        for normalized in re.findall(r"\d+", raw):
            if normalized not in target_ids:
                target_ids.append(normalized)
        return target_ids

    @staticmethod
    def _brief_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:80]

    async def _current_group_label(self, event: AiocqhttpMessageEvent) -> str:
        group_id = event.get_group_id()
        group_name = f"群 {group_id}"
        try:
            info = await event.bot.get_group_info(group_id=int(group_id))
            data = info.get("data") if isinstance(info, dict) else None
            source = data if isinstance(data, dict) else info
            group_name = str(source.get("group_name") or group_name)
        except Exception:
            pass
        return f"{group_name}({group_id})"

    async def _kick_current_group_user(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str,
    ) -> str:
        try:
            target_name = await get_nickname(event, user_id=user_id)
        except Exception:
            target_name = user_id

        try:
            await event.bot.set_group_kick(
                group_id=int(event.get_group_id()),
                user_id=int(user_id),
                reject_add_request=True,
            )
            return f"{user_id}-{target_name} 已踢出"
        except Exception as exc:
            return f"{user_id}-{target_name} 踢出失败：{self._brief_error(exc)}"

    async def set_group_block(
        self,
        event: AiocqhttpMessageEvent,
        blacklist_service: GlobalBlacklistService,
    ):
        """拉黑 @user / 拉黑 QQ：加入总黑名单，当前群立即踢出，其他群私聊确认"""
        target_ids = self._extract_target_ids(event)
        if not target_ids:
            await event.send(event.plain_result("请@要拉黑的群友，或填写QQ号"))
            return

        if event.get_self_id() in target_ids:
            await event.send(event.plain_result("不能把机器人自己加入总黑名单"))
            return

        added = blacklist_service.add_global_ids(target_ids)
        added_text = "、".join(added) if added else "无新增"

        current_results = []
        for user_id in target_ids:
            result = await self._kick_current_group_user(event, user_id)
            current_results.append(f"{user_id}：{result}")

        group_name = await self._current_group_label(event)
        for user_id, result in zip(target_ids, current_results):
            await blacklist_service.create_pending_kick_task(
                user_id,
                notice_group_id=event.get_group_id(),
                origin_group_name=group_name,
                current_group_result=result,
                fallback_client=event.bot,
            )

        await event.send(
            event.plain_result(
                "\n".join(
                    [
                        f"已写入总黑名单：{added_text}",
                        "当前群处理：",
                        *current_results,
                        "其他群处理清单已尝试私发给超管确认。",
                    ]
                )
            )
        )

    async def remove_global_block(
        self,
        event: AiocqhttpMessageEvent,
        blacklist_service: GlobalBlacklistService,
    ):
        """删除总黑名单 QQ"""
        target_ids = self._extract_target_ids(event)
        if not target_ids:
            await event.send(event.plain_result("请填写要移出总黑名单的QQ号"))
            return

        removed = blacklist_service.remove_global_ids(target_ids)
        if removed:
            await event.send(event.plain_result(f"已移出总黑名单：{'、'.join(removed)}"))
            return

        await event.send(event.plain_result("总黑名单中没有这些QQ号"))

    async def remove_leave_block(self, event: AiocqhttpMessageEvent):
        """删除当前群退群黑名单 QQ"""
        target_ids = self._extract_target_ids(event)
        if not target_ids:
            await event.send(event.plain_result("请填写要移出退群黑名单的QQ号"))
            return

        removed = await self.db.remove_many(
            event.get_group_id(),
            "leave_block_ids",
            target_ids,
            include_default_aggregate=True,
        )
        if removed:
            await event.send(
                event.plain_result(f"已移出退群黑名单：{'、'.join(removed)}")
            )
            return

        await event.send(event.plain_result("当前群退群黑名单中没有这些QQ号"))

    async def delete_msg(self, event: AiocqhttpMessageEvent):
        """(引用消息)撤回 | 撤回 @某人(默认bot) 数量(默认50)"""
        client = event.bot
        chain = event.get_messages()
        if not chain:
            return
        first_seg = chain[0]
        if isinstance(first_seg, Reply):
            try:
                await client.delete_msg(message_id=int(first_seg.id))
            except Exception:
                await event.send(event.plain_result("我无权撤回这条消息"))
            finally:
                event.stop_event()
        elif any(isinstance(seg, At) for seg in chain):
            target_ids = get_ats(event) or [event.get_self_id()]
            target_ids = {str(uid) for uid in target_ids}

            parts = event.message_str.split()
            end_arg = parts[-1] if parts else ""
            count = int(end_arg) if end_arg.isdigit() else 50

            payloads = {
                "group_id": int(event.get_group_id()),
                "message_seq": 0,
                "count": count,
                "reverseOrder": True,
            }
            result: dict = await client.api.call_action(
                "get_group_msg_history", **payloads
            )

            messages = list(reversed(result.get("messages", [])))
            delete_count = 0
            sem = asyncio.Semaphore(10)

            # 撤回消息
            async def try_delete(message: dict):
                nonlocal delete_count
                if str(message["sender"]["user_id"]) not in target_ids:
                    return
                async with sem:
                    try:
                        await client.delete_msg(message_id=message["message_id"])
                        delete_count += 1
                    except Exception:
                        pass

            # 并发撤回
            tasks = [try_delete(msg) for msg in messages]
            await asyncio.gather(*tasks)

            await event.send(
                event.plain_result(f"已从{count}条消息中撤回{delete_count}条")
            )
