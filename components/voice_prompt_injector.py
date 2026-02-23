"""POST_LLM 事件处理器：常驻语音模式下注入语音文本写作指导"""

from typing import Optional, Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_events_handler import (
    BaseEventHandler,
    CustomEventHandlerResult,
    EventType,
    MaiMessages,
)

from .tts_tool import is_always_voice

logger = get_logger("minimax_tts_plugin")

VOICE_TEXT_GUIDELINES = (
    "\n[语音文本写作要求]\n"
    "本次回复将被合成为语音，请严格遵守以下要求：\n"
    "- 用自然口语风格书写，像真人说话一样，避免书面化表达\n"
    "- 适当插入拟声词增加真人感（不要每句都加，自然地穿插）：\n"
    "  笑: (laughs) (chuckle)\n"
    "  呼吸: (breath) (pant) (inhale) (exhale) (gasps)\n"
    "  情绪: (sighs) (groans) (snorts) (humming)\n"
    "  其他: (coughs) (clear-throat) (sniffs) (sneezes) (burps) (lip-smacking) (hissing) (emm)\n"
    "- 在需要停顿的地方用 <#秒数#> 标记，如思考时 <#0.5#>、转折时 <#0.8#>、强调前 <#1.0#>\n"
    "- 用语气词和停顿让节奏自然，如：嗯、啊、呢、吧、哦、嘿\n"
    "- 不要使用 emoji、括号注释、【】标记等无法朗读的符号\n"
    "- 不要分点列举或使用序号，用连贯的口语表达\n"
)


class VoicePromptInjector(BaseEventHandler):
    """POST_LLM 阶段：常驻语音模式或概率触发时注入写作指导

    确保 LLM 在生成文本前就知道这段文字将被合成为语音，
    从而使用口语风格、拟声词和停顿标记。
    """

    event_type = EventType.POST_LLM
    handler_name = "minimax_voice_prompt_injector"
    handler_description = "常驻语音模式下向 LLM 注入语音文本写作指导"
    intercept_message = True
    weight = 500

    async def execute(
        self, message: MaiMessages | None
    ) -> Tuple[bool, bool, Optional[str], Optional[CustomEventHandlerResult], Optional[MaiMessages]]:
        try:
            if not message or not message.llm_prompt:
                return True, True, None, None, message

            stream_id = message.stream_id
            if not stream_id:
                return True, True, None, None, message

            # 仅在常驻语音模式下注入
            if not await is_always_voice(stream_id):
                return True, True, None, None, message

            # 注入写作指导到 prompt 前面
            new_prompt = VOICE_TEXT_GUIDELINES + "\n" + message.llm_prompt
            message.modify_llm_prompt(new_prompt, suppress_warning=True)

            logger.debug(f"[PromptInjector] 已注入语音写作指导: {stream_id}")
            return True, True, "已注入", None, message

        except Exception as e:
            logger.error(f"[PromptInjector] 执行出错: {e}")
            return True, True, f"出错: {e}", None, message
