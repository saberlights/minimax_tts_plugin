"""音频工具：路径解析、文件列表、缓存清理"""

import asyncio
import os
import time
from functools import partial
from typing import Any, Dict, List, Optional

from src.common.logger import get_logger

logger = get_logger("minimax_tts_plugin")

# 目录常量（上溯到插件根目录）
PLUGIN_DIR = os.path.dirname(os.path.dirname(__file__))
VOICE_AUDIOS_DIR = os.path.join(PLUGIN_DIR, "voice_audios")
AUDIO_CACHE_DIR = os.path.join(PLUGIN_DIR, ".audio_cache")

AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".wav", ".flac"})


def resolve_audio_path(audio_path: str) -> Optional[str]:
    """解析音频路径，支持相对路径和绝对路径。

    Args:
        audio_path: 音频路径（可以是文件名、相对路径或绝对路径）

    Returns:
        完整的绝对路径，如果文件不存在返回 None
    """
    if os.path.isabs(audio_path) and os.path.exists(audio_path):
        return audio_path

    search_dirs = [
        VOICE_AUDIOS_DIR,
        os.path.join(VOICE_AUDIOS_DIR, "main"),
        os.path.join(VOICE_AUDIOS_DIR, "prompts"),
    ]

    for directory in search_dirs:
        path = os.path.join(directory, audio_path)
        if os.path.exists(path):
            return path

    return None


def _list_audio_files_sync() -> Dict[str, List[Dict[str, Any]]]:
    """同步列出 voice_audios 目录下的所有音频文件（在 executor 中调用）"""
    result: Dict[str, List[Dict[str, Any]]] = {
        "main": [],
        "prompts": [],
        "root": [],
    }

    scan_targets = [
        ("main", os.path.join(VOICE_AUDIOS_DIR, "main")),
        ("prompts", os.path.join(VOICE_AUDIOS_DIR, "prompts")),
    ]

    try:
        for key, directory in scan_targets:
            if not os.path.exists(directory):
                continue
            for filename in os.listdir(directory):
                if os.path.splitext(filename)[1].lower() in AUDIO_EXTENSIONS:
                    filepath = os.path.join(directory, filename)
                    stat = os.stat(filepath)
                    result[key].append({
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })

        # 扫描根目录
        if os.path.exists(VOICE_AUDIOS_DIR):
            for filename in os.listdir(VOICE_AUDIOS_DIR):
                filepath = os.path.join(VOICE_AUDIOS_DIR, filename)
                if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in AUDIO_EXTENSIONS:
                    stat = os.stat(filepath)
                    result["root"].append({
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
    except Exception as e:
        logger.error(f"列出音频文件失败: {e}")

    return result


async def list_audio_files() -> Dict[str, List[Dict[str, Any]]]:
    """异步列出 voice_audios 目录下的所有音频文件"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_audio_files_sync)


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


async def cleanup_audio_cache(max_age_hours: int = 24) -> int:
    """清理过期的临时音频缓存文件。

    Args:
        max_age_hours: 最大保留时间（小时）

    Returns:
        删除的文件数
    """
    def _cleanup() -> int:
        if not os.path.exists(AUDIO_CACHE_DIR):
            return 0

        deleted = 0
        now = time.time()
        max_age_seconds = max_age_hours * 3600

        for filename in os.listdir(AUDIO_CACHE_DIR):
            filepath = os.path.join(AUDIO_CACHE_DIR, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                if now - os.path.getmtime(filepath) > max_age_seconds:
                    os.remove(filepath)
                    deleted += 1
            except OSError:
                pass

        return deleted

    loop = asyncio.get_running_loop()
    count = await loop.run_in_executor(None, _cleanup)
    if count > 0:
        logger.info(f"清理了 {count} 个过期缓存音频文件")
    return count
