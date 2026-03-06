# MP3 Tagger - MP3 标签整理工具

自动整理 MP3 文件，重命名为「艺术家 - 标题」格式。

## 快速开始

### 图形界面（推荐）

```bash
python gui_main.py
```

### 命令行

```bash
# 预览
python mb_search.py "D:\Music" --dry-run --recursive

# 执行
python mb_search.py "D:\Music" --recursive
```

## 功能特点

- ✅ **预览功能**：先查看再执行，避免误操作
- ✅ **智能联网**：仅缺失标签时查询 MusicBrainz
- ✅ **编码修复**：自动处理 GBK/Big5 乱码
- ✅ **批量处理**：支持递归扫描子文件夹
- ✅ **备份选项**：重命名前可选备份

## 工具说明

| 工具 | 说明 |
|------|------|
| `gui_main.py` | 图形界面（推荐） |
| `mb_search.py` | 命令行（MusicBrainz 搜索） |
| `id3_cli.py` | 命令行（仅 ID3 重命名） |
| `full_tagger.py` | 命令行（音频指纹，需要 fpc.exe） |

## 命令行选项

| 选项 | 说明 |
|------|------|
| `--pattern`, `-p` | 命名格式 (默认：`{artist} - {title}`) |
| `--dry-run`, `-n` | 仅预览，不修改 |
| `--recursive`, `-r` | 递归子文件夹 |
| `--backup`, `-b` | 备份原文件 |
| `--force-search`, `-f` | 强制所有文件联网 |
| `-y` | 预览后直接执行 |

## 配置

API Key 保存在 `config.json`，无需手动修改。

## 使用示例

```bash
# 图形界面
python gui_main.py

# 预览
python mb_search.py "D:\Music" --dry-run --recursive

# 预览后直接执行
python mb_search.py "D:\Music" --recursive -y
```
