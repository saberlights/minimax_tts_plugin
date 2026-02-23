"""LLM 工具（request_voice_reply）—— 设置 TTS 标志"""

import asyncio
from typing import Any, Set

from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool
from src.plugin_system.base.component_types import ToolParamType

logger = get_logger("minimax_tts_plugin")

# 受 Lock 保护的全局状态
_lock = asyncio.Lock()
_tts_pending_chats: Set[str] = set()
_tts_always_chats: Set[str] = set()  # 常驻语音模式的 chat


async def mark_tts_pending(chat_id: str) -> None:
    """标记某个 chat 需要 TTS"""
    async with _lock:
        _tts_pending_chats.add(chat_id)


async def consume_tts_pending(chat_id: str) -> bool:
    """消费 TTS 标志，返回是否已标记。"""
    async with _lock:
        if chat_id not in _tts_pending_chats:
            return False
        _tts_pending_chats.discard(chat_id)
        return True


async def is_tts_pending(chat_id: str) -> bool:
    async with _lock:
        return chat_id in _tts_pending_chats


async def toggle_always_voice(chat_id: str) -> bool:
    """切换常驻语音模式，返回切换后的状态（True=开启）"""
    async with _lock:
        if chat_id in _tts_always_chats:
            _tts_always_chats.discard(chat_id)
            return False
        else:
            _tts_always_chats.add(chat_id)
            return True


async def is_always_voice(chat_id: str) -> bool:
    async with _lock:
        return chat_id in _tts_always_chats


class MiniMaxTTSTool(BaseTool):
    """文本转语音工具 - 供 LLM 调用，设置 TTS 标志"""

    name = "request_voice_reply"
    description = """当用户消息中包含以下任一关键词或表达时，**必须**调用此工具以语音形式回复：

**强制触发关键词**（包含即调用）：
- 语音: "语音"、"voice"、"音频"、"audio"
- 朗读: "朗读"、"念"、"读"、"说"、"讲"
- 声音: "声音"、"听"、"发音"
- 动作: "念出来"、"说出来"、"讲出来"、"读给我听"、"听一下"、"用声音"

**典型触发句式**：
- "用语音xxx"
- "发语音xxx"
- "语音回复xxx"
- "念xxx"
- "读xxx"
- "说xxx"
- "朗读xxx"

**特殊场景**（自主判断）：
- 诗歌、歌词、台词等适合朗读的文学内容
- 语言学习、发音练习
- 用户明确希望听到语气、情感的内容

**不触发的情况**：
- 普通对话交流（没有上述关键词）
- 技术问题、代码讨论
- 简短信息查询

优先级：关键词匹配 > 场景判断"""

    parameters = [
        ("enable", ToolParamType.BOOLEAN, "是否启用语音回复，默认true", False, None),
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """设置 TTS 标志，并根据 language_boost 配置指示语言"""
        try:
            enable = function_args.get("enable", True)

            if not self.chat_stream:
                return {
                    "tool_name": "request_voice_reply",
                    "content": "未获取到聊天信息",
                    "type": "tool_result",
                }

            chat_id = self.chat_stream.stream_id
            if not chat_id:
                return {
                    "tool_name": "request_voice_reply",
                    "content": "未获取到聊天信息",
                    "type": "tool_result",
                }

            if not enable:
                async with _lock:
                    _tts_pending_chats.discard(chat_id)
                return {
                    "tool_name": "request_voice_reply",
                    "content": "已取消语音回复标记。",
                    "type": "tool_result",
                }

            # 标记 TTS（不传情绪，交给 MiniMax 模型自动推断）
            await mark_tts_pending(chat_id)

            # 获取 language_boost 配置
            language_boost = self.get_config("minimax.language_boost", "auto")

            language_instruction = ""
            if language_boost and language_boost != "auto":
                language_map = {
                    "Japanese": "日语",
                    "Chinese": "中文",
                    "English": "英语",
                    "Korean": "韩语",
                    "French": "法语",
                    "German": "德语",
                    "Spanish": "西班牙语",
                    "Russian": "俄语",
                    "Arabic": "阿拉伯语",
                }
                target_language = language_map.get(language_boost, language_boost)
                language_instruction = f"**必须使用{target_language}回复。**"

            logger.info(f"[Tool] 已标记 chat {chat_id} 需要 TTS")

            content = (
                "已标记需要语音回复，将在回复生成后合成语音。\n"
                "**语音文本写作要求**：\n"
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
            if language_instruction:
                content += f"\n{language_instruction}"

            return {
                "tool_name": "request_voice_reply",
                "content": content,
                "type": "tool_result",
            }

        except Exception as e:
            logger.error(f"[Tool] 执行出错: {e}")
            return {
                "tool_name": "request_voice_reply",
                "content": f"出错: {str(e)}",
                "type": "tool_result",
            }
