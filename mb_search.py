#!/usr/bin/env python3
"""
MP3 Tagger - MusicBrainz 搜索版本
通过文件名搜索 MusicBrainz 获取标签信息，不需要 fpc.exe
"""

import os
import sys
import io
import argparse
import json
import re
from pathlib import Path

# Windows 控制台编码修复
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    os.system('chcp 65001 >nul')

import musicbrainzngs
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC
from mutagen.mp3 import MP3

# MusicBrainz 用户代理
musicbrainzngs.set_useragent("MP3Tagger", "1.0")

# 配置
CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config():
    """加载配置"""
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        return config.get('acoustid_api_key', '')
    return ''


def clean_filename(name):
    """清理文件名中的无效字符"""
    if not name:
        return ""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip().strip('.')


def extract_search_terms(mp3_path):
    """从文件名提取搜索关键词"""
    name = mp3_path.stem

    # 尝试分离艺术家和标题
    # 模式：艺术家 - 标题
    if ' - ' in name:
        parts = name.split(' - ', 1)
        return {'artist': parts[0].strip(), 'title': parts[1].strip()}
    if '-' in name:
        parts = name.split('-', 1)
        if len(parts) == 2:
            return {'artist': parts[0].strip(), 'title': parts[1].strip()}

    # 否则整个文件名作为标题搜索
    return {'title': name}


def search_musicbrainz(query, artist=None):
    """搜索 MusicBrainz"""
    try:
        # 清理查询字符串
        query = re.sub(r'[^\w\s\u4e00-\u9fff\-]', ' ', query)
        query = ' '.join(query.split())  # 去除多余空格

        if artist:
            artist = re.sub(r'[^\w\s\u4e00-\u9fff\-]', ' ', artist)
            artist = ' '.join(artist.split())

        # 构建搜索查询
        if artist:
            search_query = f'recording:"{query}" AND artist:"{artist}"'
        else:
            search_query = f'recording:"{query}"'

        result = musicbrainzngs.search_recordings(query=search_query, limit=5)

        if not result.get('recording-list'):
            # 尝试只搜索标题
            if artist:
                result = musicbrainzngs.search_recordings(query=query, limit=5)

        if not result.get('recording-list'):
            return None

        # 返回最佳匹配
        recording = result['recording-list'][0]

        # 提取艺术家
        artist_name = ""
        if 'artist-credit' in recording:
            ac = recording['artist-credit']
            if isinstance(ac, list) and len(ac) > 0:
                artist_name = ac[0].get('artist', {}).get('name', '')
            elif isinstance(ac, dict):
                artist_name = ac.get('name', '')

        # 提取标题
        title = recording.get('title', '')

        # 提取专辑
        album = ""
        if 'release-list' in recording and recording['release-list']:
            album = recording['release-list'][0].get('title', '')

        # 提取年份
        year = ""
        if 'release-list' in recording and recording['release-list']:
            release = recording['release-list'][0]
            if 'date' in release:
                year = release['date'][:4]

        if not title:
            return None

        return {
            'artist': clean_filename(artist_name),
            'title': clean_filename(title),
            'album': clean_filename(album),
            'year': year
        }

    except Exception as e:
        print(f"  搜索失败：{e}")
        return None


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

        result = {}
        if clean_filename(artist):
            result['artist'] = clean_filename(artist)
        if clean_filename(title):
            result['title'] = clean_filename(title)
        if clean_filename(album):
            result['album'] = clean_filename(album)
        if year:
            result['year'] = str(year)[:4]

        return result if result else None

    except Exception as e:
        print(f"  读取标签失败：{e}")
        return None


def update_tags(mp3_path, metadata):
    """更新 ID3 标签"""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        tags['TIT2'] = TIT2(encoding=3, text=metadata['title'])

        if metadata.get('artist'):
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


