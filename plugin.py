"""MiniMax TTS 插件 - 文本转语音和音色克隆

基于 MiniMax Speech 2.8 API 的语音合成插件
API: https://api.minimaxi.com
文档: https://platform.minimaxi.com/document/T2A%20V2
"""

from typing import List, Tuple, Type

from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.apis.plugin_register_api import register_plugin

from .config_schema import CONFIG_SCHEMA, CONFIG_SECTION_DESCRIPTIONS
from .voice_clone import VoiceCloneManager
from .components.tts_tool import MiniMaxTTSTool
from .components.tts_handler import MiniMaxTTSEventHandler, set_voice_clone_manager as set_handler_vcm
from .components.tts_command import MiniMaxTTSCommand
from .components.clone_commands import (
    CloneVoiceCommand,
    ListVoicesCommand,
    TestVoiceCommand,
    DeleteVoiceCommand,
    ListAudioCommand,
    CloneVoiceBatchCommand,
    set_voice_clone_manager as set_clone_vcm,
)
from .components.voice_always_command import VoiceAlwaysCommand

# 共享的 VoiceCloneManager 实例
_voice_clone_manager = VoiceCloneManager()

# 注入到需要它的模块
set_handler_vcm(_voice_clone_manager)
set_clone_vcm(_voice_clone_manager)


@register_plugin
class MiniMaxTTSPlugin(BasePlugin):
    """MiniMax TTS 插件"""

    plugin_name = "minimax_tts_plugin"
    plugin_description = "MiniMax 文本转语音插件"
    plugin_version = "2.0.0"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp"]

    config_section_descriptions = CONFIG_SECTION_DESCRIPTIONS
    config_schema = CONFIG_SCHEMA

    def get_plugin_components(self) -> List[Tuple]:
        components = []

        command_enabled = self.get_config("components.command_enabled", True)
        tool_enabled = self.get_config("components.tool_enabled", True)
        handler_enabled = self.get_config("components.handler_enabled", True)
        voice_clone_enabled = self.get_config("components.voice_clone_enabled", True)

        if command_enabled:
            components.append((MiniMaxTTSCommand.get_command_info(), MiniMaxTTSCommand))
            components.append((VoiceAlwaysCommand.get_command_info(), VoiceAlwaysCommand))
        if tool_enabled:
            components.append((MiniMaxTTSTool.get_tool_info(), MiniMaxTTSTool))
        if handler_enabled:
            components.append((MiniMaxTTSEventHandler.get_handler_info(), MiniMaxTTSEventHandler))

        if voice_clone_enabled:
            components.append((CloneVoiceCommand.get_command_info(), CloneVoiceCommand))
            components.append((ListVoicesCommand.get_command_info(), ListVoicesCommand))
            components.append((TestVoiceCommand.get_command_info(), TestVoiceCommand))
            components.append((DeleteVoiceCommand.get_command_info(), DeleteVoiceCommand))
            components.append((ListAudioCommand.get_command_info(), ListAudioCommand))
            components.append((CloneVoiceBatchCommand.get_command_info(), CloneVoiceBatchCommand))

        return components
