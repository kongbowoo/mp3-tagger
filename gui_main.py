#!/usr/bin/env python3
"""
MP3 Tagger - 完整版（支持预览 + MusicBrainz 搜索）
"""

import os
import sys
import io
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from threading import Thread
import musicbrainzngs
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC
from mutagen.mp3 import MP3

# Windows 控制台编码修复
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# MusicBrainz 用户代理
musicbrainzngs.set_useragent("MP3Tagger", "1.0")

# 配置文件
CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config():
    """加载配置"""
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        return config.get('acoustid_api_key', '')
    return ''


class MP3TaggerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 Tagger - 音乐标签整理工具")
        self.root.geometry("1000x700")

        # 配置
        self.folder_path = tk.StringVar()
        self.processing = False
        self.rename_pattern = "{artist} - {title}"
        self.use_network = tk.BooleanVar(value=True)  # 是否启用联网搜索

        # 统计
        self.stats = {'skipped': 0, 'preview': 0, 'success': 0, 'failed': 0, 'network': 0}
        self.preview_files = []

        # 创建 UI
        self._create_ui()

    def _create_ui(self):
        """创建用户界面"""
        # === 顶部框架 - 文件夹选择 ===
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="音乐文件夹:").pack(side=tk.LEFT)
        self.folder_entry = ttk.Entry(top_frame, textvariable=self.folder_path, width=60)
        self.folder_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="浏览...", command=self._select_folder).pack(side=tk.LEFT)

        # === 第二行 - 命名格式和选项 ===
        format_frame = ttk.Frame(self.root, padding="10")
        format_frame.pack(fill=tk.X)

        ttk.Label(format_frame, text="命名格式:").pack(side=tk.LEFT)
        self.pattern_entry = ttk.Entry(format_frame, width=40)
        self.pattern_entry.insert(0, self.rename_pattern)
        self.pattern_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(format_frame, text="可用：{artist}, {title}, {album}, {year}").pack(side=tk.LEFT)

        # === 选项框架 ===
        option_frame = ttk.LabelFrame(self.root, text="选项", padding="10")
        option_frame.pack(fill=tk.X, padx=10, pady=5)

        self.subfolder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(option_frame, text="包含子文件夹", variable=self.subfolder_var).pack(side=tk.LEFT, padx=5)

        self.backup_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(option_frame, text="备份原文件", variable=self.backup_var).pack(side=tk.LEFT, padx=5)

        ttk.Checkbutton(option_frame, text="启用联网搜索（仅缺失标签时）", variable=self.use_network).pack(side=tk.LEFT, padx=5)

        # === 控制按钮 ===
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)

        self.preview_btn = ttk.Button(control_frame, text="预览", command=self._start_preview)
        self.preview_btn.pack(side=tk.LEFT)

        self.start_btn = ttk.Button(control_frame, text="开始处理", command=self._start_process)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="停止", command=self._stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # === 进度条 ===
        self.progress_frame = ttk.Frame(self.root, padding="10")
        self.progress_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X)
        self.status_label = ttk.Label(self.progress_frame, text="就绪")
        self.status_label.pack()

        # === 结果列表 ===
        list_frame = ttk.Frame(self.root, padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('source', 'old_name', 'new_name', 'artist', 'title', 'status')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        self.tree.heading('source', text='来源')
        self.tree.heading('old_name', text='原文件名')
        self.tree.heading('new_name', text='新文件名')
        self.tree.heading('artist', text='艺术家')
        self.tree.heading('title', text='标题')
        self.tree.heading('status', text='状态')

        self.tree.column('source', width=80)
        self.tree.column('old_name', width=180)
        self.tree.column('new_name', width=180)
        self.tree.column('artist', width=100)
        self.tree.column('title', width=150)
        self.tree.column('status', width=70)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # === 日志区域 ===
        log_frame = ttk.LabelFrame(self.root, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, height=5, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # === 统计信息 ===
        self.stats_label = ttk.Label(self.root, text="", font=('Arial', 10))
        self.stats_label.pack()

        # === 预览确认框架（预览后显示）===
        self.confirm_frame = ttk.Frame(self.root, padding="10")
        # 初始隐藏

    def _select_folder(self):
        """选择文件夹"""
        folder = filedialog.askdirectory(title="选择音乐文件夹")
        if folder:
            self.folder_path.set(folder)
            self._log(f"已选择文件夹：{folder}")

    def _log(self, message):
        """添加日志"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def _clear_tree(self):
        """清空列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.preview_files = []
        self.stats = {'skipped': 0, 'preview': 0, 'success': 0, 'failed': 0, 'network': 0}

    def _add_to_tree(self, source, old_name, new_name, artist, title, status):
        """添加到结果列表"""
        self.tree.insert('', tk.END, values=(source, old_name, new_name, artist, title, status))

    def _update_stats(self):
        """更新统计信息"""
        text = f"统计：无需修改={self.stats['skipped']}, 待修改={self.stats['preview']}, 成功={self.stats['success']}, 失败={self.stats['failed']}, 联网查询={self.stats['network']}"
        self.stats_label.configure(text=text)

    def _clean_filename(self, name):
        """清理文件名"""
        if not name:
            return ""
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip().strip('.')

    def _read_id3_tags(self, mp3_path):
        """读取 ID3 标签（支持编码修复）"""
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
            if self._clean_filename(artist):
                result['artist'] = self._clean_filename(artist)
            if self._clean_filename(title):
                result['title'] = self._clean_filename(title)
            if self._clean_filename(album):
                result['album'] = self._clean_filename(album)
            if year:
                result['year'] = str(year)[:4]

            return result if result else None
        except Exception as e:
            return None

    def _extract_search_terms(self, mp3_path):
        """从文件名提取搜索词"""
        name = mp3_path.stem
        if ' - ' in name:
            parts = name.split(' - ', 1)
            return {'artist': parts[0].strip(), 'title': parts[1].strip()}
        if '-' in name:
            parts = name.split('-', 1)
            if len(parts) == 2:
                return {'artist': parts[0].strip(), 'title': parts[1].strip()}
        return {'title': name}

    def _search_musicbrainz(self, query, artist=None):
        """搜索 MusicBrainz"""
        try:
            query = re.sub(r'[^\w\s\u4e00-\u9fff\-]', ' ', query)
            query = ' '.join(query.split())
            if artist:
                artist = re.sub(r'[^\w\s\u4e00-\u9fff\-]', ' ', artist)
                artist = ' '.join(artist.split())
                search_query = f'recording:"{query}" AND artist:"{artist}"'
            else:
                search_query = f'recording:"{query}"'

            result = musicbrainzngs.search_recordings(query=search_query, limit=5)
            if not result.get('recording-list'):
                if artist:
                    result = musicbrainzngs.search_recordings(query=query, limit=5)

            if not result.get('recording-list'):
                return None

            recording = result['recording-list'][0]
            artist_name = ""
            if 'artist-credit' in recording:
                ac = recording['artist-credit']
                if isinstance(ac, list) and len(ac) > 0:
                    artist_name = ac[0].get('artist', {}).get('name', '')
                elif isinstance(ac, dict):
                    artist_name = ac.get('name', '')

            title = recording.get('title', '')
            album = ""
            year = ""
            if 'release-list' in recording and recording['release-list']:
                release = recording['release-list'][0]
                album = release.get('title', '')
                if 'date' in release:
                    year = release['date'][:4]

            if not title:
                return None

            return {
                'artist': self._clean_filename(artist_name),
                'title': self._clean_filename(title),
                'album': self._clean_filename(album),
                'year': year
            }
        except Exception as e:
            self._log(f"  搜索失败：{e}")
            return None

    def _start_preview(self):
        """开始预览"""
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("错误", "请选择有效的音乐文件夹")
            return

        self._clear_tree()
        self._log("=" * 70)
        self._log("开始预览...")
        self._process_files(folder, preview_only=True)

    def _start_process(self):
        """开始处理"""
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("错误", "请选择有效的音乐文件夹")
            return

        # 如果启用预览且还未预览
        if not self.preview_files and self.stats['preview'] == 0 and self.stats['success'] == 0:
            self._log("请先点击'预览'按钮查看将要修改的文件")
            self._start_preview()
            return

        # 如果有待修改文件，询问确认
        if self.stats['preview'] > 0:
            result = messagebox.askyesno(
                "确认",
                f"找到 {self.stats['preview']} 个文件需要修改\n\n"
                f"无需修改：{self.stats['skipped']}\n"
                f"待修改：{self.stats['preview']}\n"
                f"失败：{self.stats['failed']}\n"
                f"联网查询：{self.stats['network']}\n\n"
                f"是否开始处理？"
            )
            if not result:
                return

        self._clear_tree()
        self._log("=" * 70)
        self._log("开始处理...")
        self._process_files(folder, preview_only=False)

    def _process_files(self, folder, preview_only=True):
        """处理文件（在后台线程中）"""
        self.processing = True
        self.preview_btn.configure(state=tk.DISABLED)
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        # 获取文件列表
        if self.subfolder_var.get():
            mp3_files = list(Path(folder).rglob("*.mp3"))
        else:
            mp3_files = list(Path(folder).glob("*.mp3"))

        if not mp3_files:
            self.root.after(0, lambda: messagebox.showinfo("提示", "未找到 MP3 文件"))
            self._finish_processing()
            return

        self.root.after(0, lambda: self.progress.configure(maximum=len(mp3_files)))

        processed = 0
        for mp3_path in mp3_files:
            if not self.processing:
                break
            self._process_single_file(mp3_path, preview_only)
            processed += 1
            self.root.after(0, lambda p=processed: self.progress.configure(value=p))
            self.root.after(0, self._update_stats)

        self._log("处理完成!")
        self._update_stats()

        if preview_only:
            self._show_confirm()

        self._finish_processing()

    def _process_single_file(self, mp3_path, preview_only):
        """处理单个文件"""
        old_name = mp3_path.name
        tags = self._read_id3_tags(mp3_path)

        need_search = False
        source = "ID3"

        # 检查是否需要联网搜索
        if not tags:
            need_search = True
            source = "无 ID3"
        elif not tags.get('artist') or not tags.get('title'):
            need_search = True
            source = "ID3 不完整"

        # 联网搜索
        if need_search and self.use_network.get():
            search_terms = self._extract_search_terms(mp3_path)
            self._log(f"  [联网] {source}: {search_terms.get('title', 'unknown')}")
            self.stats['network'] += 1

            tags = self._search_musicbrainz(
                search_terms.get('title', ''),
                search_terms.get('artist', '')
            )

            if tags:
                self._log(f"  [成功] {tags['artist']} - {tags['title']}")
                source = "MusicBrainz"
            else:
                self._log(f"  [失败] 未找到匹配结果")
                self.stats['failed'] += 1
                self.root.after(0, lambda: self._add_to_tree(source, old_name, "-", "-", "-", "搜索失败"))
                return

        if not tags or not tags.get('title'):
            self.stats['skipped'] += 1
            self.root.after(0, lambda: self._add_to_tree(source, old_name, "-", "-", "-", "无数据"))
            return

        if not tags.get('artist'):
            tags['artist'] = '未知艺术家'

        # 生成新文件名
        pattern = self.pattern_entry.get()
        try:
            expected_name = pattern.format(**tags) + '.mp3'
        except KeyError:
            self.stats['failed'] += 1
            self.root.after(0, lambda: self._add_to_tree(source, old_name, "-", "-", "-", "格式错误"))
            return

        # 检查是否已符合格式
        if self._name_matches(old_name, expected_name):
            self.stats['skipped'] += 1
            self.root.after(0, lambda: self._add_to_tree(source, old_name, expected_name, tags['artist'], tags['title'], "✓"))
            return

        # 需要修改
        self.stats['preview'] += 1
        self.preview_files.append((mp3_path, tags, source))

        if preview_only:
            self.root.after(0, lambda: self._add_to_tree(
                source, old_name, expected_name, tags['artist'], tags['title'], "待修改"
            ))
            self._log(f"  [预览] {old_name} → {expected_name}")
        else:
            # 执行重命名
            try:
                new_path = mp3_path.with_name(expected_name)
                if new_path.exists():
                    if self.backup_var.get():
                        backup_path = mp3_path.with_suffix('.mp3.bak')
                        mp3_path.rename(backup_path)
                    else:
                        base = expected_name.rsplit('.', 1)[0]
                        new_path = mp3_path.with_name(f"{base}_dup.mp3")

                # 更新 ID3 标签
                self._update_id3_tags(mp3_path, tags)
                mp3_path.rename(new_path)

                self.stats['success'] += 1
                self.root.after(0, lambda: self._add_to_tree(
                    source, old_name, new_path.name, tags['artist'], tags['title'], "成功"
                ))
                self._log(f"  [成功] {old_name} → {new_path.name}")
            except Exception as e:
                self.stats['failed'] += 1
                self.root.after(0, lambda: self._add_to_tree(
                    source, old_name, f"错误：{e}", "-", "-", "失败"
                ))
                self._log(f"  [失败] {e}")

    def _name_matches(self, actual, expected):
        """检查文件名是否匹配"""
        actual_base = actual.rsplit('.', 1)[0] if '.' in actual else actual
        expected_base = expected.rsplit('.', 1)[0] if '.' in expected else expected
        return actual_base == expected_base

    def _update_id3_tags(self, mp3_path, metadata):
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
        except Exception as e:
            pass  # 忽略标签更新错误

    def _show_confirm(self):
        """显示确认按钮"""
        # 清空确认框架
        for widget in self.confirm_frame.winfo_children():
            widget.destroy()

        if self.stats['preview'] > 0:
            ttk.Label(self.confirm_frame, text=f"找到 {self.stats['preview']} 个文件需要修改", foreground='blue').pack(side=tk.LEFT, padx=5)
            ttk.Button(self.confirm_frame, text="确认执行", command=self._start_process).pack(side=tk.LEFT, padx=5)
            ttk.Button(self.confirm_frame, text="取消", command=self._hide_confirm).pack(side=tk.LEFT, padx=5)
            self.confirm_frame.pack()
        else:
            self._log("没有需要修改的文件")

    def _hide_confirm(self):
        """隐藏确认框架"""
        self.confirm_frame.pack_forget()

    def _finish_processing(self):
        """处理完成"""
        self.processing = False
        self.preview_btn.configure(state=tk.NORMAL)
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def _stop_processing(self):
        """停止处理"""
        self.processing = False
        self._log("正在停止...")


def main():
    root = tk.Tk()
    app = MP3TaggerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
