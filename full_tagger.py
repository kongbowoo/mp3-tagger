#!/usr/bin/env python3
"""
MP3 Tagger - 完整版本（音频指纹 + ID3）
需要安装 fpc.exe 和 AcoustID API Key
"""

import os
import sys
import io
import argparse
import json
from pathlib import Path

# Windows 控制台编码修复
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    os.system('chcp 65001 >nul')

import acoustid
import musicbrainzngs
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC
from mutagen.mp3 import MP3

# MusicBrainz 用户代理
musicbrainzngs.set_useragent("MP3Tagger", "1.0")

# 配置
ACOUSTID_API_KEY = ""
CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config():
    """加载配置"""
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        return config.get('acoustid_api_key', '')

    # 检查 acoustid_key.txt
    key_file = Path(__file__).parent / "acoustid_key.txt"
    if key_file.exists():
        return key_file.read_text().strip()

    return ''


def clean_filename(name):
    """清理文件名中的无效字符"""
    if not name:
        return ""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip().strip('.')


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
            if isinstance(text, str):
                # 检查是否包含乱码（GBK/Big5 误读为 Latin-1）
                if any(ord(c) > 127 and ord(c) < 256 for c in text):
                    try:
                        latin_bytes = text.encode('latin-1')
                        for enc in ['gbk', 'big5']:
                            try:
                                result = latin_bytes.decode(enc)
                                if any('\u4e00' <= c <= '\u9fff' for c in result):
                                    return result
                            except:
                                pass
                    except:
                        pass
                return text
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
        genre = get_text('TCON')

        result = {}
        if clean_filename(artist):
            result['artist'] = clean_filename(artist)
        if clean_filename(title):
            result['title'] = clean_filename(title)
        if clean_filename(album):
            result['album'] = clean_filename(album)
        if year:
            result['year'] = str(year)[:4]
        if genre:
            result['genre'] = clean_filename(genre)

        return result if result else None

    except Exception as e:
        print(f"  读取标签失败：{e}")
        return None


def fingerprint_search(api_key, mp3_path):
    """通过音频指纹搜索元数据"""
    try:
        matches, fingerprint, duration = acoustid.match(
            api_key,
            str(mp3_path),
            meta='recordings+releasegroups'
        )

        if not matches:
            return None

        best_match = matches[0]
        if 'recordings' not in best_match:
            return None

        recording = best_match['recordings'][0]

        # 提取艺术家
        artist = ""
        if 'artists' in recording and recording['artists']:
            artist = recording['artists'][0].get('name', '')

        # 提取标题
        title = recording.get('title', '')

        # 提取专辑
        album = ""
        year = ""
        if 'releases' in recording and recording['releases']:
            release = recording['releases'][0]
            album = release.get('title', '')
            if 'date' in release:
                year = release['date'][:4]

        # 清理
        artist = clean_filename(artist)
        title = clean_filename(title)
        album = clean_filename(album)

        if not artist or not title:
            return None

        return {
            'artist': artist,
            'title': title,
            'album': album,
            'year': year
        }

    except acoustid.NoBackendError:
        raise Exception("未找到 fpc.exe (Chromaprint)，请安装后再试")
    except acoustid.FingerprintGenerationError:
        raise Exception("无法生成音频指纹")
    except acoustid.WebServiceError as e:
        raise Exception(f"网络请求失败：{e}")
    except Exception as e:
        print(f"  指纹查询失败：{e}")
        return None


def update_tags(mp3_path, metadata):
    """更新 ID3 标签"""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        tags['TIT2'] = TIT2(encoding=3, text=metadata['title'])
        tags['TPE1'] = TPE1(encoding=3, text=metadata['artist'])

        if metadata.get('album'):
            tags['TALB'] = TALB(encoding=3, text=metadata['album'])
        if metadata.get('year'):
            tags['TDRC'] = TDRC(encoding=3, text=metadata['year'])

        audio.save()
        return True
    except Exception as e:
        print(f"  标签更新失败：{e}")
        return False


