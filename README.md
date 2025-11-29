# MiniMax TTS 插件

基于 MiniMax Speech 2.6 API 的高质量文本转语音和音色克隆插件。

[![MiniMax](https://img.shields.io/badge/MiniMax-Speech%202.6-blue)](https://platform.minimaxi.com)
[![License](https://img.shields.io/badge/license-AGPL--v3.0-green)](LICENSE)

## ✨ 特性

- 🎙️ **高质量语音合成** - 支持多种语言和音色
- 🎭 **音色克隆** - 克隆自定义音色，支持批量处理
- 🎚️ **丰富的音频控制** - 语速、音调、音量、情绪等
- 🎨 **音效器** - 回声、电话音、机器人等特效
- 🤖 **智能触发** - LLM 自动判断何时使用语音回复
- 🌍 **多语言支持** - 中文、英语、日语、韩语等30+语言

## 📦 快速开始

### 1. 获取 API Key

1. 访问 [MiniMax 控制台](https://platform.minimaxi.com/user-center/basic-information/interface-key)
2. 注册/登录账号
3. 创建 API Key

### 2. 配置插件

编辑 `config.toml`，填写 API Key：

```toml
[minimax]
api_key = "your_api_key_here"
voice_id = "moss_audio_51758de9-c2ad-11f0-acdb-d238e4d54c00"
```

### 3. 基本使用

**手动触发语音合成：**
```
/minimax 你好世界
/minimax こんにちは Japanese_Voice
```

**让 AI 自动判断：**
```
用户: 用语音念一首诗
AI: [自动调用 TTS 工具，语音回复]
```

## 🎤 音色克隆

### 准备音频文件

将音频文件放到 `voice_audios` 目录：

```bash
voice_audios/
├── main/      # 主音频（10秒-5分钟，用于克隆）
├── prompts/   # 参考音频（<8秒，可选，增强克隆效果）
└── temp/      # 临时文件
```

### 克隆命令

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
/list_voices              # 查看所有已克隆音色
/list_audio               # 查看可用音频文件
/test_voice MyVoice001 测试文本   # 测试音色效果
/delete_voice MyVoice001  # 删除音色
```

## ⚙️ 配置详解

### 🎵 音色基础参数

| 参数 | 说明 | 范围 | 默认值 | 推荐 |
|------|------|------|--------|------|
| `speed` | 语速 | 0.5-2.0 | 1.0 | 0.8-1.2 |
| `vol` | 音量 | 0.1-10.0 | 1.0 | 0.8-1.5 |
| `pitch` | 音调 | -12~12 | 0 | -3~3 |
| `emotion` | 情绪 | happy/sad/angry/calm/fluent | 留空 | 留空自动 |

**示例配置：**
```toml
speed = 1.1              # 稍快
vol = 1.2                # 稍大声
pitch = -2               # 稍低沉
emotion = "calm"         # 平静情绪
```

### 🎨 高级音效器

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

**示例配置：**
```toml
voice_modify_pitch = -30      # 更低沉
voice_modify_intensity = 20   # 更有力
voice_modify_timbre = 10      # 稍清脆
sound_effects = "spacious_echo"
```

### 🎧 音质设置

| 参数 | 说明 | 可选值 | 默认 | 推荐 |
|------|------|--------|------|------|
| `sample_rate` | 采样率(Hz) | 8000/16000/32000/44100 | 32000 | **44100** |
| `bitrate` | 比特率(bps) | 32000/64000/128000/256000 | 128000 | **256000** |
| `audio_format` | 音频格式 | mp3/wav/flac/pcm | mp3 | mp3 |
| `channel` | 声道数 | 1/2 | 1 | **1** |

**高音质配置：**
```toml
sample_rate = 44100      # CD音质
bitrate = 256000         # 最高比特率
audio_format = "mp3"     # 兼容性好
channel = 1              # 单声道（TTS推荐）
```

### ⏸️ 尾部停顿（防止截断）

```toml
trailing_pause = 1.0     # 尾部停顿1秒，防止最后一个字被截断
```

| 场景 | 推荐值 |
|------|--------|
| 一般对话 | 1.0 |
| 正式朗读 | 1.5 |
| 快速交互 | 0.5 |
| 语音被截断 | 1.5-2.0 |

### 🌍 语言增强

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
- `French` - 法语
- `German` - 德语
- `Spanish` - 西班牙语
- 以及其他30+语言

### 🔧 特殊功能

```toml
text_normalization = true    # 优化数字、日期朗读（略增延迟）
latex_read = true            # 支持LaTeX公式朗读（需用$包裹）
```

**LaTeX 示例：**
```
文本：二次方程 $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$ 的解
（注意：代码中的 \ 需要转义为 \\）
```

## 🎭 音色克隆配置

```toml
[voice_clone]
test_text = "你好，这是音色克隆测试。"
need_noise_reduction = false         # 源音频有噪音时启用
need_volume_normalization = false    # 音量不稳定时启用
```

**何时启用降噪/归一化：**
- ✅ 音频有背景噪音 → `need_noise_reduction = true`
- ✅ 音频音量忽大忽小 → `need_volume_normalization = true`
- ❌ 音频质量很好 → 保持 `false`

## 📋 音频要求

### 主音频（用于克隆）

| 项目 | 要求 |
|------|------|
| 格式 | mp3, m4a, wav, flac |
| 时长 | 10秒 - 5分钟 |
| 大小 | ≤ 20MB |
| 内容 | 清晰人声，无敏感内容 |
| 建议 | 朗读文本，语速均匀，无背景音乐 |

### 参考音频（可选，增强效果）

| 项目 | 要求 |
|------|------|
| 格式 | mp3, m4a, wav, flac |
| 时长 | < 8秒 |
| 大小 | ≤ 20MB |
| 用途 | 提供音色参考，提升克隆效果 |

## 🤖 智能触发（LLM自动判断）

插件会在检测到以下关键词时自动使用语音回复：

**强制触发关键词：**
- 语音相关: "语音"、"voice"、"音频"、"audio"
- 朗读相关: "朗读"、"念"、"读"、"说"、"讲"
- 声音相关: "声音"、"听"、"发音"

**典型触发句式：**
- "用语音xxx"
- "发语音xxx"
- "念xxx"
- "朗读xxx"

**特殊场景（AI自主判断）：**
- 诗歌、歌词、台词
- 语言学习、发音练习
- 需要情感表达的内容

## 🛠️ 组件控制

```toml
[components]
command_enabled = true         # 手动命令 (/minimax)
tool_enabled = true            # LLM工具调用
handler_enabled = true         # 事件处理器
voice_clone_enabled = true     # 音色克隆功能
```

| 组件 | 说明 | 禁用影响 |
|------|------|---------|
| `command_enabled` | 手动命令触发 | 无法使用 /minimax |
| `tool_enabled` | AI自动判断 | AI无法自动语音回复 |
| `handler_enabled` | 执行TTS | 无法合成语音 |
| `voice_clone_enabled` | 克隆功能 | 无法克隆/管理音色 |

## ❓ 常见问题

### Q: 克隆失败，提示风控不通过？

**可能原因：**
- 音频包含敏感内容
- 音频质量差被误判
- 背景噪音被误识别

**解决方案：**
```toml
[voice_clone]
need_noise_reduction = true    # 启用降噪
```

或更换清晰的朗读音频。

### Q: 语音最后一个字被截断？

**解决方案：**
```toml
trailing_pause = 1.5    # 增加尾部停顿
```

### Q: 音质不如官网？

**优化配置：**
```toml
sample_rate = 44100     # 提高采样率
bitrate = 256000        # 提高比特率
channel = 1             # 使用单声道
```

### Q: 音色ID重复？

**解决方案：**
```bash
/delete_voice OldVoiceID   # 删除旧音色
/clone_voice audio.mp3 NewVoiceID   # 重新克隆
```

### Q: 找不到音频文件？

**解决方案：**
```bash
/list_audio   # 查看可用文件
```
确认文件在 `voice_audios/main/` 或 `voice_audios/prompts/` 目录。

### Q: 如何获取系统音色ID？

访问 [系统音色列表](https://platform.minimaxi.com/faq/system-voice-id) 或使用 [获取音色API](https://platform.minimaxi.com/api-reference/voice-management-get)。

## 📚 参考资源

### 官方文档
- [MiniMax TTS API](https://platform.minimaxi.com/document/T2A%20V2)
- [音色克隆 API](https://platform.minimaxi.com/document/%E5%BF%AB%E9%80%9F%E5%85%8B%E9%9A%86)
- [系统音色列表](https://platform.minimaxi.com/faq/system-voice-id)
- [错误代码参考](https://platform.minimaxi.com/api-reference/errorcode)

### 控制台
- [MiniMax 控制台](https://platform.minimaxi.com)
- [API Keys 管理](https://platform.minimaxi.com/user-center/basic-information/interface-key)

## 🔧 依赖

- `aiohttp` - 异步HTTP请求

## 📄 许可证

本插件基于 AGPL-v3.0 许可证开源。

---

**💡 提示：** 首次使用建议先测试默认配置，再根据需要调整参数。
