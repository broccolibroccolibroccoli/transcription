#!/usr/bin/env python3
"""
transcription.db を開くためのGUIアプリケーション
"""
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
from pathlib import Path

DB_PATH = "/Users/kayoko.namba/Desktop/transcription/transcription.db"


class DatabaseViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("transcription.db ビューアー")
        self.root.geometry("1200x800")
        
        # データベース接続
        if not os.path.exists(DB_PATH):
            messagebox.showerror("エラー", f"データベースファイルが見つかりません:\n{DB_PATH}")
            root.destroy()
            return
        
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row  # 辞書形式で取得
        
        self.create_widgets()
        self.load_tables()
    
    def create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 左側: テーブル一覧
        left_frame = ttk.LabelFrame(main_frame, text="テーブル", padding="10")
        left_frame.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        self.table_listbox = tk.Listbox(left_frame, width=20, height=10)
        self.table_listbox.pack(fill=tk.BOTH, expand=True)
        self.table_listbox.bind('<<ListboxSelect>>', self.on_table_select)
        
        # 右側: データ表示エリア
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        # タブ
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # データ表示タブ
        self.data_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.data_frame, text="データ")
        self.data_frame.columnconfigure(0, weight=1)
        self.data_frame.rowconfigure(0, weight=1)
        
        # ツリービュー（テーブル表示用）
        self.tree = ttk.Treeview(self.data_frame)
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # スクロールバー
        scrollbar_y = ttk.Scrollbar(self.data_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.tree.configure(yscrollcommand=scrollbar_y.set)
        
        scrollbar_x = ttk.Scrollbar(self.data_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.tree.configure(xscrollcommand=scrollbar_x.set)
        
        # SQL実行タブ
        self.sql_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.sql_frame, text="SQL実行")
        self.sql_frame.columnconfigure(0, weight=1)
        self.sql_frame.rowconfigure(0, weight=1)
        self.sql_frame.rowconfigure(2, weight=1)
        
        # SQL入力エリア
        sql_label = ttk.Label(self.sql_frame, text="SQLクエリを入力:")
        sql_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.sql_text = scrolledtext.ScrolledText(self.sql_frame, height=5, wrap=tk.WORD)
        self.sql_text.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # 実行ボタン
        button_frame = ttk.Frame(self.sql_frame)
        button_frame.grid(row=2, column=0, sticky=tk.W)
        
        execute_btn = ttk.Button(button_frame, text="実行", command=self.execute_sql)
        execute_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        clear_btn = ttk.Button(button_frame, text="クリア", command=self.clear_sql)
        clear_btn.pack(side=tk.LEFT)
        
        # SQL結果表示エリア
        result_label = ttk.Label(self.sql_frame, text="結果:")
        result_label.grid(row=3, column=0, sticky=tk.W, pady=(10, 5))
        
        self.result_tree = ttk.Treeview(self.sql_frame)
        self.result_tree.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.sql_frame.rowconfigure(4, weight=1)
        
        result_scrollbar_y = ttk.Scrollbar(self.sql_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        result_scrollbar_y.grid(row=4, column=1, sticky=(tk.N, tk.S))
        self.result_tree.configure(yscrollcommand=result_scrollbar_y.set)
        
        # 統計情報タブ
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="統計情報")
        
        self.stats_text = scrolledtext.ScrolledText(self.stats_frame, wrap=tk.WORD)
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.load_statistics()
    
    def load_tables(self):
        """テーブル一覧を読み込む"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        self.table_listbox.delete(0, tk.END)
        for table in tables:
            self.table_listbox.insert(tk.END, table[0])
    
    def on_table_select(self, event):
        """テーブルが選択されたとき"""
        selection = self.table_listbox.curselection()
        if not selection:
            return
        
        table_name = self.table_listbox.get(selection[0])
        self.load_table_data(table_name)
    
    def load_table_data(self, table_name):
        """テーブルのデータを読み込む"""
        # 既存の列をクリア
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree["columns"] = ()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1000")
            
            # 列名を取得
            columns = [description[0] for description in cursor.description]
            self.tree["columns"] = columns
            
            # 列の設定
            self.tree.heading("#0", text="行番号", anchor=tk.W)
            self.tree.column("#0", width=60)
            
            for col in columns:
                self.tree.heading(col, text=col, anchor=tk.W)
                self.tree.column(col, width=150)
            
            # データを挿入
            for idx, row in enumerate(cursor.fetchall(), 1):
                values = [str(row[col]) if row[col] is not None else "" for col in columns]
                self.tree.insert("", tk.END, text=str(idx), values=values)
        
        except Exception as e:
            messagebox.showerror("エラー", f"データの読み込みに失敗しました:\n{str(e)}")
    
    def execute_sql(self):
        """SQLクエリを実行"""
        sql = self.sql_text.get("1.0", tk.END).strip()
        if not sql:
            messagebox.showwarning("警告", "SQLクエリを入力してください")
            return
        
        # 既存の結果をクリア
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.result_tree["columns"] = ()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            
            # SELECT文の場合
            if sql.strip().upper().startswith("SELECT"):
                columns = [description[0] for description in cursor.description]
                self.result_tree["columns"] = columns
                
                self.result_tree.heading("#0", text="行番号", anchor=tk.W)
                self.result_tree.column("#0", width=60)
                
                for col in columns:
                    self.result_tree.heading(col, text=col, anchor=tk.W)
                    self.result_tree.column(col, width=150)
                
                for idx, row in enumerate(cursor.fetchall(), 1):
                    values = [str(row[col]) if row[col] is not None else "" for col in columns]
                    self.result_tree.insert("", tk.END, text=str(idx), values=values)
            else:
                # INSERT, UPDATE, DELETEなど
                self.conn.commit()
                messagebox.showinfo("成功", f"クエリが実行されました。\n影響を受けた行数: {cursor.rowcount}")
        
        except Exception as e:
            messagebox.showerror("エラー", f"SQLクエリの実行に失敗しました:\n{str(e)}")
    
    def clear_sql(self):
        """SQL入力エリアをクリア"""
        self.sql_text.delete("1.0", tk.END)
    
    def load_statistics(self):
        """統計情報を読み込む"""
        try:
            cursor = self.conn.cursor()
            
            stats = []
            
            # ファイル統計
            cursor.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'completed'")
            completed_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'error'")
            error_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'processing'")
            processing_count = cursor.fetchone()[0]
            
            # セグメント統計
            cursor.execute("SELECT COUNT(*) FROM segments")
            segment_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT speaker) FROM segments WHERE speaker IS NOT NULL")
            speaker_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(duration) FROM files WHERE duration IS NOT NULL")
            total_duration = cursor.fetchone()[0] or 0
            
            stats.append("=" * 60)
            stats.append("データベース統計情報")
            stats.append("=" * 60)
            stats.append("")
            stats.append(f"【ファイル情報】")
            stats.append(f"  登録ファイル数: {file_count}件")
            stats.append(f"  完了: {completed_count}件")
            stats.append(f"  処理中: {processing_count}件")
            stats.append(f"  エラー: {error_count}件")
            stats.append("")
            stats.append(f"【セグメント情報】")
            stats.append(f"  セグメント総数: {segment_count}件")
            stats.append(f"  話者数: {speaker_count}人")
            stats.append(f"  総音声時間: {total_duration:.1f}秒 ({total_duration/60:.1f}分)")
            stats.append("")
            
            # 話者別統計
            cursor.execute("""
                SELECT speaker, COUNT(*) as count
                FROM segments
                WHERE speaker IS NOT NULL
                GROUP BY speaker
                ORDER BY count DESC
            """)
            
            speaker_stats = cursor.fetchall()
            if speaker_stats:
                stats.append("【話者別セグメント数】")
                for speaker, count in speaker_stats:
                    stats.append(f"  {speaker}: {count}件")
                stats.append("")
            
            # ファイル一覧
            cursor.execute("""
                SELECT filename, status, duration, processed_at
                FROM files
                ORDER BY processed_at DESC
            """)
            
            files = cursor.fetchall()
            if files:
                stats.append("【ファイル一覧】")
                for filename, status, duration, processed_at in files:
                    duration_str = f"{duration:.1f}秒" if duration else "処理中"
                    stats.append(f"  {filename}")
                    stats.append(f"    状態: {status}")
                    stats.append(f"    長さ: {duration_str}")
                    if processed_at:
                        stats.append(f"    処理日時: {processed_at}")
                    stats.append("")
            
            self.stats_text.delete("1.0", tk.END)
            self.stats_text.insert("1.0", "\n".join(stats))
        
        except Exception as e:
            self.stats_text.delete("1.0", tk.END)
            self.stats_text.insert("1.0", f"統計情報の読み込みに失敗しました:\n{str(e)}")
    
    def __del__(self):
        """終了時にデータベース接続を閉じる"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    root = tk.Tk()
    app = DatabaseViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
