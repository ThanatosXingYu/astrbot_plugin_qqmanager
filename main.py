import asyncio
import random
import re

from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.event_message_type import EventMessageType

from .config import PluginConfig
from .core import (
    BanproHandle,
    CurfewHandle,
    JoinHandle,
    MemberHandle,
    NormalHandle,
)
from .data import QQAdminDB
from .group_info_cache import QQGroupInfoCache
from .permission import (
    PermLevel,
    perm_manager,
    perm_required,
)
from .utils import print_logo
from .web import QQAdminWebController


class QQManagerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.cfg = PluginConfig(config, context)
        self.db = QQAdminDB(self.cfg)
        self.db.default_cfg = self.cfg.build_group_default_config()
        self.group_cache = QQGroupInfoCache(context, self.db)
        self.normal = NormalHandle(self.cfg, self.db)
        self.banpro = BanproHandle(self.cfg, self.db)
        self.join = JoinHandle(self.cfg, self.db)
        self.member = MemberHandle(self)
        self.curfew = CurfewHandle(self.context, self.cfg)
        self.web = QQAdminWebController(context, self.cfg, self.db, self.group_cache)
        self.web.register_routes()

    async def initialize(self):
        await self.db.init()

        asyncio.create_task(self.curfew.initialize())

        perm_manager.lazy_init(self.cfg, self.db)

        if random.random() < 0.01:
            print_logo()

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        """平台加载完成时"""
        if not self.curfew.curfew_managers:
            asyncio.create_task(self.curfew.initialize())

    @filter.command("群管帮助", alias={"QQ管理帮助", "qq群管帮助"})
    async def show_help(self, event: AiocqhttpMessageEvent):
        """查看 QQ 群管理插件命令帮助"""
        yield event.plain_result(
            "\n".join(
                [
                    "【QQ群管理帮助】",
                    "基础群管：禁言 <秒数> @群友 / 解禁 @群友 / 踢 @群友 / 拉黑 @群友",
                    "消息管理：撤回",
                    "风控审核：禁词禁言 <秒数> / 设置禁词 / 内置禁词 开|关 / 刷屏禁言 <秒数> / 开启宵禁 / 关闭宵禁",
                    "入群管理：进群审核 开|关 / 进群白词 / 进群黑词 / 进群黑名单 / 批准 / 驳回",
                    "群工具：群友信息",
                    "配置：群管配置 / 群管重置 <群号|all>，主人QQ可在 settings 面板或群管配置中设置。",
                ]
            )
        )

    @filter.command("禁言", desc="禁言 <秒数> @群友")
    @perm_required(PermLevel.ADMIN)
    async def set_group_ban(
        self, event: AiocqhttpMessageEvent, ban_time: int | None = None
    ):
        await self.normal.set_group_ban(event, ban_time)

    @filter.command("解禁", desc="解禁 @群友")
    @perm_required(PermLevel.ADMIN)
    async def cancel_group_ban(self, event: AiocqhttpMessageEvent):
        await self.normal.cancel_group_ban(event)

    @filter.command("踢", desc="踢 @群友")
    @perm_required(PermLevel.ADMIN)
    async def set_group_kick(self, event: AiocqhttpMessageEvent):
        await self.normal.set_group_kick(event)

    @filter.command("拉黑", desc="拉黑@群友")
    @perm_required(PermLevel.ADMIN)
    async def set_group_block(self, event: AiocqhttpMessageEvent):
        await self.normal.set_group_block(event)

    @filter.command("撤回")
    @perm_required(PermLevel.MEMBER)
    async def delete_msg(self, event: AiocqhttpMessageEvent):
        "(引用消息)撤回 | 撤回 <@群友> <消息数量>"
        await self.normal.delete_msg(event)

    @filter.command("禁词禁言")
    @perm_required(PermLevel.ADMIN, perm_key="word_ban")
    async def handle_word_ban_time(
        self, event: AiocqhttpMessageEvent, time: int | None = None
    ):
        """禁词禁言 <秒数>, 设为 0 表示关闭禁词检测"""
        await self.banpro.handle_word_ban_time(event, time)

    @filter.command("设置禁词", alias={"禁词", "违禁词"})
    @perm_required(PermLevel.ADMIN, perm_key="word_ban")
    async def handle_builtin_ban_words(self, event: AiocqhttpMessageEvent):
        """禁词 +词1 -词2, 带+-则增删, 不带则覆写"""
        await self.banpro.handle_ban_words(event)

    @filter.command("内置禁词")
    @perm_required(PermLevel.ADMIN, perm_key="word_ban")
    async def handle_ban_words(
        self, event: AiocqhttpMessageEvent, mode: str | bool | None = None
    ):
        """内置禁词 开/关"""
        await self.banpro.handle_builtin_ban_words(event, mode)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_ban_words(self, event: AiocqhttpMessageEvent):
        """自动检测违禁词，撤回并禁言"""
        if not event.is_admin():
            await self.banpro.on_ban_words(event)

    @filter.command("刷屏禁言")
    @perm_required(PermLevel.ADMIN, perm_key="spamming")
    async def handle_spamming_ban_time(
        self, event: AiocqhttpMessageEvent, time: int | None = None
    ):
        """刷屏禁言 <秒数>, 设为 0 表示关闭禁词检测"""
        await self.banpro.handle_spamming_ban_time(event, time)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def spamming_ban(self, event: AiocqhttpMessageEvent):
        """刷屏检测与禁言"""
        await self.banpro.spamming_ban(event)

    @filter.command("开启宵禁", desc="开启宵禁 HH:MM HH:MM")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @perm_required(PermLevel.ADMIN, perm_key="curfew")
    async def start_curfew(
        self,
        event: AiocqhttpMessageEvent,
        start_time: str | None = None,
        end_time: str | None = None,
    ):
        await self.curfew.start_curfew(event, start_time, end_time)

    @filter.command("关闭宵禁", desc="关闭本群的宵禁任务")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @perm_required(PermLevel.ADMIN, perm_key="curfew")
    async def stop_curfew(self, event: AiocqhttpMessageEvent):
        await self.curfew.stop_curfew(event)

    @filter.command("进群审核")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_join_review(
        self, event: AiocqhttpMessageEvent, mode: str | bool | None = None
    ):
        "进群审核 开/关，所有进群审核功能的总开关"
        await self.join.handle_join_review(event, mode)

    @filter.command("进群白词")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_accept_words(self, event: AiocqhttpMessageEvent):
        "设置/查看自动批准进群的关键词（空格隔开，无参数表示查看）"
        await self.join.handle_accept_words(event)

    @filter.command("进群黑词")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_reject_words(self, event: AiocqhttpMessageEvent):
        "设置/查看进群黑名单关键词（空格隔开，无参数表示查看）"
        await self.join.handle_reject_words(event)

    @filter.command("未命中驳回", desc="未命中白词自动驳回 开/关")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_no_match_reject(
        self, event: AiocqhttpMessageEvent, mode: str | bool | None = None
    ):
        "设置/查看是否拒绝无关键词的进群申请（无参数表示查看）"
        await self.join.handle_no_match_reject(event, mode)

    @filter.command("进群等级")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_join_min_level(
        self, event: AiocqhttpMessageEvent, level: int | None = None
    ):
        "设置/查看本群进群等级门槛，（0表示不限制，无参数表示查看）"
        await self.join.handle_join_min_level(event, level)

    @filter.command("进群次数")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_join_max_time(
        self, event: AiocqhttpMessageEvent, time: int | None = None
    ):
        "设置/查看未命中进群关键词多少次后拉黑（0表示不限制，无参数表示查看）"
        await self.join.handle_join_max_time(event, time)

    @filter.command("进群黑名单")
    @perm_required(PermLevel.ADMIN, perm_key="join")
    async def handle_reject_ids(self, event: AiocqhttpMessageEvent):
        "进群黑名单 +QQ -QQ, 带+-则增删, 不带则覆写"
        await self.join.handle_block_ids(event)

    @filter.command("批准", alias={"同意进群"}, desc="批准进群申请")
    @perm_required(PermLevel.ADMIN, perm_key="approve")
    async def agree_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        await self.join.agree_add_group(event, extra)

    @filter.command("驳回", alias={"拒绝进群", "不批准"}, desc="驳回进群申请")
    @perm_required(PermLevel.ADMIN, perm_key="approve")
    async def refuse_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        await self.join.refuse_add_group(event, extra)

    @filter.command("进群禁言")
    @perm_required(PermLevel.ADMIN, perm_key="welcome")
    async def handle_join_ban(
        self, event: AiocqhttpMessageEvent, time: int | None = None
    ):
        "进群禁言 <秒数>，设为 0 表示本群不启用该功能"
        await self.join.handle_join_ban(event, time)

    @filter.command("进群欢迎")
    @perm_required(PermLevel.MEMBER, perm_key="welcome")
    async def handle_join_welcome(self, event: AiocqhttpMessageEvent):
        await self.join.handle_join_welcome(event)

    @filter.command("退群通知")
    @perm_required(PermLevel.MEMBER, perm_key="leave")
    async def handle_leave_notify(
        self, event: AiocqhttpMessageEvent, mode: str | bool | None = None
    ):
        """退群通知 开/关"""
        await self.join.handle_leave_notify(event, mode)

    @filter.command("退群拉黑")
    @perm_required(PermLevel.ADMIN, perm_key="leave")
    async def handle_leave_block(
        self, event: AiocqhttpMessageEvent, mode: str | bool | None = None
    ):
        "退群拉黑 开/关, 拉黑后下次进群直接自动拒绝"
        await self.join.handle_leave_block(event, mode)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        await self.join.event_monitoring(event)

    @filter.command("群友信息", desc="查看群友信息")
    @perm_required(PermLevel.MEMBER)
    async def get_group_member_list(self, event: AiocqhttpMessageEvent):
        await self.member.get_group_member_list(event)

    @filter.command("群管配置", alias={"群管设置"})
    @perm_required(PermLevel.MEMBER, check_at=False)
    async def set_config(self, event: AiocqhttpMessageEvent):
        """群管配置 <群号 | 留空> <配置串>"""
        raw: str = event.message_str.partition(" ")[2].strip()
        if not raw:  # 空串，仅查询
            gid = event.get_group_id()
            config_str = await self.db.export_cn_lines(gid)
            yield event.plain_result(f"【群管配置】\n{config_str}")
            return

        # 正则：^(\d+)\s+(.+)  捕获“数字 + 空格 + 剩余串”
        m = re.match(r"(\d+)\s+(.+)", raw)
        if m:
            gid = str(m.group(1))
            arg = m.group(2)
        else:
            gid = event.get_group_id()
            arg = raw

        # 更新配置
        await self.db.import_cn_lines(gid, arg)
        config_str = await self.db.export_cn_lines(gid)
        yield event.plain_result(f"【群管配置】更新:\n{config_str}")

    @filter.command("群管重置")
    @perm_required(PermLevel.MEMBER, check_at=False)
    async def reset_config(
        self, event: AiocqhttpMessageEvent, group_id: str | int | None = None
    ):
        """群管重置 <群号 | all>"""
        gid = group_id or event.get_group_id()
        if gid == "all" and event.is_admin():
            await self.db.reset_to_default()
            yield event.plain_result("已重置所有群的群管配置")
        else:
            await self.db.reset_to_default(str(gid))
            yield event.plain_result("已重置本群的群管配置")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await self.curfew.stop_all_tasks()
        await self.db.close()
        logger.info("插件 astrbot_plugin_qqmanager 已优雅关闭")
