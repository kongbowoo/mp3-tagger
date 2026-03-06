#!/usr/bin/env python3
"""
MP3 Tagger - ID3 标签重命名（命令行版本）
"""

import os
import sys
import argparse
import io
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC
from mutagen.mp3 import MP3

# Windows 控制台编码修复
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    # 设置控制台为 UTF-8 模式
    os.system('chcp 65001 >nul')


def read_id3_tags(mp3_path):
    """读取 ID3 标签"""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        tags = audio.tags

        if tags is None:
            return None

        def get_text(tag_name):
            tag = tags.get(tag_name)
            if not tag or not tag.text:
                return ""

            text = tag.text[0]

            # 如果是字符串，检查是否包含乱码（常见 Big5/GBK 误读为 Latin-1）
            if isinstance(text, str):
                # 检查是否需要重新解码
                # 如果包含 Õ,Ó,Â 等字符 (0x80-0xFF 范围),很可能是 Big5/GBK 被误读为 Latin-1
                if any(ord(c) > 127 and ord(c) < 256 for c in text):
                    try:
                        latin_bytes = text.encode('latin-1')
                        # 优先试 GBK（简体），因为大部分中文音乐是简体
                        try:
                            result = latin_bytes.decode('gbk')
                            # 验证：如果结果包含常见中文字符，很可能是正确的
                            if any('\u4e00' <= c <= '\u9fff' for c in result):
                                return result
                        except:
                            pass
                        # 再试 Big5（繁体）
                        try:
                            result = latin_bytes.decode('big5')
                            if any('\u4e00' <= c <= '\u9fff' for c in result):
                                return result
                        except:
                            pass
                    except:
                        pass
                return text

            # 如果是字节
            if isinstance(text, bytes):
                for enc in ['utf-8', 'gbk', 'big5', 'latin-1']:
                    try:
                        return text.decode(enc)
                    except:
                        continue
                return text.decode('utf-8', errors='replace')

            return str(text)

        artist = get_text('TPE1')
        title = get_text('TIT2')
        album = get_text('TALB')
        year = get_text('TDRC')

        # 清理
        artist = clean_filename(artist)
        title = clean_filename(title)
        album = clean_filename(album)
        year = str(year)[:4] if year else ""

        return {
            'artist': artist,
            'title': title,
            'album': album,
            'year': year
        }

    except Exception as e:
        print(f"  读取标签失败：{e}")
        return None


def clean_filename(name):
    """清理文件名中的无效字符"""
    if not name:
        return ""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip().strip('.')


