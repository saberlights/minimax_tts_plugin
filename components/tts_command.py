"""/minimax 命令：手动触发语音合成"""

from typing import Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand

from ..core.api_client import MiniMaxAPIClient

logger = get_logger("minimax_tts_plugin")


class MiniMaxTTSCommand(BaseCommand):
    """手动命令触发的语音合成"""

    command_name = "minimax_tts_command"
    command_description = "将文本转换为语音"
    # 修正正则：贪婪匹配全部文本，移除内联 voice_id 参数
    command_pattern = r"^/minimax\s+(?P<text>.+)$"
    command_help = "用法：/minimax <文本>"
    command_examples = ["/minimax 你好", "/minimax こんにちは"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            text = self.matched_groups.get("text", "").strip()

            if not text:
                await self.send_text("请输入文本")
                return False, "缺少文本", True

            voice_id = self.get_config("minimax.voice_id", "")
            api_key = self.get_config("minimax.api_key", "")

            if not api_key:
                await self.send_text("未配置 API Key")
                return False, "未配置 API Key", True
            if not voice_id:
                await self.send_text("未配置音色")
                return False, "未配置音色", True

            logger.info(f"语音合成: {text[:50]}...")

            # 使用 auto_synthesize 自动选择同步/流式/异步
            client = await MiniMaxAPIClient.get_instance()
            audio_path = await client.auto_synthesize(
                self.get_config, text, voice_id
            )

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=audio_path)
                logger.info("语音发送成功")
                return True, "成功", True
            else:
                await self.send_text("合成失败")
                return False, "合成失败", True

        except Exception as e:
            logger.error(f"执行出错: {e}")
            await self.send_text(f"出错: {e}")
            return False, str(e), True
