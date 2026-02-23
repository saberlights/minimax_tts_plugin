"""/voice_always 命令：切换常驻语音模式"""

from typing import Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand

from .tts_tool import toggle_always_voice

logger = get_logger("minimax_tts_plugin")


class VoiceAlwaysCommand(BaseCommand):
    """切换常驻语音模式，开启后 bot 每条回复都使用语音"""

    command_name = "voice_always"
    command_description = "切换常驻语音模式（每条回复都使用语音）"
    command_pattern = r"^/voice_always$"
    command_help = "用法：/voice_always（再次执行关闭）"
    command_examples = ["/voice_always"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            chat_stream = getattr(self.message, "chat_stream", None)
            stream_id = getattr(chat_stream, "stream_id", None) if chat_stream else None

            if not stream_id:
                await self.send_text("未获取到聊天信息")
                return False, "无 stream_id", True

            now_on = await toggle_always_voice(stream_id)

            if now_on:
                await self.send_text("常驻语音模式已开启，bot 每条回复都将使用语音。\n再次发送 /voice_always 关闭。")
                logger.info(f"常驻语音模式开启: {stream_id}")
            else:
                await self.send_text("常驻语音模式已关闭。")
                logger.info(f"常驻语音模式关闭: {stream_id}")

            return True, "已切换", True

        except Exception as e:
            logger.error(f"切换常驻语音出错: {e}")
            await self.send_text(f"出错: {e}")
            return False, str(e), True
