from datetime import datetime

from astrbot.core.message.components import At, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

def print_logo():
    """打印欢迎 Logo"""
    logo = r"""
 ________  __                  __            __
|        \|  \                |  \          |  \
 \$$$$$$$$| $$____    ______  | $$  _______ | $$  ______    ______
    /  $$ | $$    \  |      \ | $$ /       \| $$ |      \  /      \
   /  $$  | $$$$$$$\  \$$$$$$\| $$|  $$$$$$$| $$  \$$$$$$\|  $$$$$$\
  /  $$   | $$  | $$ /      $$| $$ \$$    \ | $$ /      $$| $$   \$$
 /  $$___ | $$  | $$|  $$$$$$$| $$ _\$$$$$$\| $$|  $$$$$$$| $$
|  $$    \| $$  | $$ \$$    $$| $$|       $$| $$ \$$    $$| $$
 \$$$$$$$$ \$$   \$$  \$$$$$$$ \$$ \$$$$$$$  \$$  \$$$$$$$ \$$

        """
    print("\033[92m" + logo + "\033[0m")  # 绿色文字
    print("\033[94m欢迎使用群管插件！\033[0m")  # 蓝色文字


async def get_nickname(event: AiocqhttpMessageEvent, user_id: int | str) -> str:
    """获取指定群友的群昵称或 Q 名，群接口失败/空结果自动降级到陌生人资料"""
    user_id = int(user_id)
    client = event.bot
    group_id = event.get_group_id()
    info = {}

    # 在群里就先试群资料，任何异常或空结果都跳过
    if group_id.isdigit():
        try:
            info = (
                await client.get_group_member_info(
                    group_id=int(group_id), user_id=user_id
                )
                or {}
            )
        except Exception:
            pass

    # 群资料没拿到就降级到陌生人资料
    if not info:
        try:
            info = await client.get_stranger_info(user_id=user_id) or {}
        except Exception:
            pass

    # 依次取群名片、QQ 昵称、通用 nick，兜底数字 UID
    return info.get("card") or info.get("nickname") or info.get("nick") or str(user_id)


def get_ats(event: AiocqhttpMessageEvent) -> list[str]:
    """获取被at者们的id列表"""
    return [
        str(seg.qq)
        for seg in event.get_messages()
        if (isinstance(seg, At) and str(seg.qq) != event.get_self_id())
    ]


def get_reply_message_str(event: AiocqhttpMessageEvent) -> str | None:
    """
    获取被引用的消息解析后的纯文本消息字符串。
    """
    return next(
        (
            seg.message_str
            for seg in event.message_obj.message
            if isinstance(seg, Reply)
        ),
        "",
    )


def format_time(timestamp):
    """格式化时间戳"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def parse_bool(mode: str | bool | None):
    """解析布尔值"""
    mode = str(mode).strip().lower()
    match mode:
        case "开" | "开启" | "启用" | "on" | "true" | "1" | "是" | "真":
            return True
        case "关" | "关闭" | "禁用" | "off" | "false" | "0" | "否" | "假":
            return False
        case _:
            return None
