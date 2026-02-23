"""AFTER_LLM 事件处理器：检测 TTS 标志并合成语音"""

import random
import re
from typing import Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_events_handler import BaseEventHandler, EventType, MaiMessages
from src.plugin_system.apis import send_api

from ..core.api_client import MiniMaxAPIClient
from ..core.voice_clone import VoiceCloneManager
from .tts_tool import consume_tts_pending, is_always_voice

logger = get_logger("minimax_tts_plugin")

# 共享的管理器实例（由 plugin.py 在组装时设置）
_voice_clone_manager: VoiceCloneManager | None = None


def set_voice_clone_manager(mgr: VoiceCloneManager) -> None:
    global _voice_clone_manager
    _voice_clone_manager = mgr


class MiniMaxTTSEventHandler(BaseEventHandler):
    """AFTER_LLM 阶段检查 TTS 标志并合成语音

    触发优先级：常驻语音模式 > LLM 工具标记 > 概率随机触发
    """

    event_type = EventType.AFTER_LLM
    handler_name = "minimax_tts_handler"
    handler_description = "检测 TTS 标志，使用主回复文本合成语音"
    intercept_message = True
    weight = 150

    async def execute(
        self, message: MaiMessages | None
    ) -> Tuple[bool, bool, str | None, None, MaiMessages | None]:
        try:
            if not message or not message.llm_response_content:
                return True, True, "无内容", None, message

            stream_id = message.stream_id
            if not stream_id:
                return True, True, "无 stream_id", None, message

            # ── 判断是否需要 TTS ──
            should_tts = False
            pending_emotion = None

            # 1. 常驻语音模式（最高优先级）
            if await is_always_voice(stream_id):
                should_tts = True
                # 常驻模式下也消费 LLM 标记的情绪（如果有）
                was_pending, pending_emotion = await consume_tts_pending(stream_id)
                logger.debug(f"[EventHandler] 常驻语音模式触发: {stream_id}")

            # 2. LLM 工具标记
            if not should_tts:
                was_pending, pending_emotion = await consume_tts_pending(stream_id)
                if was_pending:
                    should_tts = True

            # 3. 概率随机触发
            if not should_tts:
                probability = self.get_config("minimax.random_voice_probability", 0.0)
                if probability > 0 and random.random() < probability:
                    should_tts = True
                    logger.info(f"[EventHandler] 概率触发语音 (p={probability}): {stream_id}")

            if not should_tts:
                return True, True, "未触发TTS", None, message

            # ── 合成语音 ──
            text = message.llm_response_content.strip()
            text = re.sub(r'【[^】]*】', '', text)
            text = re.sub(r'\s+', ' ', text).strip()

            if not text:
                logger.warning("主回复文本为空")
                return True, True, "文本为空", None, message

            voice_id = self.get_config("minimax.voice_id", "")
            api_key = self.get_config("minimax.api_key", "")

            if not api_key:
                logger.error("未配置 API Key")
                return True, True, "未配置API Key", None, message
            if not voice_id:
                logger.error("未配置音色")
                return True, True, "未配置音色", None, message

            logger.info(f"[EventHandler] 语音合成完整回复: {text[:50]}...")

            # ── 情绪决策：LLM 指定 > 配置默认值 > MiniMax 内置自动推断 ──
            # 不传 emotion 参数时 MiniMax 模型会自动根据文本选择最自然的情绪
            final_emotion = pending_emotion

            client = await MiniMaxAPIClient.get_instance()
            audio_path = await client.auto_synthesize(
                self.get_config, text, voice_id, override_emotion=final_emotion
            )

            if audio_path and stream_id:
                if _voice_clone_manager:
                    await _voice_clone_manager.touch_voice(voice_id)

                await send_api.custom_to_stream(
                    message_type="voiceurl",
                    content=audio_path,
                    stream_id=stream_id,
                    typing=False,
                    set_reply=False,
                    reply_message=None,
                    storage_message=False,
                )

                message.modify_llm_response_content("")
                return True, False, None, None, message
            else:
                logger.error("[EventHandler] 语音合成失败，回退到文本发送")
                return True, True, "合成失败", None, message

        except Exception as e:
            logger.error(f"[EventHandler] 执行出错: {e}")
            return True, True, f"出错: {e}", None, message
