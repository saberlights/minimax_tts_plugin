"""克隆管理命令集：CloneVoice、ListVoices、TestVoice、DeleteVoice、ListAudio、CloneVoiceBatch"""

import os
import re
from datetime import datetime
from typing import Tuple

from src.common.logger import get_logger
from src.plugin_system.base.base_command import BaseCommand

from ..core.api_client import MiniMaxAPIClient
from ..core.audio_utils import format_file_size, list_audio_files, resolve_audio_path, VOICE_AUDIOS_DIR
from ..core.voice_clone import VoiceCloneManager

logger = get_logger("minimax_tts_plugin")

# 共享的管理器实例（由 plugin.py 注入）
_voice_clone_manager: VoiceCloneManager | None = None


def set_voice_clone_manager(mgr: VoiceCloneManager) -> None:
    global _voice_clone_manager
    _voice_clone_manager = mgr


def _get_manager() -> VoiceCloneManager:
    if _voice_clone_manager is None:
        raise RuntimeError("VoiceCloneManager 未初始化")
    return _voice_clone_manager


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
  - 音频文件：10秒-5分钟，mp3/m4a/wav格式，<=20MB
  - 音色ID：8-256字符，首字符必须为字母
  - 参考音频（可选）：<8秒，用于增强克隆效果
  - 参考文本（可选）：参考音频对应的文本"""
    command_examples = [
        "/clone_voice /tmp/voice.mp3 MyVoice001",
        "/clone_voice /tmp/voice.wav MyVoice002 /tmp/prompt.mp3 你好世界",
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            mgr = _get_manager()
            audio_path = self.matched_groups.get("audio_path", "").strip()
            voice_id = self.matched_groups.get("voice_id", "").strip()
            prompt_audio = (self.matched_groups.get("prompt_audio", "") or "").strip()
            prompt_text = (self.matched_groups.get("prompt_text", "") or "").strip()

            if not audio_path or not voice_id:
                await self.send_text("缺少必需参数\n" + self.command_help)
                return False, "缺少参数", True

            if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{7,255}$", voice_id):
                await self.send_text("音色ID格式错误\n要求：8-256字符，首字符为字母，允许字母、数字、_、-")
                return False, "voice_id格式错误", True

            if await mgr.voice_exists(voice_id):
                await self.send_text(f"音色ID '{voice_id}' 已存在，请使用其他ID或先删除现有音色")
                return False, "voice_id已存在", True

            resolved_audio_path = resolve_audio_path(audio_path)
            if not resolved_audio_path:
                await self.send_text(f"音频文件不存在: {audio_path}\n提示：可以使用 /list_audio 查看可用音频")
                return False, "文件不存在", True
            audio_path = resolved_audio_path

            if prompt_audio:
                resolved_prompt_path = resolve_audio_path(prompt_audio)
                if not resolved_prompt_path:
                    await self.send_text(f"参考音频不存在: {prompt_audio}\n提示：可以使用 /list_audio 查看可用音频")
                    return False, "参考音频不存在", True
                prompt_audio = resolved_prompt_path

            if prompt_audio and not prompt_text:
                await self.send_text("提供了参考音频但未提供参考文本")
                return False, "缺少参考文本", True

            api_key = self.get_config("minimax.api_key", "")
            base_url = self.get_config("minimax.base_url", "https://api.minimaxi.com")
            if not api_key:
                await self.send_text("未配置 API Key")
                return False, "未配置API Key", True

            await self.send_text("正在上传音频文件...")

            file_id = await mgr.upload_audio(api_key, base_url, audio_path, "voice_clone")
            if not file_id:
                await self.send_text("上传音频失败")
                return False, "上传失败", True

            logger.info(f"待克隆音频已上传: file_id={file_id}")

            prompt_audio_id = None
            if prompt_audio:
                await self.send_text("正在上传参考音频...")
                prompt_audio_id = await mgr.upload_audio(api_key, base_url, prompt_audio, "prompt_audio")
                if not prompt_audio_id:
                    await self.send_text("上传参考音频失败")
                    return False, "上传参考音频失败", True
                logger.info(f"参考音频已上传: file_id={prompt_audio_id}")

            await self.send_text("正在克隆音色...")

            test_text = self.get_config("voice_clone.test_text", "你好，这是音色克隆测试。")
            model = self.get_config("minimax.model", "speech-2.8-hd")
            need_noise_reduction = self.get_config("voice_clone.need_noise_reduction", False)
            need_volume_normalization = self.get_config("voice_clone.need_volume_normalization", False)
            accuracy = self.get_config("voice_clone.accuracy", 0.7)

            success, message, demo_audio = await mgr.clone_voice(
                api_key=api_key,
                base_url=base_url,
                file_id=file_id,
                voice_id=voice_id,
                test_text=test_text,
                model=model,
                prompt_audio_id=prompt_audio_id,
                prompt_text=prompt_text,
                need_noise_reduction=need_noise_reduction,
                need_volume_normalization=need_volume_normalization,
                accuracy=accuracy,
            )

            if not success:
                await self.send_text(message)
                return False, message, True

            voice_info = {
                "voice_id": voice_id,
                "audio_path": audio_path,
                "prompt_audio": prompt_audio if prompt_audio else None,
                "prompt_text": prompt_text if prompt_text else None,
                "created_at": datetime.now().isoformat(),
                "last_used_at": datetime.now().isoformat(),
                "file_id": file_id,
                "prompt_audio_id": prompt_audio_id,
            }

            if await mgr.add_voice(voice_id, voice_info):
                result_msg = f"音色克隆成功！\n\n音色ID: {voice_id}\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                if demo_audio:
                    result_msg += f"\n\n试听音频URL: {demo_audio}"
                    if demo_audio.startswith("http"):
                        try:
                            await self.send_custom(message_type="voiceurl", content=demo_audio)
                        except Exception as e:
                            logger.error(f"发送试听音频失败: {e}")
                await self.send_text(result_msg)
                return True, "克隆成功", True
            else:
                await self.send_text("克隆成功但保存本地记录失败")
                return False, "保存失败", True

        except Exception as e:
            logger.error(f"克隆音色出错: {e}")
            await self.send_text(f"出错: {e}")
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
            mgr = _get_manager()
            voices = await mgr.get_voices()

            if not voices:
                await self.send_text("还没有克隆任何音色")
                return True, "无音色", True

            msg = f"已克隆的音色（共 {len(voices)} 个）：\n\n"

            for voice_id, info in voices.items():
                created_at = info.get("created_at", "未知")
                if "T" in created_at:
                    try:
                        dt = datetime.fromisoformat(created_at)
                        created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        pass

                msg += f"- {voice_id}\n"
                msg += f"   创建时间: {created_at}\n"

                last_used = info.get("last_used_at")
                if last_used:
                    try:
                        dt = datetime.fromisoformat(last_used)
                        msg += f"   最后使用: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    except (ValueError, TypeError):
                        pass

                audio_path = info.get("audio_path", "")
                if audio_path:
                    msg += f"   源音频: {os.path.basename(audio_path)}\n"

                if info.get("prompt_audio"):
                    msg += "   使用参考音频: 是\n"

                msg += "\n"

            # 检查尚未激活的音色
            unactivated = await mgr.check_unactivated_voices()
            if unactivated:
                msg += f"[注意] 以下音色克隆后尚未使用，7天内未调用将被删除：{', '.join(unactivated)}\n\n"

            msg += "使用 /test_voice <音色ID> <文本> 测试音色\n"
            msg += "使用 /delete_voice <音色ID> 删除音色"

            await self.send_text(msg)
            return True, "列表已显示", True

        except Exception as e:
            logger.error(f"列出音色出错: {e}")
            await self.send_text(f"出错: {e}")
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
        "/test_voice MyVoice002 测试音色效果",
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            mgr = _get_manager()
            voice_id = self.matched_groups.get("voice_id", "").strip()
            text = self.matched_groups.get("text", "").strip()

            if not voice_id or not text:
                await self.send_text("缺少参数\n" + self.command_help)
                return False, "缺少参数", True

            if not await mgr.voice_exists(voice_id):
                await self.send_text(f"音色 '{voice_id}' 不存在\n\n使用 /list_voices 查看所有音色")
                return False, "音色不存在", True

            api_key = self.get_config("minimax.api_key", "")
            if not api_key:
                await self.send_text("未配置 API Key")
                return False, "未配置API Key", True

            await self.send_text(f"正在使用音色 '{voice_id}' 合成语音...")

            client = await MiniMaxAPIClient.get_instance()
            audio_path = await client.synthesize(
                self.get_config, text, voice_id
            )

            if audio_path:
                # 更新使用时间
                await mgr.touch_voice(voice_id)
                await self.send_custom(message_type="voiceurl", content=audio_path)
                logger.info(f"音色测试成功: {voice_id}")
                return True, "测试成功", True
            else:
                await self.send_text("合成失败")
                return False, "合成失败", True

        except Exception as e:
            logger.error(f"测试音色出错: {e}")
            await self.send_text(f"出错: {e}")
            return False, str(e), True


class DeleteVoiceCommand(BaseCommand):
    """删除克隆的音色（本地 + 服务端）"""

    command_name = "delete_voice"
    command_description = "删除已克隆的音色"
    command_pattern = r"^/delete_voice\s+(?P<voice_id>\S+)$"
    command_help = """用法：/delete_voice <音色ID>

