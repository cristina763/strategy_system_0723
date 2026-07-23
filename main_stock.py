import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

# 匯入功能模組
import gpt_assistant
import gpt_to_datalist
import Fibonacci_Retracement_draw_GUI as fib_gui

root = tk.Tk()
root.title("股市分析與回測整合系統")
root.geometry("1280x800")

# 設定全域字體大小
tkFont.nametofont("TkDefaultFont").configure(size=10)

# 使用 alt 主題（讓 background 設定有效）
style = ttk.Style()
style.theme_use("alt")

# 設定按鈕樣式：藍底白字 + 懸停變深藍
style.configure("Custom.TButton",
                foreground="white",
                background="#007acc",
                font=("Helvetica", 14),
                padding=10)
style.map("Custom.TButton",
          background=[("active", "#005f99")])

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# 初始首頁面板（只顯示三個功能按鈕）
welcome_tab = ttk.Frame(notebook)
notebook.add(welcome_tab, text="首頁")

btn_frame = ttk.Frame(welcome_tab)
btn_frame.pack(pady=50)

# 用於避免重複加載
loaded_tabs = {"tab1": False, "tab2": False, "tab3": False}

def load_tab1():
    if not loaded_tabs["tab1"]:
        tab1 = ttk.Frame(notebook)
        gpt_assistant.create_tab1(tab1)
        notebook.add(tab1, text="股市趨勢分析與建議")
        loaded_tabs["tab1"] = True
    notebook.select(len(notebook.tabs()) - 1)

def load_tab2():
    if not loaded_tabs["tab2"]:
        tab2 = ttk.Frame(notebook)
        gpt_to_datalist.create_tab2(tab2)
        notebook.add(tab2, text="股市資料表查詢或修改")
        loaded_tabs["tab2"] = True
    notebook.select(len(notebook.tabs()) - 1)

def load_tab3():
    if not loaded_tabs["tab3"]:
        tab3 = ttk.Frame(notebook)
        fib_gui.create_tab3(tab3)
        notebook.add(tab3, text="Fibonacci + Granville策略分析與圖表")
        loaded_tabs["tab3"] = True
    notebook.select(len(notebook.tabs()) - 1)

# 首頁三顆按鈕（使用自訂樣式）
ttk.Button(btn_frame, text="股市趨勢分析與建議", command=load_tab1,
           style="Custom.TButton", width=40).pack(pady=10)
ttk.Button(btn_frame, text="股市資料表查詢或修改", command=load_tab2,
           style="Custom.TButton", width=40).pack(pady=10)
ttk.Button(btn_frame, text="Fibonacci + Granville+KD策略分析與圖表", command=load_tab3,
           style="Custom.TButton", width=40).pack(pady=10)

root.mainloop()
