"""MiniMax API 客户端：session 复用、重试、限流、流式合成、异步长文本"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from src.common.logger import get_logger

from .audio_utils import AUDIO_CACHE_DIR
from .config_schema import FATAL_ERROR_CODES, RETRYABLE_ERROR_CODES

logger = get_logger("minimax_tts_plugin")


class RateLimiter:
    """令牌桶速率限制器"""

    def __init__(self, rpm: int = 60):
        self._rpm = max(1, rpm)
        self._interval = 60.0 / self._rpm
        self._last_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last_time + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_time = time.monotonic()


class MiniMaxAPIClient:
    """MiniMax TTS API 客户端（单例模式，复用 aiohttp.ClientSession）"""

    _instance: Optional["MiniMaxAPIClient"] = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter: Optional[RateLimiter] = None

    @classmethod
    async def get_instance(cls) -> "MiniMaxAPIClient":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _ensure_rate_limiter(self, rpm: int) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(rpm)
        return self._rate_limiter

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _build_request_body(
        self,
        get_config: Callable,
        text: str,
        voice_id: str,
        override_emotion: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建 TTS 请求体。

        text_normalization / english_normalization / latex_read 放在请求体顶层
        （修正原来错误地放在 voice_setting 内的问题）。
        """
        processed_text = text

        # 尾部停顿
        trailing_pause = get_config("minimax.trailing_pause", 0.0)
        if trailing_pause > 0:
            pause_duration = max(0.01, min(99.99, trailing_pause))
            processed_text = f"{processed_text}<#{pause_duration:.2f}#>"

        # voice_setting —— 只放音色相关参数
        voice_setting: Dict[str, Any] = {
            "voice_id": voice_id,
            "speed": get_config("minimax.speed", 1.0),
            "vol": get_config("minimax.vol", 1.0),
            "pitch": int(get_config("minimax.pitch", 0)),
        }

        emotion = override_emotion or get_config("minimax.emotion", None)
        if emotion:
            voice_setting["emotion"] = emotion

        body: Dict[str, Any] = {
            "model": get_config("minimax.model", "speech-2.8-hd"),
            "text": processed_text,
            "stream": False,
            "language_boost": get_config("minimax.language_boost", "auto"),
            "output_format": get_config("minimax.output_format", "hex"),
            "voice_setting": voice_setting,
            "audio_setting": {
                "sample_rate": int(get_config("minimax.sample_rate", 32000)),
                "bitrate": int(get_config("minimax.bitrate", 128000)),
                "format": get_config("minimax.audio_format", "mp3"),
                "channel": int(get_config("minimax.channel", 1)),
            },
        }

        # 顶层参数（不放在 voice_setting 内）
        if get_config("minimax.text_normalization", False):
            body["text_normalization"] = True
        if get_config("minimax.english_normalization", False):
            body["english_normalization"] = True
        if get_config("minimax.latex_read", False):
            body["latex_read"] = True

        # voice_modify
        voice_modify: Dict[str, Any] = {}
        modify_pitch = get_config("minimax.voice_modify_pitch", None)
        modify_intensity = get_config("minimax.voice_modify_intensity", None)
        modify_timbre = get_config("minimax.voice_modify_timbre", None)
        sound_effects = get_config("minimax.sound_effects", None)

        if modify_pitch is not None and modify_pitch != 0:
            voice_modify["pitch"] = int(modify_pitch)
        if modify_intensity is not None and modify_intensity != 0:
            voice_modify["intensity"] = int(modify_intensity)
        if modify_timbre is not None and modify_timbre != 0:
            voice_modify["timbre"] = int(modify_timbre)
        if sound_effects:
            voice_modify["sound_effects"] = sound_effects

        if voice_modify:
            body["voice_modify"] = voice_modify

        # 发音词典（#16）
        pronunciation_dict_str = get_config("minimax.pronunciation_dict", "")
        if pronunciation_dict_str:
            try:
                pronunciation_dict = json.loads(pronunciation_dict_str)
                if isinstance(pronunciation_dict, dict):
                    body["pronunciation_dict"] = pronunciation_dict
            except json.JSONDecodeError:
                logger.warning("pronunciation_dict 配置格式错误，已忽略")

        # 音频混合（#17）
        audio_mix_url = get_config("minimax.audio_mix_url", "")
        if audio_mix_url:
            audio_mix_item = {
                "audio_url": audio_mix_url,
                "start_time": int(get_config("minimax.audio_mix_start_time", 0)),
                "end_time": int(get_config("minimax.audio_mix_end_time", -1)),
                "volume": float(get_config("minimax.audio_mix_volume", 0.3)),
                "repeat": bool(get_config("minimax.audio_mix_repeat", True)),
            }
            body.setdefault("audio_setting", {})["audio_mix"] = [audio_mix_item]

        return body

    async def _write_audio_file(self, audio_bytes: bytes, audio_format: str) -> str:
        """使用 UUID 文件名写入 .audio_cache/ 目录（通过 run_in_executor 异步写入）"""
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{audio_format}"
        filepath = os.path.join(AUDIO_CACHE_DIR, filename)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_file_sync, filepath, audio_bytes)

        logger.info(f"音频生成: {filepath} ({len(audio_bytes)} 字节)")
        return filepath

    @staticmethod
    def _write_file_sync(filepath: str, data: bytes) -> None:
        with open(filepath, "wb") as f:
            f.write(data)

    def _build_url(self, base_url: str, group_id: str) -> str:
        """拼接完整 API URL（含 group_id 查询参数）"""
        url = f"{base_url.rstrip('/')}/v1/t2a_v2"
        if group_id:
            url = f"{url}?GroupId={group_id}"
        return url

    async def synthesize(
        self,
        get_config: Callable,
        text: str,
        voice_id: str,
        override_emotion: Optional[str] = None,
    ) -> Optional[str]:
        """同步合成（含重试、限流、group_id、UUID 文件名）。

        Returns:
            音频文件路径（hex 模式）或 URL（url 模式），失败返回 None
        """
        api_key = get_config("minimax.api_key", "")
        base_url = get_config("minimax.base_url", "https://api.minimaxi.com")
        group_id = get_config("minimax.group_id", "")
        timeout = get_config("minimax.timeout", 30)
        max_retries = get_config("minimax.max_retries", 3)
        retry_delay = get_config("minimax.retry_delay", 1.0)
        rpm = get_config("minimax.rate_limit_rpm", 60)
        max_text_length = get_config("minimax.max_text_length", 10000)

        if not api_key:
            logger.error("未配置 API Key")
            return None
        if not voice_id:
            logger.error("未配置音色 ID")
            return None

        # 文本长度校验与截断
        if len(text) > max_text_length:
            logger.warning(f"文本长度 {len(text)} 超过限制 {max_text_length}，已截断")
            text = text[:max_text_length]

        url = self._build_url(base_url, group_id)
        body = self._build_request_body(get_config, text, voice_id, override_emotion)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        rate_limiter = self._ensure_rate_limiter(rpm)
        session = await self._ensure_session()

        last_error: Optional[str] = None

        for attempt in range(1, max_retries + 1):
            try:
                await rate_limiter.acquire()

                async with session.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API 调用失败 (HTTP {response.status}), 第 {attempt}/{max_retries} 次")
                        last_error = f"HTTP {response.status}"
                        if attempt < max_retries:
                            await asyncio.sleep(retry_delay * (2 ** (attempt - 1)))
                        continue

                    resp_json = await response.json()

                base_resp = resp_json.get("base_resp", {})
                status_code = base_resp.get("status_code", -1)
                status_msg = base_resp.get("status_msg", "未知错误")

                if status_code != 0:
                    if status_code in FATAL_ERROR_CODES:
                        logger.error(f"API 致命错误: {status_msg} (代码: {status_code})")
                        return None

                    if status_code in RETRYABLE_ERROR_CODES and attempt < max_retries:
                        logger.warning(f"API 可重试错误: {status_msg} (代码: {status_code}), 第 {attempt}/{max_retries} 次")
                        await asyncio.sleep(retry_delay * (2 ** (attempt - 1)))
                        continue

                    logger.error(f"API 返回错误: {status_msg} (代码: {status_code})")
                    return None

                data = resp_json.get("data", {})
                audio_value = data.get("audio")
                if not audio_value:
                    logger.error("API 未返回音频数据")
                    return None

                output_format = get_config("minimax.output_format", "hex")
                if output_format == "hex":
                    try:
                        audio_bytes = bytes.fromhex(audio_value)
                    except ValueError as e:
                        logger.error(f"hex 解码失败: {e}")
                        return None

                    audio_format = get_config("minimax.audio_format", "mp3")
                    return await self._write_audio_file(audio_bytes, audio_format)

                elif output_format == "url":
                    return audio_value
                else:
                    logger.error(f"不支持的输出格式: {output_format}")
                    return None

            except asyncio.TimeoutError:
                logger.error(f"API 超时, 第 {attempt}/{max_retries} 次")
                last_error = "超时"
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** (attempt - 1)))
            except aiohttp.ClientError as e:
                logger.error(f"网络错误: {e}, 第 {attempt}/{max_retries} 次")
                last_error = str(e)
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** (attempt - 1)))
            except Exception as e:
                logger.error(f"API 调用出错: {e}")
                return None

        logger.error(f"API 调用 {max_retries} 次重试后仍失败: {last_error}")
        return None

    async def synthesize_stream(
        self,
        get_config: Callable,
        text: str,
        voice_id: str,
        override_emotion: Optional[str] = None,
    ) -> Optional[str]:
        """SSE 流式合成：解析 data: 事件，拼接 hex 音频块。

        Returns:
            音频文件路径，失败返回 None
        """
        api_key = get_config("minimax.api_key", "")
        base_url = get_config("minimax.base_url", "https://api.minimaxi.com")
        group_id = get_config("minimax.group_id", "")
        timeout = get_config("minimax.timeout", 60)
        max_text_length = get_config("minimax.max_text_length", 10000)
        rpm = get_config("minimax.rate_limit_rpm", 60)

        if not api_key or not voice_id:
            logger.error("未配置 API Key 或音色 ID")
            return None

        if len(text) > max_text_length:
            logger.warning(f"文本长度 {len(text)} 超过限制 {max_text_length}，已截断")
            text = text[:max_text_length]

        url = self._build_url(base_url, group_id)
        body = self._build_request_body(get_config, text, voice_id, override_emotion)
        body["stream"] = True

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        rate_limiter = self._ensure_rate_limiter(rpm)
        session = await self._ensure_session()

        try:
            await rate_limiter.acquire()

            import json

            audio_chunks: list[bytes] = []

            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    logger.error(f"流式 API 调用失败 (HTTP {response.status})")
                    return None

                async for line_bytes in response.content:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()
                    if not data_str:
                        continue

                    try:
                        event_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # 检查错误
                    base_resp = event_data.get("base_resp", {})
                    if base_resp.get("status_code", 0) != 0:
                        logger.error(f"流式 API 错误: {base_resp.get('status_msg')}")
                        return None

                    # 提取音频块
                    data_field = event_data.get("data", {})
                    audio_hex = data_field.get("audio")
                    if audio_hex:
                        try:
                            audio_chunks.append(bytes.fromhex(audio_hex))
                        except ValueError:
                            continue

            if not audio_chunks:
                logger.error("流式合成未收到音频数据")
                return None

            combined = b"".join(audio_chunks)
            audio_format = get_config("minimax.audio_format", "mp3")
            return await self._write_audio_file(combined, audio_format)

        except asyncio.TimeoutError:
            logger.error("流式 API 超时")
            return None
        except Exception as e:
            logger.error(f"流式 API 调用出错: {e}")
            return None

    # ── 异步长文本 API (#8) ────────────────────────────

    def _build_async_url(self, base_url: str, group_id: str) -> str:
        """拼接异步合成提交 URL"""
        url = f"{base_url.rstrip('/')}/v1/t2a_v2"
        if group_id:
            url = f"{url}?GroupId={group_id}"
        return url

    def _build_query_url(self, base_url: str, group_id: str, task_id: str) -> str:
        """拼接异步任务查询 URL"""
        url = f"{base_url.rstrip('/')}/v1/query/t2a_task?task_id={task_id}"
        if group_id:
            url = f"{url}&GroupId={group_id}"
        return url

    async def synthesize_async(
        self,
        get_config: Callable,
        text: str,
        voice_id: str,
        override_emotion: Optional[str] = None,
    ) -> Optional[str]:
        """异步长文本合成：提交任务 → 轮询结果 → 下载音频。

        适用于超过 async_threshold 的长文本。MiniMax 异步 API 会返回
        task_id，通过轮询查询接口获取合成结果。

        Returns:
            音频文件路径，失败返回 None
        """
        api_key = get_config("minimax.api_key", "")
        base_url = get_config("minimax.base_url", "https://api.minimaxi.com")
        group_id = get_config("minimax.group_id", "")
        timeout = get_config("minimax.timeout", 30)
        poll_interval = get_config("minimax.async_poll_interval", 2.0)
        max_wait = get_config("minimax.async_max_wait", 300)
        rpm = get_config("minimax.rate_limit_rpm", 60)

        if not api_key or not voice_id:
            logger.error("未配置 API Key 或音色 ID")
            return None

        # 异步模式不截断文本（长文本就是它存在的意义）
        url = self._build_async_url(base_url, group_id)
        body = self._build_request_body(get_config, text, voice_id, override_emotion)
        body["stream"] = False

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        rate_limiter = self._ensure_rate_limiter(rpm)
        session = await self._ensure_session()

        try:
            # ── 1. 提交异步任务 ──
            await rate_limiter.acquire()

            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    logger.error(f"异步 API 提交失败 (HTTP {response.status})")
                    return None
                resp_json = await response.json()

            base_resp = resp_json.get("base_resp", {})
            status_code = base_resp.get("status_code", -1)

            if status_code != 0:
                logger.error(f"异步 API 提交错误: {base_resp.get('status_msg')} (代码: {status_code})")
                return None

            # 尝试直接获取音频（短文本可能直接返回）
            data = resp_json.get("data", {})
            audio_value = data.get("audio")
            if audio_value:
                return await self._process_audio_response(get_config, audio_value)

            # 获取 task_id
            task_id = data.get("task_id") or resp_json.get("task_id")
            if not task_id:
                logger.error("异步 API 未返回 task_id 或 audio")
                return None

            logger.info(f"异步合成任务已提交: task_id={task_id}")

            # ── 2. 轮询等待结果 ──
            query_url = self._build_query_url(base_url, group_id, task_id)
            query_headers = {
                "Authorization": f"Bearer {api_key}",
            }

            elapsed = 0.0
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    async with session.get(
                        query_url,
                        headers=query_headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as poll_resp:
                        if poll_resp.status != 200:
                            logger.warning(f"异步查询失败 (HTTP {poll_resp.status})，继续等待...")
                            continue
                        poll_json = await poll_resp.json()
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    logger.warning("异步查询网络错误，继续等待...")
                    continue

                poll_base = poll_json.get("base_resp", {})
                poll_status = poll_base.get("status_code", -1)

                if poll_status != 0:
                    # 任务仍在处理中 或 出错
                    task_status = poll_json.get("status") or poll_json.get("data", {}).get("status", "")
                    if task_status in ("failed", "error"):
                        logger.error(f"异步任务失败: {poll_base.get('status_msg')}")
                        return None
                    # 仍在处理中，继续轮询
                    continue

                # 成功：提取音频
                poll_data = poll_json.get("data", {})
                poll_audio = poll_data.get("audio")
                audio_url = poll_data.get("audio_url")

                if poll_audio:
                    logger.info(f"异步合成完成 (耗时 {elapsed:.1f}s)")
                    return await self._process_audio_response(get_config, poll_audio)
                elif audio_url:
                    logger.info(f"异步合成完成 (耗时 {elapsed:.1f}s)，获取音频 URL")
                    return await self._download_audio(session, audio_url, get_config)
                else:
                    # 可能还未完成，status_code=0 但还没有音频
                    task_status = poll_data.get("status", "")
                    if task_status in ("processing", "pending", "running"):
                        continue
                    logger.error("异步查询返回成功但无音频数据")
                    return None

            logger.error(f"异步合成超时（等待 {max_wait}s）")
            return None

        except asyncio.TimeoutError:
            logger.error("异步 API 超时")
            return None
        except Exception as e:
            logger.error(f"异步 API 调用出错: {e}")
            return None

    async def _process_audio_response(
        self, get_config: Callable, audio_value: str
    ) -> Optional[str]:
        """处理音频响应（hex 解码并写文件，或直接返回 URL）"""
        output_format = get_config("minimax.output_format", "hex")
        if output_format == "hex":
            try:
                audio_bytes = bytes.fromhex(audio_value)
            except ValueError as e:
                logger.error(f"hex 解码失败: {e}")
                return None
            audio_format = get_config("minimax.audio_format", "mp3")
            return await self._write_audio_file(audio_bytes, audio_format)
        elif output_format == "url":
            return audio_value
        else:
            logger.error(f"不支持的输出格式: {output_format}")
            return None

    async def _download_audio(
        self, session: aiohttp.ClientSession, audio_url: str, get_config: Callable
    ) -> Optional[str]:
        """从 URL 下载音频并保存到缓存"""
        try:
            async with session.get(audio_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.error(f"下载音频失败 (HTTP {resp.status})")
                    return None
                audio_bytes = await resp.read()

            audio_format = get_config("minimax.audio_format", "mp3")
            return await self._write_audio_file(audio_bytes, audio_format)
        except Exception as e:
            logger.error(f"下载音频出错: {e}")
            return None

    async def auto_synthesize(
        self,
        get_config: Callable,
        text: str,
        voice_id: str,
        override_emotion: Optional[str] = None,
    ) -> Optional[str]:
        """自动选择合成方式：根据文本长度和配置决定使用同步/流式/异步。

        Returns:
            音频文件路径或 URL，失败返回 None
        """
        async_enabled = get_config("minimax.async_enabled", False)
        async_threshold = get_config("minimax.async_threshold", 5000)
        stream_enabled = get_config("minimax.stream_enabled", False)

        # 长文本 + 开启异步 → 使用异步 API
        if async_enabled and len(text) > async_threshold:
            logger.info(f"文本长度 {len(text)} 超过阈值 {async_threshold}，使用异步长文本 API")
            return await self.synthesize_async(get_config, text, voice_id, override_emotion)

        # 流式
        if stream_enabled:
            return await self.synthesize_stream(get_config, text, voice_id, override_emotion)

        # 同步
        return await self.synthesize(get_config, text, voice_id, override_emotion)