def process_file(mp3_path, api_key, pattern, backup, dry_run, force_search=False):
    """处理单个文件"""
    old_name = mp3_path.name

    # 读取现有 ID3 标签
    tags = read_id3_tags(mp3_path)

    need_search = force_search
    source = "ID3 标签"

    if not tags or (not tags.get('artist') and not tags.get('title')):
        need_search = True
        source = "需要查询"
    elif not tags.get('artist') or not tags.get('title'):
        # 标签不完整，需要查询
        need_search = True
        source = "标签不完整"

    if need_search:
        if not api_key:
            print(f"  [跳过] {source} - 需要 AcoustID API Key")
            return 'skipped'

        print(f"  [联网查询] {source}")
        tags = fingerprint_search(api_key, mp3_path)
        if not tags:
            print(f"  [失败] 未找到匹配结果")
            return 'failed'
        print(f"  [成功] {tags['artist']} - {tags['title']}")

    print(f"  [{source}] {tags['artist']} - {tags['title']}")

    # 生成新文件名
    try:
        new_name = pattern.format(**tags) + '.mp3'
        new_name = clean_filename(new_name)
    except KeyError as e:
        print(f"  [失败] 格式错误：{e}")
        return 'failed'

    if new_name == old_name:
        print(f"  [无需更改]")
        return 'skipped'

    print(f"  {old_name}")
    print(f"    → {new_name}")

    if dry_run:
        return 'preview'

    # 执行重命名
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

        # 更新标签并重命名
        if not dry_run:
            update_tags(mp3_path, tags)
            mp3_path.rename(new_path)

        print(f"    [成功]")
        return 'success'

    except Exception as e:
        print(f"    [失败] {e}")
        return 'failed'


def main():
    parser = argparse.ArgumentParser(
        description='MP3 Tagger - 音频指纹标签整理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python full_tagger.py /path/to/music
  python full_tagger.py /path/to/music --api-key YOUR_KEY
  python full_tagger.py /path/to/music --dry-run
  python full_tagger.py /path/to/music --force-search  # 强制联网查询所有文件
        """
    )

    parser.add_argument('folder', help='音乐文件夹路径')
    parser.add_argument('--api-key', '-k', help='AcoustID API Key')
    parser.add_argument('--pattern', '-p', default='{artist} - {title}',
                        help='命名格式 (默认：{artist} - {title})')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='仅预览，不实际重命名')
    parser.add_argument('--recursive', '-r', action='store_true', default=True,
                        help='递归扫描子文件夹')
    parser.add_argument('--backup', '-b', action='store_true',
                        help='重命名前备份原文件')
    parser.add_argument('--force-search', '-f', action='store_true',
                        help='强制联网查询所有文件（即使已有 ID3 标签）')
    parser.add_argument('--max-files', '-m', type=int,
                        help='最大处理文件数')

    args = parser.parse_args()

    # 获取 API Key
    api_key = args.api_key or load_config()

    if not api_key:
        print("错误：需要 AcoustID API Key")
        print("  1. 使用 --api-key 参数")
        print("  2. 或在 config.json 中配置 acoustid_api_key")
        print("  3. 或创建 acoustid_key.txt 文件")
        print("\n获取免费 API Key: https://acoustid.org/api-key")
        sys.exit(1)

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
    else:
        print(f"API Key: {api_key[:8]}...{api_key[-4:]}\n")
    print("=" * 60)

    if args.max_files:
        mp3_files = mp3_files[:args.max_files]

    # 统计
    stats = {'success': 0, 'failed': 0, 'skipped': 0, 'preview': 0}

    # 处理文件
    for i, mp3_path in enumerate(mp3_files, 1):
        print(f"\n[{i}/{len(mp3_files)}] {mp3_path.name}")
        result = process_file(mp3_path, api_key, args.pattern, args.backup, args.dry_run, args.force_search)
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
