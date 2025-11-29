"""MiniMax TTS 插件 - 文本转语音和音色克隆

基于 MiniMax Speech 2.6 API 的语音合成插件
API: https://api.minimaxi.com
文档: https://platform.minimaxi.com/document/T2A%20V2
"""

from typing import List, Tuple, Type, Optional, Any, Dict
import aiohttp
import asyncio
import os
import re
import json
from datetime import datetime
from src.common.logger import get_logger
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.base_tool import BaseTool
from src.plugin_system.base.base_events_handler import BaseEventHandler, EventType, MaiMessages
from src.plugin_system.base.component_types import ComponentInfo, ToolParamType
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.apis import send_api

logger = get_logger("minimax_tts_plugin")

# 全局标志存储：记录哪些chat需要TTS
_tts_pending_chats = set()

# 音色数据存储文件路径
VOICES_DATA_FILE = os.path.join(os.path.dirname(__file__), "cloned_voices.json")

# 音频文件存储目录
VOICE_AUDIOS_DIR = os.path.join(os.path.dirname(__file__), "voice_audios")


def load_cloned_voices() -> Dict[str, Dict[str, Any]]:
    """加载已克隆的音色数据"""
    if os.path.exists(VOICES_DATA_FILE):
        try:
            with open(VOICES_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载音色数据失败: {e}")
            return {}
    return {}


def save_cloned_voices(voices: Dict[str, Dict[str, Any]]) -> bool:
    """保存已克隆的音色数据"""
    try:
        with open(VOICES_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(voices, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存音色数据失败: {e}")
        return False


def resolve_audio_path(audio_path: str) -> Optional[str]:
    """解析音频路径，支持相对路径和绝对路径

    Args:
        audio_path: 音频路径（可以是文件名、相对路径或绝对路径）

    Returns:
        完整的绝对路径，如果文件不存在返回 None
    """
    # 如果是绝对路径且存在，直接返回
    if os.path.isabs(audio_path) and os.path.exists(audio_path):
        return audio_path

    # 尝试在 voice_audios 目录下查找
    # 1. 直接在 voice_audios 根目录
    path = os.path.join(VOICE_AUDIOS_DIR, audio_path)
    if os.path.exists(path):
        return path

    # 2. 在 main 子目录
    path = os.path.join(VOICE_AUDIOS_DIR, "main", audio_path)
    if os.path.exists(path):
        return path

    # 3. 在 prompts 子目录
    path = os.path.join(VOICE_AUDIOS_DIR, "prompts", audio_path)
    if os.path.exists(path):
        return path

    # 未找到
    return None


def list_audio_files() -> Dict[str, List[Dict[str, Any]]]:
    """列出 voice_audios 目录下的所有音频文件

    Returns:
        按目录分类的音频文件列表
    """
    result = {
        "main": [],
        "prompts": [],
        "root": []
    }

    audio_extensions = {".mp3", ".m4a", ".wav", ".flac"}

    try:
        # 扫描 main 目录
        main_dir = os.path.join(VOICE_AUDIOS_DIR, "main")
        if os.path.exists(main_dir):
            for filename in os.listdir(main_dir):
                if os.path.splitext(filename)[1].lower() in audio_extensions:
                    filepath = os.path.join(main_dir, filename)
                    stat = os.stat(filepath)
                    result["main"].append({
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })

        # 扫描 prompts 目录
        prompts_dir = os.path.join(VOICE_AUDIOS_DIR, "prompts")
        if os.path.exists(prompts_dir):
            for filename in os.listdir(prompts_dir):
                if os.path.splitext(filename)[1].lower() in audio_extensions:
                    filepath = os.path.join(prompts_dir, filename)
                    stat = os.stat(filepath)
                    result["prompts"].append({
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })

        # 扫描根目录
        if os.path.exists(VOICE_AUDIOS_DIR):
            for filename in os.listdir(VOICE_AUDIOS_DIR):
                filepath = os.path.join(VOICE_AUDIOS_DIR, filename)
                if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in audio_extensions:
                    stat = os.stat(filepath)
                    result["root"].append({
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })

    except Exception as e:
        logger.error(f"列出音频文件失败: {e}")

    return result


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


async def upload_audio_file(api_key: str, file_path: str, purpose: str) -> Optional[int]:
    """上传音频文件到 MiniMax

    Args:
        api_key: API密钥
        file_path: 音频文件路径
        purpose: 上传目的 (voice_clone 或 prompt_audio)

    Returns:
        file_id 或 None
    """
    try:
        url = "https://api.minimaxi.com/v1/files/upload"

        # 读取文件
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None

        with open(file_path, "rb") as f:
            file_data = f.read()

        # 构建表单数据
        form = aiohttp.FormData()
        form.add_field('purpose', purpose)
        form.add_field('file', file_data, filename=os.path.basename(file_path))

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"上传文件失败: {response.status} - {error_text}")
                    return None

                resp_json = await response.json()
                file_info = resp_json.get("file", {})
                file_id = file_info.get("file_id")

                if file_id:
                    logger.info(f"文件上传成功: {file_path} -> file_id={file_id}")
                    return file_id
                else:
                    logger.error(f"API未返回file_id: {resp_json}")
                    return None

    except Exception as e:
        logger.error(f"上传文件出错: {e}")
        return None


async def clone_voice_api(
    api_key: str,
    file_id: int,
    voice_id: str,
    test_text: str = "",
    model: str = "speech-2.6-hd",
    prompt_audio_id: Optional[int] = None,
    prompt_text: Optional[str] = None,
    need_noise_reduction: bool = False,
    need_volume_normalization: bool = False
) -> Tuple[bool, str, Optional[str]]:
    """调用音色克隆API

    Args:
        api_key: API密钥
        file_id: 待克隆音频的file_id
        voice_id: 自定义的音色ID
        test_text: 试听文本
        model: 使用的模型
        prompt_audio_id: 参考音频的file_id (可选)
        prompt_text: 参考音频的文本 (可选)
        need_noise_reduction: 是否降噪
        need_volume_normalization: 是否音量归一化

    Returns:
        (成功标志, 消息, 试听音频URL)
    """
    try:
        url = "https://api.minimaxi.com/v1/voice_clone"

        payload = {
            "file_id": file_id,
            "voice_id": voice_id,
            "need_noise_reduction": need_noise_reduction,
            "need_volume_normalization": need_volume_normalization
        }

        # 添加试听参数
        if test_text:
            payload["text"] = test_text
            payload["model"] = model

        # 添加参考音频
        if prompt_audio_id and prompt_text:
            payload["clone_prompt"] = {
                "prompt_audio": prompt_audio_id,
                "prompt_text": prompt_text
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"克隆API失败: {response.status} - {error_text}")
                    return False, f"API调用失败: {response.status}", None

                resp_json = await response.json()

        base_resp = resp_json.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)
        status_msg = base_resp.get("status_msg", "未知错误")

        if status_code != 0:
            # 特殊处理内容安全错误
            if status_code == 1026 or "sensitive" in status_msg.lower():
                error_msg = "音频内容未通过安全审核\n\n可能原因：\n"
                error_msg += "• 音频包含敏感内容\n"
                error_msg += "• 音频质量不佳导致误判\n"
                error_msg += "• 背景噪音被误识别\n\n"
                error_msg += "建议：\n"
                error_msg += "• 使用清晰的朗读音频\n"
                error_msg += "• 避免包含敏感词汇\n"
                error_msg += "• 启用降噪（config.toml中设置need_noise_reduction=true）\n"
                error_msg += "• 更换其他音频重试"
                logger.error(f"内容安全审核失败: {status_msg} (代码: {status_code})")
                return False, error_msg, None

            logger.error(f"克隆失败: {status_msg} (代码: {status_code})")
            return False, f"克隆失败: {status_msg} (错误代码: {status_code})", None

        # 检查内容安全
        input_sensitive = resp_json.get("input_sensitive", {})
        if isinstance(input_sensitive, dict):
            sensitive_type = input_sensitive.get("type", 0)
        else:
            # 如果 input_sensitive 是布尔值或其他类型
            sensitive_type = 0 if not input_sensitive else 1

        if sensitive_type != 0:
            return False, f"输入音频风控不通过，类型: {sensitive_type}", None

        demo_audio = resp_json.get("demo_audio", "")

        return True, "克隆成功", demo_audio if demo_audio else None

    except Exception as e:
        logger.error(f"克隆API调用出错: {e}")
        return False, f"出错: {e}", None


def call_minimax_api_sync(get_config_func, api_url: str, api_key: str, text: str, voice_id: str, timeout: int) -> Optional[str]:
    """同步调用 MiniMax API（由异步包装器调用）"""
    import asyncio

    async def _call_api():
        try:
            # 处理文本（在函数开始处，避免作用域问题）
            processed_text = text

            # 构建 voice_setting
            voice_setting = {
                "voice_id": voice_id,
                "speed": get_config_func("minimax.speed", 1.0),
                "vol": get_config_func("minimax.vol", 1.0),
                "pitch": int(get_config_func("minimax.pitch", 0)),
            }

            # 添加 emotion 参数（如果配置了）
            emotion = get_config_func("minimax.emotion", None)
            if emotion:
                voice_setting["emotion"] = emotion

            # 添加 text_normalization 参数
            if get_config_func("minimax.text_normalization", False):
                voice_setting["text_normalization"] = True

            # 添加 latex_read 参数
            if get_config_func("minimax.latex_read", False):
                voice_setting["latex_read"] = True

            # 自动在文本末尾添加停顿，防止语音被截断
            trailing_pause = get_config_func("minimax.trailing_pause", 0.0)
            if trailing_pause > 0:
                # 确保停顿标记在有效文本之后，范围 [0.01, 99.99]
                pause_duration = max(0.01, min(99.99, trailing_pause))
                processed_text = f"{processed_text}<#{pause_duration:.2f}#>"
                logger.debug(f"添加尾部停顿: {pause_duration}秒")

            request_data = {
                "model": get_config_func("minimax.model", "speech-2.6-hd"),
                "text": processed_text,
                "stream": False,
                "language_boost": get_config_func("minimax.language_boost", "auto"),
                "output_format": get_config_func("minimax.output_format", "hex"),
                "voice_setting": voice_setting,
                "audio_setting": {
                    "sample_rate": int(get_config_func("minimax.sample_rate", 32000)),
                    "bitrate": int(get_config_func("minimax.bitrate", 128000)),
                    "format": get_config_func("minimax.audio_format", "mp3"),
                    "channel": int(get_config_func("minimax.channel", 1)),
                }
            }

            # 添加 voice_modify（声音效果器）
            voice_modify = {}
            modify_pitch = get_config_func("minimax.voice_modify_pitch", None)
            modify_intensity = get_config_func("minimax.voice_modify_intensity", None)
            modify_timbre = get_config_func("minimax.voice_modify_timbre", None)
            sound_effects = get_config_func("minimax.sound_effects", None)

            if modify_pitch is not None:
                voice_modify["pitch"] = int(modify_pitch)
            if modify_intensity is not None:
                voice_modify["intensity"] = int(modify_intensity)
            if modify_timbre is not None:
                voice_modify["timbre"] = int(modify_timbre)
            if sound_effects:
                voice_modify["sound_effects"] = sound_effects

            if voice_modify:
                request_data["voice_modify"] = voice_modify

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(api_url, json=request_data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API调用失败: {response.status} - {error_text}")
                        return None
                    resp_json = await response.json()

            base_resp = resp_json.get("base_resp", {})
            if base_resp.get("status_code") != 0:
                logger.error(f"API返回错误: {base_resp.get('status_msg')} ({base_resp.get('status_code')})")
                return None

            data = resp_json.get("data", {})
            audio_value = data.get("audio")
            if not audio_value:
                logger.error("API未返回音频数据")
                return None

            output_format = get_config_func("minimax.output_format", "hex")
            if output_format == "hex":
                try:
                    audio_bytes = bytes.fromhex(audio_value)
                except ValueError as e:
                    logger.error(f"hex解码失败: {e}")
                    return None

                audio_format = get_config_func("minimax.audio_format", "mp3")
                audio_path = os.path.abspath(f"minimax_tts_output.{audio_format}")
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                logger.info(f"音频生成: {audio_path} ({len(audio_bytes)} 字节)")
                return audio_path

            elif output_format == "url":
                logger.info(f"获取音频URL: {audio_value}")
                return audio_value
            else:
                logger.error(f"不支持的输出格式: {output_format}")
                return None

        except asyncio.TimeoutError:
            logger.error("API超时")
            return None
        except Exception as e:
            logger.error(f"API调用出错: {e}")
            return None

    return asyncio.create_task(_call_api())


class MiniMaxTTSTool(BaseTool):
    """文本转语音工具 - 供LLM调用，设置TTS标志"""

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
        """设置TTS标志，并根据language_boost配置指示语言"""
        try:
            enable = function_args.get("enable", True)

            if enable and self.chat_stream:
                chat_id = self.chat_stream.stream_id
                _tts_pending_chats.add(chat_id)

                # 获取 language_boost 配置
                language_boost = self.get_config("minimax.language_boost", "auto")

                # 根据语言配置生成提示
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
                        "Arabic": "阿拉伯语"
                    }
                    target_language = language_map.get(language_boost, language_boost)
                    language_instruction = f"**必须使用{target_language}回复。**"

                logger.info(f"[Tool] 已标记chat {chat_id} 需要TTS，语言增强: {language_boost}")

                content = "已标记需要语音回复，将在回复生成后合成语音。"
                if language_instruction:
                    content += f"\n{language_instruction}"

                return {
                    "tool_name": "request_voice_reply",
                    "content": content,
                    "type": "tool_result"
                }
            else:
                return {
                    "tool_name": "request_voice_reply",
                    "content": "未获取到聊天信息",
                    "type": "tool_result"
                }

        except Exception as e:
            logger.error(f"[Tool] 执行出错: {e}")
            return {
                "tool_name": "request_voice_reply",
                "content": f"出错: {str(e)}",
                "type": "tool_result"
            }


class MiniMaxTTSEventHandler(BaseEventHandler):
    """AFTER_LLM阶段检查TTS标志并合成语音"""

    event_type = EventType.AFTER_LLM
    handler_name = "minimax_tts_handler"
    handler_description = "检测TTS标志，使用主回复文本合成语音"
    intercept_message = True  # 拦截消息，阻止文本发送
    weight = 150  # 大于smart_segmentation(100)，在分段之前执行

    async def execute(self, message: MaiMessages | None) -> Tuple[bool, bool, str | None, None, MaiMessages | None]:
        """执行TTS合成"""
        try:
            if not message or not message.llm_response_content:
                return True, True, "无内容", None, message

            stream_id = message.stream_id
            if not stream_id or stream_id not in _tts_pending_chats:
                # 未标记TTS，继续正常流程（包括切分和发送文本）
                return True, True, "未标记TTS", None, message

            # 移除标志
            _tts_pending_chats.discard(stream_id)

            # 保存原始完整文本
            text = message.llm_response_content.strip()
            voice_id = self.get_config("minimax.voice_id", "")

            if not text:
                logger.warning("主回复文本为空")
                return True, True, "文本为空", None, message

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                logger.error("未配置 API Key")
                return True, True, "未配置API Key", None, message

            if not voice_id:
                logger.error("未配置音色")
                return True, True, "未配置音色", None, message

            logger.info(f"[EventHandler] 语音合成完整回复: {text[:50]}...")

            task = call_minimax_api_sync(
                self.get_config,
                self.get_config("minimax.base_url", "https://api.minimaxi.com/v1/t2a_v2"),
                api_key,
                text,
                voice_id,
                self.get_config("minimax.timeout", 30)
            )
            audio_path = await task

            if audio_path and stream_id:
                # 通过stream发送语音
                await send_api.custom_to_stream(
                    message_type="voiceurl",
                    content=audio_path,
                    stream_id=stream_id,
                    typing=False,
                    set_reply=False,
                    reply_message=None,
                    storage_message=False,
                )

                # 清空文本内容，阻止后续的文本发送
                message.modify_llm_response_content("")

                # 返回True表示成功，False表示阻止后续文本发送
                return True, False, None, None, message
            else:
                logger.error("[EventHandler] 语音合成失败，继续发送文本")
                # 合成失败，允许继续发送文本
                return True, True, "合成失败", None, message

        except Exception as e:
            logger.error(f"[EventHandler] 执行出错: {e}")
            # 出错时允许继续发送文本
            return True, True, f"出错: {e}", None, message


class MiniMaxTTSCommand(BaseCommand):
    """手动命令触发的语音合成"""

    command_name = "minimax_tts_command"
    command_description = "将文本转换为语音"
    command_pattern = r"^/minimax\s+(?P<text>.+?)(?:\s+(?P<voice_id>\S+))?$"
    command_help = "用法：/minimax 你好世界 [音色ID]"
    command_examples = ["/minimax 你好", "/minimax こんにちは"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            text = self.matched_groups.get("text", "").strip()
            voice_id = self.matched_groups.get("voice_id", "") or self.get_config("minimax.voice_id", "")

            if not text:
                await self.send_text("❌ 请输入文本")
                return False, "缺少文本", True

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                await self.send_text("❌ 未配置 API Key")
                return False, "未配置 API Key", True

            if not voice_id:
                await self.send_text("❌ 未配置音色")
                return False, "未配置音色", True

            logger.info(f"语音合成: {text[:50]}...")

            task = call_minimax_api_sync(
                self.get_config,
                self.get_config("minimax.base_url", "https://api.minimaxi.com/v1/t2a_v2"),
                api_key,
                text,
                voice_id,
                self.get_config("minimax.timeout", 30)
            )
            audio_path = await task

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=audio_path)
                logger.info("语音发送成功")
                return True, "成功", True
            else:
                await self.send_text("❌ 合成失败")
                return False, "合成失败", True

        except Exception as e:
            logger.error(f"执行出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class CloneVoiceCommand(BaseCommand):
    """音色克隆命令"""

    command_name = "clone_voice"
    command_description = "克隆音色并保存"
    command_pattern = r"^/clone_voice\s+(?P<audio_path>\S+)\s+(?P<voice_id>\S+)(?:\s+(?P<prompt_audio>\S+)(?:\s+(?P<prompt_text>.+?))?)?$"
    command_help = """用法：/clone_voice <音频文件路径> <音色ID> [参考音频路径] [参考文本]

示例：
  /clone_voice /path/to/audio.mp3 my_voice_001
  /clone_voice /path/to/audio.mp3 my_voice_002 /path/to/prompt.mp3 这是参考文本

说明：
  - 音频文件：10秒-5分钟，mp3/m4a/wav格式，≤20MB
  - 音色ID：8-256字符，首字符必须为字母
  - 参考音频（可选）：<8秒，用于增强克隆效果
  - 参考文本（可选）：参考音频对应的文本"""
    command_examples = [
        "/clone_voice /tmp/voice.mp3 MyVoice001",
        "/clone_voice /tmp/voice.wav MyVoice002 /tmp/prompt.mp3 你好世界"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            audio_path = self.matched_groups.get("audio_path", "").strip()
            voice_id = self.matched_groups.get("voice_id", "").strip()
            prompt_audio = self.matched_groups.get("prompt_audio", "")
            prompt_text = self.matched_groups.get("prompt_text", "")

            if prompt_audio:
                prompt_audio = prompt_audio.strip()
            if prompt_text:
                prompt_text = prompt_text.strip()

            # 验证参数
            if not audio_path or not voice_id:
                await self.send_text("❌ 缺少必需参数\n" + self.command_help)
                return False, "缺少参数", True

            # 验证 voice_id 格式
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{7,255}$", voice_id):
                await self.send_text("❌ 音色ID格式错误\n要求：8-256字符，首字符为字母，允许字母、数字、_、-")
                return False, "voice_id格式错误", True

            # 检查是否已存在
            voices = load_cloned_voices()
            if voice_id in voices:
                await self.send_text(f"❌ 音色ID '{voice_id}' 已存在，请使用其他ID或先删除现有音色")
                return False, "voice_id已存在", True

            # 解析并验证音频文件路径
            resolved_audio_path = resolve_audio_path(audio_path)
            if not resolved_audio_path:
                await self.send_text(f"❌ 音频文件不存在: {audio_path}\n提示：可以使用 /list_audio 查看可用音频")
                return False, "文件不存在", True
            audio_path = resolved_audio_path

            # 解析并验证参考音频路径
            if prompt_audio:
                resolved_prompt_path = resolve_audio_path(prompt_audio)
                if not resolved_prompt_path:
                    await self.send_text(f"❌ 参考音频不存在: {prompt_audio}\n提示：可以使用 /list_audio 查看可用音频")
                    return False, "参考音频不存在", True
                prompt_audio = resolved_prompt_path

            if prompt_audio and not prompt_text:
                await self.send_text("❌ 提供了参考音频但未提供参考文本")
                return False, "缺少参考文本", True

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                await self.send_text("❌ 未配置 API Key")
                return False, "未配置API Key", True

            await self.send_text("⏳ 正在上传音频文件...")

            # 1. 上传待克隆音频
            file_id = await upload_audio_file(api_key, audio_path, "voice_clone")
            if not file_id:
                await self.send_text("❌ 上传音频失败")
                return False, "上传失败", True

            logger.info(f"待克隆音频已上传: file_id={file_id}")

            # 2. 上传参考音频（如果有）
            prompt_audio_id = None
            if prompt_audio:
                await self.send_text("⏳ 正在上传参考音频...")
                prompt_audio_id = await upload_audio_file(api_key, prompt_audio, "prompt_audio")
                if not prompt_audio_id:
                    await self.send_text("❌ 上传参考音频失败")
                    return False, "上传参考音频失败", True
                logger.info(f"参考音频已上传: file_id={prompt_audio_id}")

            # 3. 调用克隆API
            await self.send_text("⏳ 正在克隆音色...")

            test_text = self.get_config("voice_clone.test_text", "你好，这是音色克隆测试。")
            model = self.get_config("minimax.model", "speech-2.6-hd")
            need_noise_reduction = self.get_config("voice_clone.need_noise_reduction", False)
            need_volume_normalization = self.get_config("voice_clone.need_volume_normalization", False)

            success, message, demo_audio = await clone_voice_api(
                api_key=api_key,
                file_id=file_id,
                voice_id=voice_id,
                test_text=test_text,
                model=model,
                prompt_audio_id=prompt_audio_id,
                prompt_text=prompt_text,
                need_noise_reduction=need_noise_reduction,
                need_volume_normalization=need_volume_normalization
            )

            if not success:
                await self.send_text(f"❌ {message}")
                return False, message, True

            # 4. 保存音色信息
            voices[voice_id] = {
                "voice_id": voice_id,
                "audio_path": audio_path,
                "prompt_audio": prompt_audio if prompt_audio else None,
                "prompt_text": prompt_text if prompt_text else None,
                "created_at": datetime.now().isoformat(),
                "file_id": file_id,
                "prompt_audio_id": prompt_audio_id
            }

            if save_cloned_voices(voices):
                result_msg = f"✅ 音色克隆成功！\n\n音色ID: {voice_id}\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                if demo_audio:
                    result_msg += f"\n\n试听音频URL: {demo_audio}"
                    # 如果是URL，可以尝试发送
                    if demo_audio.startswith("http"):
                        try:
                            await self.send_custom(message_type="voiceurl", content=demo_audio)
                        except Exception as e:
                            logger.error(f"发送试听音频失败: {e}")

                await self.send_text(result_msg)
                return True, "克隆成功", True
            else:
                await self.send_text("⚠️ 克隆成功但保存失败")
                return False, "保存失败", True

        except Exception as e:
            logger.error(f"克隆音色出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class ListVoicesCommand(BaseCommand):
    """列出已克隆的音色"""

    command_name = "list_voices"
    command_description = "列出所有已克隆的音色"
    command_pattern = r"^/list_voices$"
    command_help = "用法：/list_voices"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            voices = load_cloned_voices()

            if not voices:
                await self.send_text("📝 还没有克隆任何音色")
                return True, "无音色", True

            msg = f"🎤 已克隆的音色（共 {len(voices)} 个）：\n\n"

            for voice_id, info in voices.items():
                created_at = info.get("created_at", "未知")
                if "T" in created_at:
                    # 格式化 ISO 时间
                    try:
                        dt = datetime.fromisoformat(created_at)
                        created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass

                msg += f"🔹 {voice_id}\n"
                msg += f"   创建时间: {created_at}\n"

                audio_path = info.get("audio_path", "")
                if audio_path:
                    msg += f"   源音频: {os.path.basename(audio_path)}\n"

                if info.get("prompt_audio"):
                    msg += f"   使用参考音频: 是\n"

                msg += "\n"

            msg += "💡 使用 /test_voice <音色ID> <文本> 测试音色\n"
            msg += "💡 使用 /delete_voice <音色ID> 删除音色"

            await self.send_text(msg)
            return True, "列表已显示", True

        except Exception as e:
            logger.error(f"列出音色出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class TestVoiceCommand(BaseCommand):
    """测试克隆的音色"""

    command_name = "test_voice"
    command_description = "使用克隆的音色合成测试语音"
    command_pattern = r"^/test_voice\s+(?P<voice_id>\S+)\s+(?P<text>.+)$"
    command_help = """用法：/test_voice <音色ID> <文本>

示例：
  /test_voice my_voice_001 你好，这是测试
  /test_voice MyVoice002 今天天气真好"""
    command_examples = [
        "/test_voice my_voice_001 你好世界",
        "/test_voice MyVoice002 测试音色效果"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            voice_id = self.matched_groups.get("voice_id", "").strip()
            text = self.matched_groups.get("text", "").strip()

            if not voice_id or not text:
                await self.send_text("❌ 缺少参数\n" + self.command_help)
                return False, "缺少参数", True

            # 检查音色是否存在
            voices = load_cloned_voices()
            if voice_id not in voices:
                await self.send_text(f"❌ 音色 '{voice_id}' 不存在\n\n使用 /list_voices 查看所有音色")
                return False, "音色不存在", True

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                await self.send_text("❌ 未配置 API Key")
                return False, "未配置API Key", True

            await self.send_text(f"⏳ 正在使用音色 '{voice_id}' 合成语音...")

            # 使用现有的 TTS 函数
            task = call_minimax_api_sync(
                self.get_config,
                self.get_config("minimax.base_url", "https://api.minimaxi.com/v1/t2a_v2"),
                api_key,
                text,
                voice_id,
                self.get_config("minimax.timeout", 30)
            )
            audio_path = await task

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=audio_path)
                logger.info(f"音色测试成功: {voice_id}")
                return True, "测试成功", True
            else:
                await self.send_text("❌ 合成失败")
                return False, "合成失败", True

        except Exception as e:
            logger.error(f"测试音色出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class ListAudioCommand(BaseCommand):
    """列出 voice_audios 目录下的音频文件"""

    command_name = "list_audio"
    command_description = "列出所有可用的音频文件"
    command_pattern = r"^/list_audio$"
    command_help = "用法：/list_audio"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            audio_files = list_audio_files()

            total_count = len(audio_files["main"]) + len(audio_files["prompts"]) + len(audio_files["root"])

            if total_count == 0:
                msg = f"📂 voice_audios 目录为空\n\n"
                msg += f"音频目录：{VOICE_AUDIOS_DIR}\n\n"
                msg += "💡 将音频文件放到以下目录：\n"
                msg += "  • main/ - 主音频（10秒-5分钟）\n"
                msg += "  • prompts/ - 参考音频（<8秒）"
                await self.send_text(msg)
                return True, "目录为空", True

            msg = f"🎵 可用音频文件（共 {total_count} 个）\n\n"

            # Main 目录
            if audio_files["main"]:
                msg += f"📁 main/ ({len(audio_files['main'])} 个)\n"
                for audio in sorted(audio_files["main"], key=lambda x: x["name"]):
                    msg += f"  • {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            # Prompts 目录
            if audio_files["prompts"]:
                msg += f"📁 prompts/ ({len(audio_files['prompts'])} 个)\n"
                for audio in sorted(audio_files["prompts"], key=lambda x: x["name"]):
                    msg += f"  • {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            # 根目录
            if audio_files["root"]:
                msg += f"📁 根目录 ({len(audio_files['root'])} 个)\n"
                for audio in sorted(audio_files["root"], key=lambda x: x["name"]):
                    msg += f"  • {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            msg += "💡 使用音频克隆：\n"
            msg += "  /clone_voice <文件名> <音色ID>\n"
            msg += "  /clone_voice_batch <文件1> <文件2> ..."

            await self.send_text(msg)
            return True, "列表已显示", True

        except Exception as e:
            logger.error(f"列出音频文件出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class CloneVoiceBatchCommand(BaseCommand):
    """批量克隆音色"""

    command_name = "clone_voice_batch"
    command_description = "批量克隆多个音频文件"
    command_pattern = r"^/clone_voice_batch\s+(.+)$"
    command_help = """用法：/clone_voice_batch <音频1> <音频2> [音频3] ...

示例：
  /clone_voice_batch voice1.mp3 voice2.mp3 voice3.mp3

说明：
  - 每个音频会创建一个独立的音色
  - 音色ID自动生成为：文件名_cloned
  - 支持文件名或相对路径"""
    command_examples = [
        "/clone_voice_batch voice1.mp3 voice2.mp3",
        "/clone_voice_batch main/v1.mp3 main/v2.mp3 main/v3.mp3"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            # 解析音频文件列表
            audio_files_str = self.matched_groups.get("__match__", "").strip()
            if not audio_files_str:
                audio_files_str = self.message.raw_message.replace("/clone_voice_batch", "").strip()

            # 分割文件名（支持空格和引号）
            audio_files = []
            current = ""
            in_quotes = False

            for char in audio_files_str:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ' ' and not in_quotes:
                    if current:
                        audio_files.append(current)
                        current = ""
                else:
                    current += char

            if current:
                audio_files.append(current)

            if not audio_files:
                await self.send_text("❌ 请指定至少一个音频文件\n\n" + self.command_help)
                return False, "缺少参数", True

            await self.send_text(f"🔄 开始批量克隆 {len(audio_files)} 个音频...")

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                await self.send_text("❌ 未配置 API Key")
                return False, "未配置API Key", True

            test_text = self.get_config("voice_clone.test_text", "你好，这是音色克隆测试。")
            model = self.get_config("minimax.model", "speech-2.6-hd")
            need_noise_reduction = self.get_config("voice_clone.need_noise_reduction", False)
            need_volume_normalization = self.get_config("voice_clone.need_volume_normalization", False)

            voices = load_cloned_voices()
            success_count = 0
            failed_count = 0
            results = []

            for idx, audio_file in enumerate(audio_files, 1):
                try:
                    # 解析路径
                    resolved_path = resolve_audio_path(audio_file)
                    if not resolved_path:
                        results.append(f"❌ [{idx}/{len(audio_files)}] {audio_file} - 文件不存在")
                        failed_count += 1
                        continue

                    # 生成音色ID
                    base_name = os.path.splitext(os.path.basename(audio_file))[0]
                    # 清理文件名作为voice_id
                    voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', base_name) + "_cloned"

                    # 确保voice_id符合规范
                    if not voice_id[0].isalpha():
                        voice_id = "voice_" + voice_id

                    # 检查是否已存在
                    counter = 1
                    original_voice_id = voice_id
                    while voice_id in voices:
                        voice_id = f"{original_voice_id}_{counter}"
                        counter += 1

                    await self.send_text(f"⏳ [{idx}/{len(audio_files)}] 克隆 {audio_file} -> {voice_id}")

                    # 上传音频
                    file_id = await upload_audio_file(api_key, resolved_path, "voice_clone")
                    if not file_id:
                        results.append(f"❌ [{idx}/{len(audio_files)}] {audio_file} - 上传失败")
                        failed_count += 1
                        continue

                    # 调用克隆API
                    success, message, demo_audio = await clone_voice_api(
                        api_key=api_key,
                        file_id=file_id,
                        voice_id=voice_id,
                        test_text=test_text,
                        model=model,
                        need_noise_reduction=need_noise_reduction,
                        need_volume_normalization=need_volume_normalization
                    )

                    if not success:
                        results.append(f"❌ [{idx}/{len(audio_files)}] {audio_file} - {message}")
                        failed_count += 1
                        continue

                    # 保存音色信息
                    voices[voice_id] = {
                        "voice_id": voice_id,
                        "audio_path": resolved_path,
                        "prompt_audio": None,
                        "prompt_text": None,
                        "created_at": datetime.now().isoformat(),
                        "file_id": file_id,
                        "prompt_audio_id": None
                    }

                    results.append(f"✅ [{idx}/{len(audio_files)}] {audio_file} -> {voice_id}")
                    success_count += 1

                except Exception as e:
                    logger.error(f"克隆 {audio_file} 失败: {e}")
                    results.append(f"❌ [{idx}/{len(audio_files)}] {audio_file} - {str(e)}")
                    failed_count += 1

            # 保存所有成功的音色
            if success_count > 0:
                save_cloned_voices(voices)

            # 生成结果报告
            result_msg = f"\n\n📊 批量克隆完成\n\n"
            result_msg += f"✅ 成功：{success_count}\n"
            result_msg += f"❌ 失败：{failed_count}\n"
            result_msg += f"📝 总计：{len(audio_files)}\n\n"
            result_msg += "详细结果：\n" + "\n".join(results)

            await self.send_text(result_msg)

            return True if success_count > 0 else False, f"成功{success_count}个", True

        except Exception as e:
            logger.error(f"批量克隆出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


class DeleteVoiceCommand(BaseCommand):
    """删除克隆的音色"""

    command_name = "delete_voice"
    command_description = "删除已克隆的音色"
    command_pattern = r"^/delete_voice\s+(?P<voice_id>\S+)$"
    command_help = """用法：/delete_voice <音色ID>

示例：
  /delete_voice my_voice_001
  /delete_voice MyVoice002"""
    command_examples = [
        "/delete_voice my_voice_001",
        "/delete_voice MyVoice002"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            voice_id = self.matched_groups.get("voice_id", "").strip()

            if not voice_id:
                await self.send_text("❌ 缺少音色ID\n" + self.command_help)
                return False, "缺少参数", True

            voices = load_cloned_voices()

            if voice_id not in voices:
                await self.send_text(f"❌ 音色 '{voice_id}' 不存在\n\n使用 /list_voices 查看所有音色")
                return False, "音色不存在", True

            # 删除音色
            del voices[voice_id]

            if save_cloned_voices(voices):
                await self.send_text(f"✅ 音色 '{voice_id}' 已删除")
                return True, "删除成功", True
            else:
                await self.send_text("❌ 删除失败")
                return False, "保存失败", True

        except Exception as e:
            logger.error(f"删除音色出错: {e}")
            await self.send_text(f"❌ 出错: {e}")
            return False, str(e), True


@register_plugin
class MiniMaxTTSPlugin(BasePlugin):
    """MiniMax TTS 插件"""

    plugin_name = "minimax_tts_plugin"
    plugin_description = "MiniMax 文本转语音插件"
    plugin_version = "1.0.0"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp"]

    config_section_descriptions = {
        "plugin": "插件配置",
        "components": "组件控制",
        "minimax": "API配置",
        "voice_clone": "音色克隆配置"
    }

    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件")
        },
        "components": {
            "command_enabled": ConfigField(type=bool, default=True, description="启用手动命令触发TTS (/minimax <文本>)"),
            "tool_enabled": ConfigField(type=bool, default=True, description="启用LLM工具调用 (让AI自动判断何时使用语音回复)"),
            "handler_enabled": ConfigField(type=bool, default=True, description="启用事件处理器 (执行实际的语音合成)"),
            "voice_clone_enabled": ConfigField(type=bool, default=True, description="启用音色克隆命令 (/clone_voice等)"),
        },
        "minimax": {
            "base_url": ConfigField(type=str, default="https://api.minimaxi.com/v1/t2a_v2", description="MiniMax TTS API地址 (通常无需修改)"),
            "api_key": ConfigField(type=str, default="", description="API密钥 (在 https://platform.minimaxi.com 获取)"),
            "model": ConfigField(type=str, default="speech-2.6-hd", description="TTS模型 | 可选: speech-2.6-hd(高清), speech-2.6-turbo(快速)"),
            "voice_id": ConfigField(type=str, default="", description="默认音色ID | 支持系统音色/克隆音色/AI生成音色"),
            "timeout": ConfigField(type=int, default=30, description="API请求超时时间(秒) | 长文本可适当增加"),
            "language_boost": ConfigField(type=str, default="auto", description="语言增强 | 可选: auto(自动), Chinese(中文), English(英语), Japanese(日语)等"),
            "output_format": ConfigField(type=str, default="hex", description="输出格式 | hex: 直接返回音频数据, url: 返回24小时有效URL"),
            "emotion": ConfigField(type=str, default="", description="语音情绪 | 可选: happy(快乐), sad(悲伤), angry(愤怒), calm(平静), fluent(流畅) | 留空自动"),
            "text_normalization": ConfigField(type=bool, default=False, description="文本规范化 | 开启后优化数字、日期等朗读效果 (略增延迟)"),
            "latex_read": ConfigField(type=bool, default=False, description="LaTeX公式朗读 | 开启后支持朗读数学公式 (需用$包裹公式)"),
            "trailing_pause": ConfigField(type=float, default=1.0, description="尾部停顿(秒) | 防止最后一个字被截断 | 范围: 0-99.99, 推荐: 0.5-2.0"),
            "speed": ConfigField(type=float, default=1.0, description="语速 | 范围: 0.5(慢)-2.0(快), 1.0为正常速度"),
            "vol": ConfigField(type=float, default=1.0, description="音量 | 范围: 0.1(小)-10.0(大), 1.0为正常音量"),
            "pitch": ConfigField(type=int, default=0, description="音调 | 范围: -12(低沉)~12(尖锐), 0为原始音调"),
            "voice_modify_pitch": ConfigField(type=int, default=0, description="[效果器]音高微调 | 范围: -100(深沉)~100(明亮), 比pitch更细腻"),
            "voice_modify_intensity": ConfigField(type=int, default=0, description="[效果器]声音强度 | 范围: -100(柔和)~100(刚劲)"),
            "voice_modify_timbre": ConfigField(type=int, default=0, description="[效果器]音色调整 | 范围: -100(浑厚)~100(清脆)"),
            "sound_effects": ConfigField(type=str, default="", description="音效 | 可选: spacious_echo(空旷回声), auditorium_echo(礼堂回声), lofi_telephone(电话音), robotic(机器人)"),
            "sample_rate": ConfigField(type=int, default=32000, description="采样率(Hz) | 可选: 8000/16000/32000/44100, 越高音质越好 | 推荐: 44100"),
            "bitrate": ConfigField(type=int, default=128000, description="比特率(bps) | 可选: 32000/64000/128000/256000, 越高音质越好 | 推荐: 256000"),
            "audio_format": ConfigField(type=str, default="mp3", description="音频格式 | 可选: mp3(兼容性好), wav(无损), flac(无损压缩), pcm(原始)"),
            "channel": ConfigField(type=int, default=1, description="声道数 | 1: 单声道(推荐TTS), 2: 立体声")
        },
        "voice_clone": {
            "test_text": ConfigField(type=str, default="你好，这是音色克隆测试。", description="克隆音色时的试听文本 (会自动生成试听音频)"),
            "need_noise_reduction": ConfigField(type=bool, default=False, description="克隆时启用降噪 | 源音频有背景噪音时建议开启"),
            "need_volume_normalization": ConfigField(type=bool, default=False, description="克隆时启用音量归一化 | 源音频音量不稳定时建议开启")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []
        command_enabled = self.get_config("components.command_enabled", True)
        tool_enabled = self.get_config("components.tool_enabled", True)
        handler_enabled = self.get_config("components.handler_enabled", True)
        voice_clone_enabled = self.get_config("components.voice_clone_enabled", True)

        if command_enabled:
            components.append((MiniMaxTTSCommand.get_command_info(), MiniMaxTTSCommand))
        if tool_enabled:
            components.append((MiniMaxTTSTool.get_tool_info(), MiniMaxTTSTool))
        if handler_enabled:
            components.append((MiniMaxTTSEventHandler.get_handler_info(), MiniMaxTTSEventHandler))

        # 音色克隆命令
        if voice_clone_enabled:
            components.append((CloneVoiceCommand.get_command_info(), CloneVoiceCommand))
            components.append((ListVoicesCommand.get_command_info(), ListVoicesCommand))
            components.append((TestVoiceCommand.get_command_info(), TestVoiceCommand))
            components.append((DeleteVoiceCommand.get_command_info(), DeleteVoiceCommand))
            components.append((ListAudioCommand.get_command_info(), ListAudioCommand))
            components.append((CloneVoiceBatchCommand.get_command_info(), CloneVoiceBatchCommand))

        return components