def parse_filename(mp3_path):
    """从文件名解析艺术家和标题"""
    name = mp3_path.stem  # 不含扩展名的文件名

    # 清理
    name = name.strip()
    if not name:
        return None

    # 模式 1: 艺术家 - 标题 (包含分隔符 -)
    if ' - ' in name:
        parts = name.split(' - ', 1)
        return {'artist': parts[0].strip(), 'title': parts[1].strip()}

    # 模式 2: 艺术家 - 标题 (分隔符 - 无空格)
    if '-' in name:
        parts = name.split('-', 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return {'artist': parts[0].strip(), 'title': parts[1].strip()}

    # 模式 3: 艺术家&歌手 - 标题 (多个艺术家)
    if '&' in name:
        parts = name.split('&', 1)
        if len(parts) == 2:
            # 检查第二部分是否包含 -
            if '-' in parts[1]:
                sub_parts = parts[1].split('-', 1)
                artist = f"{parts[0]}&{sub_parts[0].strip()}"
                title = sub_parts[1].strip() if len(sub_parts) > 1 else ""
                if artist and title:
                    return {'artist': artist, 'title': title}

    # 模式 4: 纯标题（无艺术家信息）
    # 如果文件名看起来像纯标题，使用"未知艺术家"
    if len(name) > 2:
        return {'artist': '未知艺术家', 'title': name}

    return None


def generate_new_name(tags, pattern):
    """生成新文件名"""
    if not tags or not tags.get('artist') or not tags.get('title'):
        return None

    try:
        new_name = pattern.format(**tags) + '.mp3'
        new_name = clean_filename(new_name)
        return new_name
    except KeyError as e:
        print(f"  格式错误：{e}")
        return None


def process_file(mp3_path, pattern, backup, dry_run):
    """处理单个文件"""
    old_name = mp3_path.name
    tags = read_id3_tags(mp3_path)

    if tags and tags.get('artist') and tags.get('title'):
        print(f"  [ID3 标签] {tags['artist']} - {tags['title']}")
    else:
        # ID3 标签不完整，需要联网查询（需要安装 fpc.exe）
        print(f"  [需要联网查询] ID3 标签不完整")
        print(f"  提示：安装 fpc.exe 后可通过音频指纹联网查询标签")
        return 'skipped'

    new_name = generate_new_name(tags, pattern)

    if not new_name:
        print(f"  [失败] 无法生成文件名")
        return 'failed'

    if new_name == old_name:
        print(f"  [无需更改]")
        return 'skipped'

    print(f"  {old_name}")
    print(f"    → {new_name}")

    if dry_run:
        return 'preview'

    try:
        new_path = mp3_path.with_name(new_name)

        if new_path.exists():
            if backup:
                backup_path = mp3_path.with_suffix('.mp3.bak')
                mp3_path.rename(backup_path)
                print(f"    [备份] {backup_path.name}")
            else:
                base = new_name.rsplit('.', 1)[0]
                new_path = mp3_path.with_name(f"{base}_dup.mp3")
                print(f"    [重名] {new_path.name}")

        mp3_path.rename(new_path)
        print(f"    [成功]")
        return 'success'

    except Exception as e:
        print(f"    [失败] {e}")
        return 'failed'


def main():
    parser = argparse.ArgumentParser(
        description='MP3 ID3 标签重命名工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python id3_renamer.py /path/to/music
  python id3_renamer.py /path/to/music --pattern "{artist} - {title}"
  python id3_renamer.py /path/to/music --dry-run
  python id3_renamer.py /path/to/music --recursive
        """
    )

    parser.add_argument('folder', help='音乐文件夹路径')
    parser.add_argument('--pattern', '-p', default='{artist} - {title}',
                        help='命名格式 (默认：{artist} - {title})')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='仅预览，不实际重命名')
    parser.add_argument('--recursive', '-r', action='store_true',
                        help='递归扫描子文件夹')
    parser.add_argument('--backup', '-b', action='store_true',
                        help='重命名前备份原文件')
    parser.add_argument('--max-files', '-m', type=int,
                        help='最大处理文件数')

    args = parser.parse_args()

    # 检查文件夹
    folder = Path(args.folder)
    if not folder.exists():
        print(f"错误：文件夹不存在：{folder}")
        sys.exit(1)

    # 查找 MP3 文件
    pattern = '**/*.mp3' if args.recursive else '*.mp3'
    mp3_files = list(folder.glob(pattern))

    if not mp3_files:
        print("未找到 MP3 文件")
        sys.exit(0)

    print(f"找到 {len(mp3_files)} 个 MP3 文件")
    print(f"命名格式：{args.pattern}")
    if args.dry_run:
        print("[预览模式 - 不会修改任何文件]\n")
    print("=" * 60)

    if args.max_files:
        mp3_files = mp3_files[:args.max_files]

    # 统计
    stats = {'success': 0, 'failed': 0, 'skipped': 0, 'preview': 0}

    # 处理文件
    for i, mp3_path in enumerate(mp3_files, 1):
        print(f"\n[{i}/{len(mp3_files)}] {mp3_path.name}")
        result = process_file(mp3_path, args.pattern, args.backup, args.dry_run)
        stats[result] += 1

    # 汇总
    print("\n" + "=" * 60)
    print("完成!")
    print(f"  成功：{stats['success']}")
    print(f"  失败：{stats['failed']}")
    print(f"  跳过：{stats['skipped']}")

    if args.dry_run:
        print(f"  预览：{stats['preview']}")
        print("\n确认无误后，去掉 --dry-run 参数执行实际重命名")


if __name__ == "__main__":
    main()
