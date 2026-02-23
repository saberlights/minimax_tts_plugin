"""/minimax_help 命令：显示所有可用命令"""

from typing import Tuple

from src.plugin_system.base.base_command import BaseCommand


HELP_TEXT = """MiniMax TTS 插件 - 命令列表

语音合成：
  /minimax <文本>          合成指定文本的语音
  /voice_always            切换常驻语音模式（再次执行关闭）

音色克隆（每次 9.9 元）：
  /clone_voice <音频> <ID> [参考音频] [参考文本]
                           克隆单个音色
  /clone_voice_batch <音频1> <音频2> ...
                           批量克隆音色

音色管理：
  /list_voices             查看已克隆音色
  /list_audio              查看可用音频文件
  /test_voice <ID> <文本>  试听指定音色
  /delete_voice <ID>       删除音色（本地+服务端）

提示：
  - 在国际版 (hailuo.ai) 新用户可免费克隆音色
  - 克隆音色需在 7 天内使用一次 TTS 合成来永久保留
  - 发送含"语音"等关键词的消息可让 AI 自动语音回复"""


class HelpCommand(BaseCommand):
    """显示 MiniMax TTS 插件所有可用命令"""

    command_name = "minimax_help"
    command_description = "查看 MiniMax TTS 插件帮助"
    command_pattern = r"^/minimax_help$"
    command_help = "用法：/minimax_help"
    command_examples = ["/minimax_help"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        await self.send_text(HELP_TEXT)
        return True, "已发送帮助", True
