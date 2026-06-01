```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
```

## 项目概述

MP3 Tagger 是一个基于 Python 的 MP3 文件整理工具，支持图形界面和命令行两种操作方式。主要功能包括 ID3 标签读写、MusicBrainz 网络搜索和 AcoustID 音频指纹识别。

## 快速开始

### 依赖安装

```bash
pip install -r requirements.txt
```

### 运行方式

#### 图形界面（推荐）
```bash
python gui_main.py
```

#### 命令行工具

| 工具 | 用途 | 示例 |
|------|------|------|
| `mb_search.py` | MusicBrainz 网络搜索缺失标签 | `python mb_search.py "D:\Music" --dry-run --recursive` |
| `id3_cli.py` | 仅基于现有 ID3 标签重命名 | `python id3_cli.py "D:\Music" --recursive` |
| `full_tagger.py` | 音频指纹识别（需 fpc.exe） | `python full_tagger.py "D:\Music" --recursive` |

### 常用命令行选项

| 选项 | 说明 |
|------|------|
| `--pattern`, `-p` | 命名格式（默认：`{artist} - {title}`） |
| `--dry-run`, `-n` | 预览模式，不实际修改 |
| `--recursive`, `-r` | 递归扫描子文件夹 |
| `--backup`, `-b` | 重命名前备份原文件 |
| `--force-search`, `-f` | 强制所有文件联网搜索 |

## 代码架构

### 核心模块

1. **`gui_main.py`** - 基于 Tkinter 的图形界面，支持预览和批量处理
2. **`mb_search.py`** - MusicBrainz API 集成，用于标签检索和文件重命名
3. **`id3_cli.py`** - 轻量级 ID3 标签读写工具，用于重命名操作
4. **`full_tagger.py`** - AcoustID 音频指纹识别（需 fpc.exe）

### 主要特性

- **预览功能**：`--dry-run` 选项先查看再执行
- **编码修复**：自动处理 GBK/Big5 编码的标签乱码
- **网络优化**：仅在标签缺失或不完整时才会联网搜索
- **自定义命名**：支持 `{artist}`, `{title}`, `{album}`, `{year}` 占位符
- **备份选项**：重命名前可选择备份原文件

### 配置文件

API 密钥和设置存储在 `config.json` 中：
```json
{
  "acoustid_api_key": "PRDC1WrVaQ",
  "rename_pattern": "{artist} - {title}",
  "save_tags": true,
  "backup_original": false,
  "recursive_scan": true
}
```

### 依赖库

- `mutagen`：ID3 标签操作
- `musicbrainzngs`：MusicBrainz API 集成
- `pyacoustid`：AcoustID 音频指纹识别
- `tkinter`：图形界面（Python 标准库）
