# MiniMax TTS 插件

基于 MiniMax Speech 2.6 API 的文本转语音和音色克隆插件。

## 快速开始

### 1. 配置 API Key

编辑 `config.toml`，填写 API Key：

```toml
[minimax]
api_key = "your_api_key_here"
voice_id = "your_voice_id"
```

获取 API Key：[MiniMax 控制台](https://platform.minimaxi.com/user-center/basic-information/interface-key)

### 2. 基本命令

**TTS 合成：**
```
/minimax 你好世界
```

**音色克隆：**
```
/clone_voice audio.mp3 MyVoice001
/clone_voice_batch v1.mp3 v2.mp3 v3.mp3
```

**音色管理：**
```
/list_voices          # 查看已克隆音色
/list_audio           # 查看可用音频
/test_voice ID 测试文本
/delete_voice ID
```

## 音频文件管理

### 目录结构
```
voice_audios/
├── main/      # 主音频（10秒-5分钟）
├── prompts/   # 参考音频（<8秒）
└── temp/      # 临时文件
```

### 使用方式

1. **上传音频**
   ```bash
   cp audio.mp3 voice_audios/main/
   ```

2. **查看可用音频**
   ```
   /list_audio
   ```

3. **克隆音色**
   ```
   /clone_voice audio.mp3 MyVoice
   ```

## 配置说明

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `model` | TTS模型 | speech-2.6-hd |
| `voice_id` | 默认音色ID | - |
| `speed` | 语速 [0.5-2.0] | 1.0 |
| `vol` | 音量 [0-10] | 1.0 |
| `pitch` | 音高 [-12~12] | 0 |

### 音色克隆

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `test_text` | 试听文本 | - |
| `need_noise_reduction` | 启用降噪 | false |
| `need_volume_normalization` | 音量归一化 | false |

## 音频要求

**主音频：**
- 格式：mp3、m4a、wav
- 时长：10秒-5分钟
- 大小：≤20MB

**参考音频：**
- 格式：mp3、m4a、wav
- 时长：<8秒
- 大小：≤20MB

## 常见问题

### Q: 克隆失败，提示风控不通过？
A: 检查音频内容是否合规，避免敏感词汇。可启用降噪：
```toml
[voice_clone]
need_noise_reduction = true
```

### Q: 音色ID重复？
A: 使用新的ID，或删除旧音色后重新克隆。

### Q: 文件不存在？
A: 使用 `/list_audio` 查看可用文件，确认文件名正确。

## API 文档

- [MiniMax TTS API](https://platform.minimaxi.com/document/T2A%20V2)
- [音色克隆 API](https://platform.minimaxi.com/document/%E5%BF%AB%E9%80%9F%E5%85%8B%E9%9A%86)
- [MiniMax 控制台](https://platform.minimaxi.com)

## 依赖

- aiohttp

## 许可证

AGPL-v3.0
