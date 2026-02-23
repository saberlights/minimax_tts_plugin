"""MiniMax TTS 插件配置 schema 与常量定义"""

from src.plugin_system.base.config_types import ConfigField

# 有效情绪枚举（完整 9 种）
VALID_EMOTIONS = frozenset({
    "happy", "sad", "angry", "fearful", "disgusted",
    "surprised", "calm", "fluent", "whisper",
})

# 可重试的 API 错误码
RETRYABLE_ERROR_CODES = {1001, 1002}

# 致命错误码（不应重试）
FATAL_ERROR_CODES = {1004, 1008}

# 支持的音频格式
VALID_AUDIO_FORMATS = frozenset({"mp3", "m4a", "wav", "flac"})

# 最大上传文件大小 (20MB)
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

CONFIG_SECTION_DESCRIPTIONS = {
    "plugin": "插件配置",
    "components": "组件控制",
    "minimax": "API配置\n# 提示：在国际版 (https://www.hailuo.ai) 可免费克隆音色，音色ID可直接在国内版使用。\n#       国内版 (https://platform.minimaxi.com) 新用户可领取15元免费额度用于语音合成。",
    "voice_clone": "音色克隆配置",
}

CONFIG_SCHEMA = {
    "plugin": {
        "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
    },
    "components": {
        "command_enabled": ConfigField(
            type=bool, default=True,
            description="启用手动命令触发TTS (/minimax <文本>)",
        ),
        "tool_enabled": ConfigField(
            type=bool, default=True,
            description="启用LLM工具调用 (让AI自动判断何时使用语音回复)",
        ),
        "handler_enabled": ConfigField(
            type=bool, default=True,
            description="启用事件处理器 (执行实际的语音合成)",
        ),
        "voice_clone_enabled": ConfigField(
            type=bool, default=True,
            description="启用音色克隆命令 (/clone_voice等)",
        ),
    },
    "minimax": {
        "base_url": ConfigField(
            type=str, default="https://api.minimaxi.com",
            description="MiniMax API 基础地址 (不含路径，路径由客户端拼接)",
        ),
        "api_key": ConfigField(
            type=str, default="", input_type="password",
            description="API密钥 (在 https://platform.minimaxi.com 获取)",
        ),
        "group_id": ConfigField(
            type=str, default="",
            description="MiniMax Group ID (可选，留空即可，部分旧接口可能需要)",
        ),
        "model": ConfigField(
            type=str, default="speech-2.8-hd",
            description="TTS模型 | 可选: speech-2.8-hd(高清), speech-2.8-turbo(快速), speech-2.6-hd, speech-2.6-turbo",
        ),
        "voice_id": ConfigField(
            type=str, default="",
            description="默认音色ID | 支持系统音色/克隆音色/AI生成音色",
        ),
        "timeout": ConfigField(
            type=int, default=30,
            description="API请求超时时间(秒) | 长文本可适当增加",
        ),
        "language_boost": ConfigField(
            type=str, default="auto",
            description="语言增强 | 可选: auto(自动), Chinese(中文), English(英语), Japanese(日语)等",
        ),
        "output_format": ConfigField(
            type=str, default="hex",
            description="输出格式 | hex: 直接返回音频数据, url: 返回24小时有效URL",
        ),
        "emotion": ConfigField(
            type=str, default="",
            description="语音情绪 | 可选: happy/sad/angry/fearful/disgusted/surprised/calm/fluent/whisper | 留空则由模型自动推断",
        ),
        "text_normalization": ConfigField(
            type=bool, default=False,
            description="文本规范化 | 开启后优化数字、日期等朗读效果 (略增延迟)",
        ),
        "english_normalization": ConfigField(
            type=bool, default=False,
            description="英文文本规范化 | 开启后优化英文缩写、数字等朗读",
        ),
        "latex_read": ConfigField(
            type=bool, default=False,
            description="LaTeX公式朗读 | 开启后支持朗读数学公式 (需用$包裹公式)",
        ),
        "trailing_pause": ConfigField(
            type=float, default=1.0,
            description="尾部停顿(秒) | 防止最后一个字被截断 | 范围: 0-99.99, 推荐: 0.5-2.0",
        ),
        "speed": ConfigField(
            type=float, default=1.0,
            description="语速 | 范围: 0.5(慢)-2.0(快), 1.0为正常速度",
        ),
        "vol": ConfigField(
            type=float, default=1.0,
            description="音量 | 范围: 0.1(小)-10.0(大), 1.0为正常音量",
        ),
        "pitch": ConfigField(
            type=int, default=0,
            description="音调 | 范围: -12(低沉)~12(尖锐), 0为原始音调",
        ),
        "voice_modify_pitch": ConfigField(
            type=int, default=0,
            description="[效果器]音高微调 | 范围: -100(深沉)~100(明亮), 比pitch更细腻",
        ),
        "voice_modify_intensity": ConfigField(
            type=int, default=0,
            description="[效果器]声音强度 | 范围: -100(柔和)~100(刚劲)",
        ),
        "voice_modify_timbre": ConfigField(
            type=int, default=0,
            description="[效果器]音色调整 | 范围: -100(浑厚)~100(清脆)",
        ),
        "sound_effects": ConfigField(
            type=str, default="",
            description="音效 | 可选: spacious_echo(空旷回声), auditorium_echo(礼堂回声), lofi_telephone(电话音), robotic(机器人)",
        ),
        "sample_rate": ConfigField(
            type=int, default=32000,
            description="采样率(Hz) | 可选: 8000/16000/22050/24000/32000/44100, 越高音质越好 | 推荐: 44100",
        ),
        "bitrate": ConfigField(
            type=int, default=128000,
            description="比特率(bps) | 可选: 32000/64000/128000/256000, 越高音质越好 | 推荐: 256000",
        ),
        "audio_format": ConfigField(
            type=str, default="mp3",
            description="音频格式 | 可选: mp3(兼容性好), wav(无损), flac(无损压缩), pcm(原始)",
        ),
        "channel": ConfigField(
            type=int, default=1,
            description="声道数 | 1: 单声道(推荐TTS), 2: 立体声",
        ),
        "stream_enabled": ConfigField(
            type=bool, default=False,
            description="启用流式合成 | 开启后使用 SSE 流式接口，降低首包延迟",
        ),
        "max_retries": ConfigField(
            type=int, default=3,
            description="API 请求最大重试次数",
        ),
        "retry_delay": ConfigField(
            type=float, default=1.0,
            description="重试初始延迟(秒) | 使用指数退避策略",
        ),
        "rate_limit_rpm": ConfigField(
            type=int, default=60,
            description="每分钟最大请求数 | 速率限制",
        ),
        "max_text_length": ConfigField(
            type=int, default=10000,
            description="单次合成最大文本长度(字符) | 超过将截断",
        ),
        # ── 异步长文本 API ──
        "async_enabled": ConfigField(
            type=bool, default=False,
            description="启用异步长文本合成 | 文本超过 async_threshold 字符时自动使用异步 API",
        ),
        "async_threshold": ConfigField(
            type=int, default=5000,
            description="异步合成触发阈值(字符) | 超过此长度自动切换异步 API",
        ),
        "async_poll_interval": ConfigField(
            type=float, default=2.0,
            description="异步任务轮询间隔(秒)",
        ),
        "async_max_wait": ConfigField(
            type=int, default=300,
            description="异步任务最大等待时间(秒) | 超时后放弃",
        ),
        # ── 发音词典 ──
        "pronunciation_dict": ConfigField(
            type=str, default="",
            description='发音词典 | JSON 格式，例: {"tone":["处理/(chǔ lǐ)","zhǐ/(指)"]} | 留空不使用',
        ),
        # ── 音频混合 ──
        "audio_mix_url": ConfigField(
            type=str, default="",
            description="背景音频 URL | 留空不混合 | 支持 mp3/wav 格式的公网可访问 URL",
        ),
        "audio_mix_volume": ConfigField(
            type=float, default=0.3,
            description="背景音频音量 | 范围: 0.0-1.0, 推荐: 0.1-0.3",
        ),
        "audio_mix_start_time": ConfigField(
            type=int, default=0,
            description="背景音频开始时间(毫秒) | 0 表示从头开始",
        ),
        "audio_mix_end_time": ConfigField(
            type=int, default=-1,
            description="背景音频结束时间(毫秒) | -1 表示到音频结尾",
        ),
        "audio_mix_repeat": ConfigField(
            type=bool, default=True,
            description="背景音频循环播放 | 当语音长度超过背景音频时是否循环",
        ),
        # ── 概率触发 ──
        "random_voice_probability": ConfigField(
            type=float, default=0.0,
            description="随机语音概率 | 范围: 0.0-1.0 | 每条回复有此概率自动使用语音 | 0.0=关闭, 1.0=每条都语音",
        ),
    },
    "voice_clone": {
        "test_text": ConfigField(
            type=str, default="你好，这是音色克隆测试。",
            description="克隆音色时的试听文本 (会自动生成试听音频)",
        ),
        "need_noise_reduction": ConfigField(
            type=bool, default=False,
            description="克隆时启用降噪 | 源音频有背景噪音时建议开启",
        ),
        "need_volume_normalization": ConfigField(
            type=bool, default=False,
            description="克隆时启用音量归一化 | 源音频音量不稳定时建议开启",
        ),
        "accuracy": ConfigField(
            type=float, default=0.7,
            description="克隆精度 | 范围: 0-1, 值越高越接近原声但可能降低自然度",
        ),
    },
}
