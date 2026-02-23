"""音色克隆管理器：上传、克隆、删除、过期检测"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from src.common.logger import get_logger

from .audio_utils import PLUGIN_DIR
from .config_schema import MAX_UPLOAD_SIZE, VALID_AUDIO_FORMATS

logger = get_logger("minimax_tts_plugin")

VOICES_DATA_FILE = os.path.join(PLUGIN_DIR, "cloned_voices.json")


class VoiceCloneManager:
    """音色克隆管理器，asyncio.Lock 保护所有读写操作"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._voices: Optional[Dict[str, Dict[str, Any]]] = None

    # ── 持久化 ──────────────────────────────────────────

    async def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._voices is not None:
            return self._voices

        loop = asyncio.get_running_loop()
        self._voices = await loop.run_in_executor(None, self._load_sync)
        return self._voices

    @staticmethod
    def _load_sync() -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(VOICES_DATA_FILE):
            return {}
        try:
            with open(VOICES_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载音色数据失败: {e}")
            return {}

    async def _save(self) -> bool:
        if self._voices is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._save_sync, self._voices)

    @staticmethod
    def _save_sync(voices: Dict[str, Dict[str, Any]]) -> bool:
        try:
            with open(VOICES_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(voices, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存音色数据失败: {e}")
            return False

    # ── 公开接口 ────────────────────────────────────────

    async def get_voices(self) -> Dict[str, Dict[str, Any]]:
        async with self._lock:
            return dict(await self._load())

    async def voice_exists(self, voice_id: str) -> bool:
        async with self._lock:
            voices = await self._load()
            return voice_id in voices

    async def add_voice(self, voice_id: str, info: Dict[str, Any]) -> bool:
        async with self._lock:
            voices = await self._load()
            voices[voice_id] = info
            return await self._save()

    async def remove_voice(self, voice_id: str) -> bool:
        async with self._lock:
            voices = await self._load()
            if voice_id not in voices:
                return False
            del voices[voice_id]
            return await self._save()

    async def touch_voice(self, voice_id: str) -> None:
        """更新 last_used_at 字段"""
        async with self._lock:
            voices = await self._load()
            if voice_id in voices:
                voices[voice_id]["last_used_at"] = datetime.now().isoformat()
                await self._save()

    async def check_expired_voices(self, warn_days: int = 6) -> List[str]:
        """检测即将过期的音色（MiniMax 克隆音色 7 天有效期）"""
        async with self._lock:
            voices = await self._load()
            expired = []
            cutoff = datetime.now() - timedelta(days=warn_days)

            for voice_id, info in voices.items():
                created_at_str = info.get("created_at", "")
                if not created_at_str:
                    continue
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at < cutoff:
                        expired.append(voice_id)
                except (ValueError, TypeError):
                    pass

            return expired

    # ── 上传音频 ────────────────────────────────────────

    async def upload_audio(
        self, api_key: str, base_url: str, file_path: str, purpose: str
    ) -> Optional[int]:
        """上传音频文件到 MiniMax（上传前验证文件大小和格式）。

        Args:
            api_key: API 密钥
            base_url: API 基础地址
            file_path: 音频文件路径
            purpose: 上传目的 (voice_clone / prompt_audio)

        Returns:
            file_id 或 None
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None

        # 验证格式
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if ext not in VALID_AUDIO_FORMATS:
            logger.error(f"不支持的音频格式: {ext}, 支持: {', '.join(VALID_AUDIO_FORMATS)}")
            return None

        # 验证大小
        file_size = os.path.getsize(file_path)
        if file_size > MAX_UPLOAD_SIZE:
            logger.error(f"文件过大: {file_size} 字节 (最大 {MAX_UPLOAD_SIZE} 字节)")
            return None

        try:
            url = f"{base_url.rstrip('/')}/v1/files/upload"

            loop = asyncio.get_running_loop()
            file_data = await loop.run_in_executor(None, self._read_file_sync, file_path)

            form = aiohttp.FormData()
            form.add_field("purpose", purpose)
            form.add_field("file", file_data, filename=os.path.basename(file_path))

            headers = {"Authorization": f"Bearer {api_key}"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=form, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"上传文件失败 (HTTP {response.status})")
                        return None

                    resp_json = await response.json()
                    file_info = resp_json.get("file", {})
                    file_id = file_info.get("file_id")

                    if file_id:
                        logger.info(f"文件上传成功: {file_path} -> file_id={file_id}")
                        return file_id
                    else:
                        logger.error("API 未返回 file_id")
                        return None

        except Exception as e:
            logger.error(f"上传文件出错: {e}")
            return None

    @staticmethod
    def _read_file_sync(path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    # ── 克隆音色 ────────────────────────────────────────

    async def clone_voice(
        self,
        api_key: str,
        base_url: str,
        file_id: int,
        voice_id: str,
        test_text: str = "",
        model: str = "speech-2.8-hd",
        prompt_audio_id: Optional[int] = None,
        prompt_text: Optional[str] = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        accuracy: float = 0.7,
    ) -> Tuple[bool, str, Optional[str]]:
        """调用音色克隆 API。

        Returns:
            (成功标志, 消息, 试听音频URL)
        """
        try:
            url = f"{base_url.rstrip('/')}/v1/voice_clone"

            payload: Dict[str, Any] = {
                "file_id": file_id,
                "voice_id": voice_id,
                "need_noise_reduction": need_noise_reduction,
                "need_volume_normalization": need_volume_normalization,
                "accuracy": accuracy,
            }

            if test_text:
                payload["text"] = test_text
                payload["model"] = model

            if prompt_audio_id and prompt_text:
                payload["clone_prompt"] = {
                    "prompt_audio": prompt_audio_id,
                    "prompt_text": prompt_text,
                }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"克隆 API 失败 (HTTP {response.status})")
                        return False, f"API 调用失败: {response.status}", None

                    resp_json = await response.json()

            base_resp = resp_json.get("base_resp", {})
            status_code = base_resp.get("status_code", -1)
            status_msg = base_resp.get("status_msg", "未知错误")

            if status_code != 0:
                if status_code == 1026 or "sensitive" in status_msg.lower():
                    error_msg = (
                        "音频内容未通过安全审核\n\n可能原因：\n"
                        "- 音频包含敏感内容\n"
                        "- 音频质量不佳导致误判\n"
                        "- 背景噪音被误识别\n\n"
                        "建议：\n"
                        "- 使用清晰的朗读音频\n"
                        "- 避免包含敏感词汇\n"
                        "- 启用降噪（config.toml 中设置 need_noise_reduction=true）\n"
                        "- 更换其他音频重试"
                    )
                    logger.error(f"内容安全审核失败: {status_msg} (代码: {status_code})")
                    return False, error_msg, None

                logger.error(f"克隆失败: {status_msg} (代码: {status_code})")
                return False, f"克隆失败: {status_msg} (错误代码: {status_code})", None

            # 检查内容安全
            input_sensitive = resp_json.get("input_sensitive", {})
            if isinstance(input_sensitive, dict):
                sensitive_type = input_sensitive.get("type", 0)
            else:
                sensitive_type = 0 if not input_sensitive else 1

            if sensitive_type != 0:
                return False, f"输入音频风控不通过，类型: {sensitive_type}", None

            demo_audio = resp_json.get("demo_audio", "")
            return True, "克隆成功", demo_audio if demo_audio else None

        except Exception as e:
            logger.error(f"克隆 API 调用出错: {e}")
            return False, f"出错: {e}", None

    # ── 删除音色（服务端 + 本地）────────────────────────

    async def delete_voice_remote(
        self, api_key: str, base_url: str, voice_id: str
    ) -> bool:
        """删除服务端的克隆音色"""
        try:
            url = f"{base_url.rstrip('/')}/v1/voice_clone/delete"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {"voice_id": voice_id}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        base_resp = resp_json.get("base_resp", {})
                        if base_resp.get("status_code", -1) == 0:
                            logger.info(f"服务端音色 '{voice_id}' 已删除")
                            return True
                    logger.warning(f"服务端删除音色 '{voice_id}' 失败 (HTTP {response.status})")
                    return False
        except Exception as e:
            logger.warning(f"服务端删除音色出错: {e}")
            return False

    async def delete_voice_full(
        self, api_key: str, base_url: str, voice_id: str
    ) -> bool:
        """同时删除本地 + 服务端音色"""
        # 尝试远程删除（不阻塞本地删除）
        await self.delete_voice_remote(api_key, base_url, voice_id)
        return await self.remove_voice(voice_id)
