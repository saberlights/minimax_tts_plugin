# MiniMax TTS 插件

基于 MiniMax Speech 2.8 API 的高质量文本转语音和音色克隆插件。

[![MiniMax](https://img.shields.io/badge/MiniMax-Speech%202.8-blue)](https://platform.minimaxi.com)
[![License](https://img.shields.io/badge/license-AGPL--v3.0-green)](LICENSE)

## 特性

- **高质量语音合成** - 支持多种语言和音色，同步/流式/异步三种模式
- **异步长文本** - 超长文本自动切换异步 API，支持文章级别合成
- **音色克隆** - 克隆自定义音色，支持批量处理和精度控制
- **丰富的音频控制** - 语速、音调、音量、情绪等
- **音效器** - 回声、电话音、机器人等特效
- **发音词典** - 自定义多音字和专有名词发音
- **音频混合** - 支持混入背景音乐/环境音效
- **智能触发** - LLM 自动判断何时使用语音回复
- **多语言支持** - 中文、英语、日语、韩语等30+语言
- **重试与限流** - 指数退避重试、令牌桶速率限制
- **异步架构** - 全异步设计，Session 复用，无阻塞 I/O

## 快速开始

### 1. 获取 API Key

1. 访问 [MiniMax 控制台](https://platform.minimaxi.com/user-center/basic-information/interface-key)
2. 注册/登录账号
3. 创建 API Key

### 2. 配置插件

编辑 `config.toml`，填写 API Key：

```toml
[minimax]
api_key = "your_api_key_here"
voice_id = "your_voice_id"
```

### 3. 基本使用

**手动触发语音合成：**
```
/minimax 你好世界
/minimax こんにちは
```

**让 AI 自动判断：**
```
用户: 用语音念一首诗
AI: [自动调用 TTS 工具，语音回复]
```

**常驻语音模式（每句话都用语音）：**
```
/voice_always        # 开启，bot 每条回复都使用语音
/voice_always        # 再次执行关闭
```

**随机语音触发：**

在 `config.toml` 中设置概率，让 bot 随机用语音回复：
```toml
random_voice_probability = 0.3   # 30% 的概率使用语音回复
```

## 音色克隆

有两种方式克隆自定义音色：

### 方式一：国际版免费克隆（推荐）

1. 访问 [MiniMax 国际版](https://www.hailuo.ai)，新用户可**免费**克隆音色
2. 在网页端上传音频完成克隆，获得音色 ID
3. 克隆后的音色 ID 可直接在国内版 API 使用，无需额外操作

> 国内版 (https://platform.minimaxi.com) 新用户可领取 15 元免费额度用于语音合成调用。建议先在国际版免费完成音色克隆，再用国内版额度进行日常 TTS 合成。

### 方式二：命令克隆（付费）

通过插件命令调用 MiniMax API 克隆音色，**每次克隆消耗 9.9 元**。

#### 准备音频文件

将音频文件放到 `voice_audios` 目录：

```bash
voice_audios/
├── main/      # 主音频（10秒-5分钟，用于克隆）
├── prompts/   # 参考音频（<8秒，可选，增强克隆效果）
└── temp/      # 临时文件
```

#### 克隆命令

**单个克隆：**
```bash
/clone_voice audio.mp3 MyVoice001
```

**带参考音频克隆（更好的效果）：**
```bash
/clone_voice main.mp3 MyVoice002 prompt.mp3 "这是参考文本"
```

**批量克隆：**
```bash
/clone_voice_batch v1.mp3 v2.mp3 v3.mp3
```

### 音色管理

```bash
/list_voices              # 查看所有已克隆音色（含过期预警）
/list_audio               # 查看可用音频文件
/test_voice MyVoice001 测试文本   # 测试音色效果
/delete_voice MyVoice001  # 删除音色（本地+服务端）
```

> **注意**: MiniMax 克隆音色有 7 天有效期。`/list_voices` 会自动提醒即将过期的音色（超过 6 天）。

## 配置详解

### 音色基础参数

| 参数 | 说明 | 范围 | 默认值 | 推荐 |
|------|------|------|--------|------|
| `speed` | 语速 | 0.5-2.0 | 1.0 | 0.8-1.2 |
| `vol` | 音量 | 0.1-10.0 | 1.0 | 0.8-1.5 |
| `pitch` | 音调 | -12~12 | 0 | -3~3 |
| `emotion` | 情绪 | 见下表 | 留空 | 留空自动 |

**完整情绪列表**: happy / sad / angry / fearful / disgusted / surprised / calm / fluent / whisper

**示例配置：**
```toml
speed = 1.1              # 稍快
vol = 1.2                # 稍大声
pitch = -2               # 稍低沉
emotion = "calm"         # 平静情绪
```

### 高级音效器

| 参数 | 说明 | 范围 | 效果 |
|------|------|------|------|
| `voice_modify_pitch` | 音高微调 | -100~100 | 负值更深沉，正值更明亮 |
| `voice_modify_intensity` | 声音强度 | -100~100 | 负值更柔和，正值更刚劲 |
| `voice_modify_timbre` | 音色调整 | -100~100 | 负值更浑厚，正值更清脆 |
| `sound_effects` | 音效 | - | 见下表 |

**音效选项：**
- `spacious_echo` - 空旷回声
- `auditorium_echo` - 礼堂回声
- `lofi_telephone` - 电话音
- `robotic` - 机器人音

### 音质设置

| 参数 | 说明 | 可选值 | 默认 | 推荐 |
|------|------|--------|------|------|
| `sample_rate` | 采样率(Hz) | 8000/16000/22050/24000/32000/44100 | 32000 | **44100** |
| `bitrate` | 比特率(bps) | 32000/64000/128000/256000 | 128000 | **256000** |
| `audio_format` | 音频格式 | mp3/wav/flac/pcm | mp3 | mp3 |
| `channel` | 声道数 | 1/2 | 1 | **1** |

### 尾部停顿（防止截断）

```toml
trailing_pause = 1.0     # 尾部停顿1秒，防止最后一个字被截断
```

### 语言增强

```toml
language_boost = "Japanese"   # 增强日语识别
```

**支持语言：**
- `auto` - 自动检测
- `Chinese` - 中文
- `Chinese,Yue` - 粤语
- `English` - 英语
- `Japanese` - 日语
- `Korean` - 韩语
- 以及其他30+语言

### 流式合成

```toml
stream_enabled = true    # 启用 SSE 流式合成，降低首包延迟
```

### 重试与限流

```toml
max_retries = 3          # 最大重试次数
retry_delay = 1.0        # 重试初始延迟（指数退避）
rate_limit_rpm = 60      # 每分钟最大请求数
max_text_length = 10000  # 单次合成最大文本长度
```

### 文本处理

```toml
text_normalization = true       # 优化数字、日期朗读（略增延迟）
english_normalization = true    # 优化英文缩写、数字朗读
latex_read = true               # 支持 LaTeX 公式朗读（需用$包裹）
```

### 发音词典

自定义特定词语的发音，适用于专有名词、多音字等场景：

```toml
# JSON 格式，tone 数组内每项格式为 "原文/(拼音)"
pronunciation_dict = '{"tone":["处理/(chǔ lǐ)","重庆/(chóng qìng)"]}'
```

**说明**：
- `tone` 数组中的每项指定一个词的发音
- 格式为 `原文/(拼音)`，拼音使用带声调的拼音
- 适合修正多音字、专业术语的发音
- 留空则不使用发音词典

### 音频混合（背景音乐）

在合成语音中混入背景音频（如背景音乐、环境音）：

```toml
audio_mix_url = "https://example.com/bgm.mp3"   # 背景音频 URL（公网可访问）
audio_mix_volume = 0.2                            # 背景音量 (0.0-1.0)
audio_mix_start_time = 0                          # 开始时间（毫秒）
audio_mix_end_time = -1                           # 结束时间（-1=到结尾）
audio_mix_repeat = true                           # 循环播放
```

**典型场景**：
- 有声书朗读配背景音乐
- 播客节目配环境音效
- 诗歌朗诵配意境音乐

**注意**：`audio_mix_url` 必须是公网可直接访问的音频链接（mp3/wav），留空则不混合。

### 异步长文本合成

当文本超长（如文章、小说章节）时，自动使用异步 API 避免超时：

```toml
async_enabled = true        # 启用异步长文本合成
async_threshold = 5000      # 触发阈值（字符数），超过则自动使用异步
async_poll_interval = 2.0   # 轮询间隔（秒）
async_max_wait = 300        # 最大等待时间（秒）
```

**工作方式**：
1. 文本长度超过 `async_threshold` 时自动提交异步任务
2. 插件在后台轮询任务状态
3. 合成完成后自动获取并发送音频
4. 文本未超过阈值时仍走正常同步/流式接口

**合成模式自动选择优先级**：
1. 长文本 + `async_enabled=true` → 异步 API
2. `stream_enabled=true` → SSE 流式
3. 默认 → 同步 API

### 拟声词说明

MiniMax TTS 支持在文本中使用特殊标记控制语音效果：

- **停顿标记**: `<#秒数#>` - 例如 `<#1.50#>` 表示停顿 1.5 秒
- 插件自动在文本末尾添加可配置的 `trailing_pause` 停顿

## 音色克隆配置

```toml
[voice_clone]
test_text = "你好，这是音色克隆测试。"
need_noise_reduction = false         # 源音频有噪音时启用
need_volume_normalization = false    # 音量不稳定时启用
accuracy = 0.7                       # 克隆精度 (0-1)
```

`accuracy` 参数说明：值越高越接近原声，但可能降低合成自然度。推荐 0.5-0.8。

## 音频要求

### 主音频（用于克隆）

| 项目 | 要求 |
|------|------|
| 格式 | mp3, m4a, wav, flac |
| 时长 | 10秒 - 5分钟 |
| 大小 | <= 20MB |
| 内容 | 清晰人声，无敏感内容 |
| 建议 | 朗读文本，语速均匀，无背景音乐 |

### 参考音频（可选，增强效果）

| 项目 | 要求 |
|------|------|
| 格式 | mp3, m4a, wav, flac |
| 时长 | < 8秒 |
| 大小 | <= 20MB |
| 用途 | 提供音色参考，提升克隆效果 |

## 语音触发机制

插件有多种方式触发语音回复，按优先级从高到低：

1. **常驻语音模式** (`/voice_always`) — 开启后每条回复都使用语音
2. **LLM 工具标记** — AI 检测到语音关键词时自动调用 `request_voice_reply` 工具
3. **概率随机触发** (`random_voice_probability`) — 按配置的概率随机触发语音

### LLM 智能触发

插件会在检测到以下关键词时自动使用语音回复：

**强制触发关键词：**
- 语音相关: "语音"、"voice"、"音频"、"audio"
- 朗读相关: "朗读"、"念"、"读"、"说"、"讲"
- 声音相关: "声音"、"听"、"发音"

**情绪自动选择**：
- 工具 `request_voice_reply` 支持可选参数 `emotion`
- 完整选项：happy / sad / angry / fearful / disgusted / surprised / calm / fluent / whisper
- AI 可根据回复语气自动选择最合适的情绪

### 情绪决策机制

插件按以下优先级决定语音情绪：

1. **LLM 显式指定** — AI 调用工具时通过 `emotion` 参数指定（最高优先级）
2. **配置默认值** — `config.toml` 中 `emotion` 字段非空时使用
3. **MiniMax 模型自动推断** — 不传 `emotion` 参数时，模型根据文本内容自动选择最自然的情绪

```toml
emotion = ""    # 留空 = 让 MiniMax 模型自动推断（推荐）
emotion = "calm"  # 固定使用平静情绪
```

> 推荐保持 `emotion` 为空。MiniMax Speech 2.8 模型内置了基于深度学习的情绪推断，效果优于手动指定。

### 随机概率触发

```toml
random_voice_probability = 0.2   # 20% 概率使用语音，0.0=关闭
```

### 常驻语音模式

发送 `/voice_always` 开启，bot 之后每条回复都用语音。再次发送关闭。
常驻模式下如果 LLM 同时标记了情绪，会使用 LLM 选择的情绪。

## 组件控制

```toml
[components]
command_enabled = true         # 手动命令 (/minimax)
tool_enabled = true            # LLM工具调用
handler_enabled = true         # 事件处理器
voice_clone_enabled = true     # 音色克隆功能
```

## 常见问题

### Q: 克隆失败，提示风控不通过？

启用降噪或更换清晰的朗读音频：
```toml
[voice_clone]
need_noise_reduction = true
```

### Q: 语音最后一个字被截断？

增加尾部停顿：
```toml
trailing_pause = 1.5
```

### Q: 音质不如预期？

提高采样率和比特率：
```toml
sample_rate = 44100
bitrate = 256000
```

### Q: 如何获取系统音色ID？

访问 [系统音色列表](https://platform.minimaxi.com/faq/system-voice-id) 或使用 [获取音色API](https://platform.minimaxi.com/api-reference/voice-management-get)。

## 参考资源

### 官方文档
- [MiniMax TTS API](https://platform.minimaxi.com/document/T2A%20V2)
- [音色克隆 API](https://platform.minimaxi.com/document/%E5%BF%AB%E9%80%9F%E5%85%8B%E9%9A%86)
- [系统音色列表](https://platform.minimaxi.com/faq/system-voice-id)
- [错误代码参考](https://platform.minimaxi.com/api-reference/errorcode)

### 控制台
- [MiniMax 控制台](https://platform.minimaxi.com)
- [API Keys 管理](https://platform.minimaxi.com/user-center/basic-information/interface-key)

## 依赖

- `aiohttp` - 异步HTTP请求

## 许可证

本插件基于 AGPL-v3.0 许可证开源。