示例：
  /delete_voice my_voice_001
  /delete_voice MyVoice002"""
    command_examples = [
        "/delete_voice my_voice_001",
        "/delete_voice MyVoice002",
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            mgr = _get_manager()
            voice_id = self.matched_groups.get("voice_id", "").strip()

            if not voice_id:
                await self.send_text("缺少音色ID\n" + self.command_help)
                return False, "缺少参数", True

            if not await mgr.voice_exists(voice_id):
                await self.send_text(f"音色 '{voice_id}' 不存在\n\n使用 /list_voices 查看所有音色")
                return False, "音色不存在", True

            api_key = self.get_config("minimax.api_key", "")
            base_url = self.get_config("minimax.base_url", "https://api.minimaxi.com")

            # 同时删除本地 + 服务端
            if await mgr.delete_voice_full(api_key, base_url, voice_id):
                await self.send_text(f"音色 '{voice_id}' 已删除（本地 + 服务端）")
                return True, "删除成功", True
            else:
                await self.send_text("删除失败")
                return False, "删除失败", True

        except Exception as e:
            logger.error(f"删除音色出错: {e}")
            await self.send_text(f"出错: {e}")
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
            audio_files = await list_audio_files()

            total_count = len(audio_files["main"]) + len(audio_files["prompts"]) + len(audio_files["root"])

            if total_count == 0:
                msg = f"voice_audios 目录为空\n\n"
                msg += f"音频目录：{VOICE_AUDIOS_DIR}\n\n"
                msg += "将音频文件放到以下目录：\n"
                msg += "  main/ - 主音频（10秒-5分钟）\n"
                msg += "  prompts/ - 参考音频（<8秒）"
                await self.send_text(msg)
                return True, "目录为空", True

            msg = f"可用音频文件（共 {total_count} 个）\n\n"

            if audio_files["main"]:
                msg += f"main/ ({len(audio_files['main'])} 个)\n"
                for audio in sorted(audio_files["main"], key=lambda x: x["name"]):
                    msg += f"  - {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            if audio_files["prompts"]:
                msg += f"prompts/ ({len(audio_files['prompts'])} 个)\n"
                for audio in sorted(audio_files["prompts"], key=lambda x: x["name"]):
                    msg += f"  - {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            if audio_files["root"]:
                msg += f"根目录 ({len(audio_files['root'])} 个)\n"
                for audio in sorted(audio_files["root"], key=lambda x: x["name"]):
                    msg += f"  - {audio['name']} ({format_file_size(audio['size'])})\n"
                msg += "\n"

            msg += "使用音频克隆：\n"
            msg += "  /clone_voice <文件名> <音色ID>\n"
            msg += "  /clone_voice_batch <文件1> <文件2> ..."

            await self.send_text(msg)
            return True, "列表已显示", True

        except Exception as e:
            logger.error(f"列出音频文件出错: {e}")
            await self.send_text(f"出错: {e}")
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
        "/clone_voice_batch main/v1.mp3 main/v2.mp3 main/v3.mp3",
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            mgr = _get_manager()

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
                await self.send_text("请指定至少一个音频文件\n\n" + self.command_help)
                return False, "缺少参数", True

            await self.send_text(f"开始批量克隆 {len(audio_files)} 个音频...")

            api_key = self.get_config("minimax.api_key", "")
            base_url = self.get_config("minimax.base_url", "https://api.minimaxi.com")
            if not api_key:
                await self.send_text("未配置 API Key")
                return False, "未配置API Key", True

            test_text = self.get_config("voice_clone.test_text", "你好，这是音色克隆测试。")
            model = self.get_config("minimax.model", "speech-2.8-hd")
            need_noise_reduction = self.get_config("voice_clone.need_noise_reduction", False)
            need_volume_normalization = self.get_config("voice_clone.need_volume_normalization", False)
            accuracy = self.get_config("voice_clone.accuracy", 0.7)

            voices = await mgr.get_voices()
            success_count = 0
            failed_count = 0
            results = []

            for idx, audio_file in enumerate(audio_files, 1):
                try:
                    resolved_path = resolve_audio_path(audio_file)
                    if not resolved_path:
                        results.append(f"[{idx}/{len(audio_files)}] {audio_file} - 文件不存在")
                        failed_count += 1
                        continue

                    base_name = os.path.splitext(os.path.basename(audio_file))[0]
                    voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', base_name) + "_cloned"

                    if not voice_id[0].isalpha():
                        voice_id = "voice_" + voice_id

                    counter = 1
                    original_voice_id = voice_id
                    while voice_id in voices:
                        voice_id = f"{original_voice_id}_{counter}"
                        counter += 1

                    await self.send_text(f"[{idx}/{len(audio_files)}] 克隆 {audio_file} -> {voice_id}")

                    file_id = await mgr.upload_audio(api_key, base_url, resolved_path, "voice_clone")
                    if not file_id:
                        results.append(f"[{idx}/{len(audio_files)}] {audio_file} - 上传失败")
                        failed_count += 1
                        continue

                    success, message, demo_audio = await mgr.clone_voice(
                        api_key=api_key,
                        base_url=base_url,
                        file_id=file_id,
                        voice_id=voice_id,
                        test_text=test_text,
                        model=model,
                        need_noise_reduction=need_noise_reduction,
                        need_volume_normalization=need_volume_normalization,
                        accuracy=accuracy,
                    )

                    if not success:
                        results.append(f"[{idx}/{len(audio_files)}] {audio_file} - {message}")
                        failed_count += 1
                        continue

                    voice_info = {
                        "voice_id": voice_id,
                        "audio_path": resolved_path,
                        "prompt_audio": None,
                        "prompt_text": None,
                        "created_at": datetime.now().isoformat(),
                        "last_used_at": datetime.now().isoformat(),
                        "file_id": file_id,
                        "prompt_audio_id": None,
                    }

                    await mgr.add_voice(voice_id, voice_info)
                    voices[voice_id] = voice_info

                    results.append(f"[{idx}/{len(audio_files)}] {audio_file} -> {voice_id} (成功)")
                    success_count += 1

                except Exception as e:
                    logger.error(f"克隆 {audio_file} 失败: {e}")
                    results.append(f"[{idx}/{len(audio_files)}] {audio_file} - {str(e)}")
                    failed_count += 1

            result_msg = f"\n\n批量克隆完成\n\n"
            result_msg += f"成功：{success_count}\n"
            result_msg += f"失败：{failed_count}\n"
            result_msg += f"总计：{len(audio_files)}\n\n"
            result_msg += "详细结果：\n" + "\n".join(results)

            await self.send_text(result_msg)
            return success_count > 0, f"成功{success_count}个", True

        except Exception as e:
            logger.error(f"批量克隆出错: {e}")
            await self.send_text(f"出错: {e}")
            return False, str(e), True