def process_file(mp3_path, pattern, backup, dry_run, force_search=False):
    """处理单个文件"""
    old_name = mp3_path.name

    # 读取现有 ID3 标签
    tags = read_id3_tags(mp3_path)

    need_search = force_search
    source = "ID3"

    # 只有在没有 ID3 或标签不完整时才联网搜索
    if not tags:
        need_search = True
        source = "无 ID3"
    elif not tags.get('artist') or not tags.get('title'):
        need_search = True
        source = "ID3 不完整"

    if need_search:
        # 从文件名提取搜索词
        search_terms = extract_search_terms(mp3_path)
        print(f"  [联网] {source}: {search_terms.get('title', 'unknown')}")

        tags = search_musicbrainz(
            search_terms.get('title', ''),
            search_terms.get('artist', '')
        )

        if not tags:
            print(f"  [失败] 未找到匹配结果")
            # 如果搜索失败，但有部分 ID3 信息，使用 ID3
            id3_tags = read_id3_tags(mp3_path)
            if id3_tags:
                tags = id3_tags
                source = "ID3(部分)"
            else:
                return 'skipped'
        else:
            print(f"  [成功] {tags['artist']} - {tags['title']}")
            source = "MusicBrainz"

    if not tags or not tags.get('title'):
        print(f"  [跳过] 无法获取歌曲信息")
        return 'skipped'

    # 如果没有艺术家，使用"未知艺术家"
    if not tags.get('artist'):
        tags['artist'] = '未知艺术家'

    # 检查文件名格式是否已经正确
    expected_name = pattern.format(**tags) + '.mp3'
    if new_name_matches_pattern(old_name, expected_name):
        print(f"  [{source}] {tags['artist']} - {tags['title']} ✓")
        return 'skipped'

    # 显示修改信息
    if dry_run:
        print(f"  [{source}] {tags['artist']} - {tags['title']}")
        print(f"  [预览] {old_name}")
        print(f"       → {expected_name}")
        return 'preview'
    else:
        print(f"  [{source}] {tags['artist']} - {tags['title']}")
        print(f"  {old_name}")
        print(f"    → {expected_name}")

    if dry_run:
        return 'preview'

    # 更新标签并重命名
    try:
        new_path = mp3_path.with_name(expected_name)

        if new_path.exists():
            if backup:
                backup_path = mp3_path.with_suffix('.mp3.bak')
                mp3_path.rename(backup_path)
                print(f"    [备份] {backup_path.name}")
            else:
                base = expected_name.rsplit('.', 1)[0]
                new_path = mp3_path.with_name(f"{base}_dup.mp3")
                print(f"    [重名] {new_path.name}")

        update_tags(mp3_path, tags)
        mp3_path.rename(new_path)

        print(f"    [成功]")
        return 'success'

    except Exception as e:
        print(f"    [失败] {e}")
        return 'failed'


def new_name_matches_pattern(actual_name, expected_name):
    """检查文件名是否已经符合格式（允许小的差异）"""
    actual_base = actual_name.rsplit('.', 1)[0] if '.' in actual_name else actual_name
    expected_base = expected_name.rsplit('.', 1)[0] if '.' in expected_name else expected_name
    return actual_base == expected_base


def main():
    parser = argparse.ArgumentParser(
        description='MP3 Tagger - MusicBrainz 搜索版本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python mb_search.py /path/to/music
  python mb_search.py /path/to/music --dry-run
  python mb_search.py /path/to/music --force-search  # 强制搜索所有文件
        """
    )

    parser.add_argument('folder', help='音乐文件夹路径')
    parser.add_argument('--pattern', '-p', default='{artist} - {title}',
                        help='命名格式 (默认：{artist} - {title})')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='仅预览，不实际重命名')
    parser.add_argument('--recursive', '-r', action='store_true', default=True,
                        help='递归扫描子文件夹')
    parser.add_argument('--backup', '-b', action='store_true',
                        help='重命名前备份原文件')
    parser.add_argument('--force-search', '-f', action='store_true',
                        help='强制联网搜索所有文件')
    parser.add_argument('--max-files', '-m', type=int,
                        help='最大处理文件数')
    parser.add_argument('--no-confirm', '-y', action='store_true',
                        help='预览后不询问，直接执行')

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
    print("=" * 70)

    if args.max_files:
        mp3_files = mp3_files[:args.max_files]

    # 统计
    stats = {'success': 0, 'failed': 0, 'skipped': 0, 'preview': 0}
    preview_list = []  # 记录预览中需要修改的文件

    # 处理文件
    for i, mp3_path in enumerate(mp3_files, 1):
        print(f"\n[{i}/{len(mp3_files)}] {mp3_path.name}")
        result = process_file(mp3_path, args.pattern, args.backup, args.dry_run, args.force_search)
        stats[result] += 1
        if result == 'preview':
            preview_list.append(mp3_path.name)

    # 汇总
    print("\n" + "=" * 70)
    print("完成!")
    print(f"  无需修改：{stats['skipped']}")

    if args.dry_run:
        print(f"  待修改：{stats['preview']}")
        print(f"  失败：{stats['failed']}")

        if preview_list:
            print("\n" + "=" * 70)
            print("以下文件将被修改:")
            for name in preview_list[:20]:  # 只显示前 20 个
                print(f"  • {name}")
            if len(preview_list) > 20:
                print(f"  ... 还有 {len(preview_list) - 20} 个文件")

            # 询问是否执行
            if not args.no_confirm:
                print("\n" + "-" * 70)
                confirm = input("是否执行实际重命名？(y/n): ")
                if confirm.lower() == 'y':
                    print("\n开始执行...\n")
                    print("=" * 70)
                    # 重新执行，这次实际修改
                    args.dry_run = False
                    stats2 = {'success': 0, 'failed': 0, 'skipped': 0, 'preview': 0}
                    for i, mp3_path in enumerate(mp3_files, 1):
                        # 跳过不需要修改的文件
                        print(f"\n[{i}/{len(mp3_files)}] {mp3_path.name}")
                        result = process_file(mp3_path, args.pattern, args.backup, False, args.force_search)
                        stats2[result] += 1
                    print("\n" + "=" * 70)
                    print("执行完成!")
                    print(f"  成功：{stats2['success']}")
                    print(f"  失败：{stats2['failed']}")
                    print(f"  跳过：{stats2['skipped']}")
                else:
                    print("\n已取消操作")
        else:
            print("\n没有需要修改的文件")
    else:
        print(f"  成功：{stats['success']}")
        print(f"  失败：{stats['failed']}")


if __name__ == "__main__":
    main()
