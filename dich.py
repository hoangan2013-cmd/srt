import customtkinter as ctk
import tkinter.messagebox as msg
from tkinter import filedialog
import threading
import os
from faster_whisper import WhisperModel
import requests
import time
import re
import json
import difflib
from google import genai
import whisper
from playwright.sync_api import sync_playwright, TimeoutError

# --- CẤU HÌNH GIAO DIỆN HỆ THỐNG ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MultiKeyManager:
    def __init__(self):
        self.api_keys = []
        self.current_index = 0

    def add_key(self, key):
        clean = key.strip()
        if clean and clean not in self.api_keys:
            self.api_keys.append(clean)
            return True
        return False

    def get_key(self):
        if not self.api_keys: return None
        return self.api_keys[self.current_index]

    def rotate(self):
        if len(self.api_keys) > 1:
            self.current_index = (self.current_index + 1) % len(self.api_keys)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("An8xSub - Super Subtitle & Video Translator - v7 Auto Pro")
        self.geometry("1350x950")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.key_manager = MultiKeyManager()
        self.file_path = None
        self.tiktok_video_path = None
        self.is_translating = False
        
        # Threading Events for TikTok Control
        self.stop_event = threading.Event()
        self.tk_post_event = threading.Event()
        self.tk_cancel_event = threading.Event()
        
        base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
        self.keys_file = os.path.join(base_dir, "saved_keys.txt")
        self.tiktok_config_file = os.path.join(base_dir, "tiktok_projects.json")
        
        # Dữ liệu dự án phim
        self.tk_projects = {}
        self.current_project_name = ""

        self.setup_ui()
        self.load_saved_keys()
        self.load_tiktok_projects()

    def setup_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        self.tabview.add("🎬 Dịch & Bóc Tách Phụ Đề")
        self.tabview.add("🚀 Đăng TikTok Nhanh")
        
        self.setup_trans_tab()
        self.setup_tiktok_tab()

    def setup_trans_tab(self):
        trans_tab = self.tabview.tab("🎬 Dịch & Bóc Tách Phụ Đề")
        trans_tab.grid_columnconfigure(0, weight=1)
        trans_tab.grid_rowconfigure(4, weight=1)

        self.tool_frame = ctk.CTkFrame(trans_tab, fg_color="transparent")
        self.tool_frame.grid(row=0, column=0, padx=20, pady=(10, 5), sticky="ew")
        ctk.CTkLabel(self.tool_frame, text="Nền tảng dịch:", font=("Arial", 12, "bold")).pack(side="left", padx=5)
        self.combo_provider = ctk.CTkComboBox(self.tool_frame, values=["Groq", "OpenRouter", "GitHub", "Gemini"], width=150, command=self.on_provider_change)
        self.combo_provider.pack(side="left", padx=5)
        self.combo_model = ctk.CTkComboBox(self.tool_frame, values=["llama-3.3-70b-versatile", "gemma2-9b-it"], width=300)
        self.combo_model.pack(side="left", padx=5)

        self.key_frame = ctk.CTkFrame(trans_tab)
        self.key_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.entry_key = ctk.CTkEntry(self.key_frame, placeholder_text="Dán API Key vào đây...")
        self.entry_key.pack(side="left", fill="x", expand=True, padx=5, pady=10)
        self.btn_add_key = ctk.CTkButton(self.key_frame, text="➕ THÊM KEY", command=self.gui_add_key)
        self.btn_add_key.pack(side="left", padx=5)
        self.lbl_key_count = ctk.CTkLabel(self.key_frame, text="Kho đạn: 0 Key", text_color="#f39c12", font=("Arial", 12, "bold"))
        self.lbl_key_count.pack(side="left", padx=10)

        self.settings_frame = ctk.CTkFrame(trans_tab)
        self.settings_frame.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        self.settings_row1 = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_row1.pack(fill="x", pady=5)
        ctk.CTkLabel(self.settings_row1, text="Bối cảnh xưng hô:", font=("Arial", 12, "bold")).pack(side="left", padx=(10, 2))
        self.entry_context = ctk.CTkEntry(self.settings_row1, width=700, placeholder_text="Bối cảnh phim...")
        self.entry_context.pack(side="left", padx=5)

        self.settings_row2 = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_row2.pack(fill="x", pady=5)
        ctk.CTkLabel(self.settings_row2, text="Chế độ chạy:", font=("Arial", 12, "bold")).pack(side="left", padx=(10, 5))
        self.combo_mode = ctk.CTkComboBox(self.settings_row2, values=["Chỉ Dịch (Tốc độ cao)", "Kết hợp (Dịch + Review)", "Chỉ Review"], width=180)
        self.combo_mode.pack(side="left", padx=5)
        ctk.CTkLabel(self.settings_row2, text="Bắt đầu từ đoạn:", font=("Arial", 12, "bold")).pack(side="left", padx=(20, 5))
        self.entry_start_block = ctk.CTkEntry(self.settings_row2, width=80)
        self.entry_start_block.pack(side="left", padx=5)
        self.entry_start_block.insert(0, "1")

        self.file_frame = ctk.CTkFrame(trans_tab, fg_color="transparent")
        self.file_frame.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        self.btn_file = ctk.CTkButton(self.file_frame, text="📂 1. CHỌN SRT", fg_color="#17a2b8", command=self.select_file)
        self.btn_file.pack(side="left")
        self.btn_video = ctk.CTkButton(self.file_frame, text="🎙️ 2. TÁCH TỪ VIDEO", fg_color="#8e44ad", command=self.extract_sub_from_video)
        self.btn_video.pack(side="left", padx=15)
        
        ctk.CTkLabel(self.file_frame, text="Tốc độ Video:", font=("Arial", 12, "bold")).pack(side="left", padx=(15, 5))
        self.entry_speed = ctk.CTkEntry(self.file_frame, width=50)
        self.entry_speed.pack(side="left")
        self.entry_speed.insert(0, "0.9")
        
        ctk.CTkLabel(self.file_frame, text="Chữ tối đa/dòng:", font=("Arial", 12, "bold")).pack(side="left", padx=(15, 5))
        self.entry_max_chars = ctk.CTkEntry(self.file_frame, width=50)
        self.entry_max_chars.pack(side="left")
        self.entry_max_chars.insert(0, "18")
        self.lbl_file = ctk.CTkLabel(self.file_frame, text="Chưa chọn file...", text_color="gray")
        self.lbl_file.pack(side="left", padx=20)

        self.text_frame = ctk.CTkFrame(trans_tab, fg_color="transparent")
        self.text_frame.grid(row=4, column=0, padx=20, pady=10, sticky="nsew")
        self.text_frame.columnconfigure((0, 1), weight=1)
        self.text_frame.rowconfigure(1, weight=1)
        self.txt_orig = ctk.CTkTextbox(self.text_frame, font=("Consolas", 14))
        self.txt_orig.grid(row=1, column=0, padx=(0, 5), sticky="nsew")
        self.txt_trans = ctk.CTkTextbox(self.text_frame, font=("Consolas", 14))
        self.txt_trans.grid(row=1, column=1, padx=(5, 0), sticky="nsew")

        self.bottom_frame = ctk.CTkFrame(trans_tab, fg_color="transparent")
        self.bottom_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        self.lbl_status = ctk.CTkLabel(self.bottom_frame, text="Trạng thái: Sẵn sàng.", font=("Arial", 14, "bold"), text_color="#4CAF50")
        self.lbl_status.pack(side="left")
        self.btn_run = ctk.CTkButton(self.bottom_frame, text="▶ BẮT ĐẦU DỊCH", fg_color="#dc3545", font=("Arial", 14, "bold"), command=self.toggle_translation)
        self.btn_run.pack(side="right")
        self.btn_save = ctk.CTkButton(self.bottom_frame, text="💾 LƯU FILE SRT", fg_color="#28a745", font=("Arial", 14, "bold"), command=self.save_translated_file)
        self.btn_save.pack(side="right", padx=10)

    def setup_tiktok_tab(self):
        tk_tab = self.tabview.tab("🚀 Đăng TikTok Nhanh")
        
        main_layout = ctk.CTkFrame(tk_tab, fg_color="transparent")
        main_layout.pack(fill="both", expand=True, padx=20, pady=20)
        
        left_col = ctk.CTkFrame(main_layout)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left_col, text="📂 QUẢN LÝ DỰ ÁN PHIM", font=("Arial", 16, "bold")).pack(pady=15)
        
        self.combo_tk_project = ctk.CTkComboBox(left_col, width=350, command=self.on_project_select)
        self.combo_tk_project.pack(pady=5, padx=20)
        
        self.entry_tk_title = ctk.CTkEntry(left_col, width=350, placeholder_text="Tiêu đề mẫu (vd: Phim - Tập {tap})")
        self.entry_tk_title.pack(pady=10, padx=20)
        
        self.txt_tk_desc = ctk.CTkTextbox(left_col, height=120, width=350)
        self.txt_tk_desc.pack(pady=5, padx=20)
        
        self.btn_save_proj = ctk.CTkButton(left_col, text="💾 LƯU DỰ ÁN", fg_color="#28a745", command=self.save_tiktok_projects)
        self.btn_save_proj.pack(pady=20, padx=20)

        right_col = ctk.CTkFrame(main_layout)
        right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        ctk.CTkLabel(right_col, text="⚙️ ĐIỀU KHIỂN UPLOAD", font=("Arial", 16, "bold")).pack(pady=15)
        
        ep_frame = ctk.CTkFrame(right_col, fg_color="transparent")
        ep_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(ep_frame, text="Tập hiện tại:").pack(side="left")
        self.entry_tk_episode = ctk.CTkEntry(ep_frame, width=80)
        self.entry_tk_episode.pack(side="left", padx=10)
        
        self.btn_tk_video = ctk.CTkButton(right_col, text="📁 CHỌN VIDEO", command=self.select_tiktok_video)
        self.btn_tk_video.pack(pady=10)
        self.lbl_tk_video = ctk.CTkLabel(right_col, text="Chưa chọn file nào", text_color="gray")
        self.lbl_tk_video.pack()

        progress_container = ctk.CTkFrame(right_col, fg_color="#2b2b2b")
        progress_container.pack(fill="x", padx=20, pady=20)
        
        self.progress_bar = ctk.CTkProgressBar(progress_container)
        self.progress_bar.pack(fill="x", padx=10, pady=10)
        self.progress_bar.set(0)
        
        self.lbl_tk_status = ctk.CTkLabel(progress_container, text="Sẵn sàng", font=("Arial", 12))
        self.lbl_tk_status.pack(pady=5)
        
        self.btn_tk_upload = ctk.CTkButton(right_col, text="BƯỚC 1: TẢI LÊN", height=40, fg_color="#007bff", command=self.start_upload_process)
        self.btn_tk_upload.pack(fill="x", padx=20, pady=5)
        
        self.btn_tk_post = ctk.CTkButton(right_col, text="BƯỚC 2: ĐĂNG NGAY", height=40, fg_color="#fe2c55", state="disabled", command=self.trigger_post)
        self.btn_tk_post.pack(fill="x", padx=20, pady=5)

    def load_tiktok_projects(self):
        if os.path.exists(self.tiktok_config_file):
            try:
                with open(self.tiktok_config_file, "r", encoding="utf-8") as f:
                    self.tk_projects = json.load(f)
                    
                    project_names = list(self.tk_projects.keys())
                    if project_names:
                        self.combo_tk_project.configure(values=project_names)
                        self.combo_tk_project.set(project_names[0])
                        self.on_project_select(project_names[0])
            except Exception as e:
                print(f"Lỗi đọc config TikTok: {e}")

    def on_project_select(self, project_name):
        if project_name in self.tk_projects:
            data = self.tk_projects[project_name]
            self.entry_tk_title.delete(0, 'end')
            self.entry_tk_title.insert(0, data.get("title", ""))
            
            self.txt_tk_desc.delete("1.0", "end")
            self.txt_tk_desc.insert("1.0", data.get("desc", ""))
            
            last_ep = data.get("last_ep", 0)
            next_ep = last_ep + 1
            self.entry_tk_episode.delete(0, 'end')
            self.entry_tk_episode.insert(0, f"{next_ep:02d}")

    def save_tiktok_projects(self, auto=False):
        proj_name = self.combo_tk_project.get().strip()
        title = self.entry_tk_title.get().strip()
        desc = self.txt_tk_desc.get("1.0", "end").strip()
        ep_str = self.entry_tk_episode.get().strip()
        
        if not proj_name:
            if not auto: msg.showwarning("Cảnh báo", "Vui lòng nhập Tên Dự Án (Chọn phim)!")
            return
            
        try: current_ep = int(ep_str) - 1
        except: current_ep = 0

        if auto:
            try: current_ep = int(ep_str)
            except: pass

        self.tk_projects[proj_name] = {
            "title": title,
            "desc": desc,
            "last_ep": current_ep
        }
        
        try:
            with open(self.tiktok_config_file, "w", encoding="utf-8") as f: 
                json.dump(self.tk_projects, f, ensure_ascii=False, indent=4)
            
            self.combo_tk_project.configure(values=list(self.tk_projects.keys()))
            if not auto: msg.showinfo("Thành công", f"Đã lưu dự án '{proj_name}' thành công!")
        except Exception as e:
            if not auto: msg.showerror("Lỗi", str(e))

    def select_tiktok_video(self):
        video_path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov")])
        if video_path:
            self.tiktok_video_path = video_path
            self.lbl_tk_video.configure(text=os.path.basename(video_path), text_color="white")

    def update_tk_status(self, text, color="orange"):
        self.after(0, lambda: self.lbl_tk_status.configure(text=text, text_color=color))

    def update_tk_progress(self, percentage):
        self.after(0, lambda: self.progress_bar.set(percentage / 100.0))

    def start_upload_process(self):
        if not self.tiktok_video_path or not os.path.exists(self.tiktok_video_path):
            msg.showwarning("Cảnh báo", "Vui lòng chọn file video trước!")
            return

        self.tk_post_event.clear()
        self.tk_cancel_event.clear()
        
        self.btn_tk_upload.configure(state="disabled")
        self.btn_tk_post.configure(state="disabled", text="Bước 2: XÁC NHẬN ĐĂNG (POST) ✅")
        
        threading.Thread(target=self.playwright_worker, daemon=True).start()

    def trigger_post(self):
        self.tk_post_event.set()
        self.btn_tk_post.configure(state="disabled", text="⏳ Đang gửi lệnh Đăng...")

    def playwright_worker(self):
        title_tpl = self.entry_tk_title.get().strip()
        desc_tpl = self.txt_tk_desc.get("1.0", "end").strip()
        ep = self.entry_tk_episode.get().strip()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        chosen_user_data_dir = os.path.join(base_dir, "TikTok_Session")
        os.makedirs(chosen_user_data_dir, exist_ok=True)

        self.update_tk_status("⏳ Đang mở trình duyệt...", "orange")

        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=chosen_user_data_dir,
                    headless=False,
                    args=[
                        "--start-maximized", 
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                page = context.new_page()
                page.set_default_timeout(60000)
                
                self.update_tk_status("🌐 Đang kết nối TikTok Studio...")
                page.goto("https://www.tiktok.com/creator-center/upload")
                
                time.sleep(3)
                if "login" in page.url or page.locator("text=Log in").is_visible() or page.locator("text=Đăng nhập").is_visible():
                    self.update_tk_status("⚠️ YÊU CẦU: Hãy quét mã QR đăng nhập trên trình duyệt!", "red")
                    page.wait_for_url("**/creator-center/upload**", timeout=300000)

                self.update_tk_status("✅ Đã vào trang Upload. Đang nạp video...", "#4CAF50")
                
                page.wait_for_selector("input[type='file']", state="attached", timeout=30000)
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(self.tiktok_video_path)
                
                self.update_tk_status("✍️ Đang điền nội dung...", "orange")
                editor = page.locator('.ProseMirror, [contenteditable="true"]').first
                editor.wait_for(state="visible", timeout=60000)
                editor.click()
                time.sleep(1)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                
                final_caption = title_tpl.replace("{tap}", ep)
                if desc_tpl: final_caption += f"\n{desc_tpl}"
                page.keyboard.type(final_caption, delay=50)
                
                self.update_tk_status("🔄 Đang tải video lên máy chủ (Vui lòng đợi)...", "cyan")
                post_button = page.locator('button:has-text("Đăng"), button:has-text("Post")').last
                
                max_wait_seconds = 300
                waited = 0
                while post_button.is_disabled():
                    time.sleep(2)
                    waited += 2
                    if waited > max_wait_seconds:
                        raise Exception("Quá thời gian tải lên (5 phút). Video quá nặng hoặc kẹt mạng.")
                    try:
                        texts = page.evaluate("document.body.innerText")
                        match = re.search(r'(\d{1,3})%', texts)
                        if match:
                            percent = int(match.group(1))
                            self.update_tk_progress(percent)
                            self.update_tk_status(f"🚀 Tiến trình tải lên: {percent}%", "cyan")
                    except: pass

                self.update_tk_status("✅ Tải lên HOÀN TẤT! Hãy bấm nút [BƯỚC 2] để Đăng.", "#4CAF50")
                self.update_tk_progress(100)
                self.after(0, lambda: self.btn_tk_post.configure(state="normal"))
                
                self.tk_post_event.wait()
                
                if self.tk_cancel_event.is_set():
                    self.update_tk_status("❌ Đã hủy đăng.", "red")
                    context.close()
                    return

                self.update_tk_status("⏳ Đang gửi lệnh Đăng...", "orange")
                time.sleep(1)
                
                try: post_button.click(force=True)
                except: pass
                
                try: page.evaluate("arguments[0].click()", post_button.element_handle())
                except: pass
                
                self.update_tk_status("🔄 Chờ TikTok xử lý bài đăng...", "cyan")
                try:
                    page.wait_for_selector('text="Manage posts", text="Quản lý bài đăng", text="Upload another video", text="Tải video khác lên"', timeout=30000)
                    self.update_tk_status("🎉 ĐĂNG THÀNH CÔNG VÀ ĐÃ LƯU TẬP MỚI!", "#4CAF50")
                    self.save_tiktok_projects(auto=True) 
                    self.after(0, lambda: self.on_project_select(self.combo_tk_project.get()))
                    self.after(0, lambda: msg.showinfo("Thành công", f"Đã đăng {final_caption} thành công!"))
                except TimeoutError:
                    self.update_tk_status("⚠️ Đã bấm Đăng, nhưng không tìm thấy thông báo xác nhận.", "orange")
                    self.after(0, lambda: msg.showwarning("Lưu ý", "Lệnh đăng đã gửi nhưng không đọc được phản hồi từ TikTok. Vui lòng kiểm tra lại kênh."))

                time.sleep(3)
                context.close()
                
        except Exception as e:
            self.update_tk_status("❌ Lỗi tiến trình tải lên.", "red")
            self.after(0, lambda: msg.showerror("Lỗi Playwright", str(e)))
        finally:
            self.after(0, lambda: self.btn_tk_upload.configure(state="normal"))
            self.after(0, lambda: self.btn_tk_post.configure(state="disabled", text="Bước 2: XÁC NHẬN ĐĂNG (POST) ✅"))
            self.update_tk_progress(0)

    def on_provider_change(self, provider):
        if "Groq" in provider: self.combo_model.configure(values=["llama-3.3-70b-versatile", "gemma2-9b-it"])
        elif "OpenRouter" in provider: self.combo_model.configure(values=["google/gemini-2.5-flash:free", "meta-llama/llama-3-8b-instruct:free"])
        elif "GitHub" in provider: self.combo_model.configure(values=["gpt-4o-mini", "Llama-3.3-70B-Instruct"])
        elif "Gemini" in provider: self.combo_model.configure(values=["gemini-2.5-flash", "gemini-2.5-pro"])
        self.combo_model.set(self.combo_model.cget("values")[0])

    def load_saved_keys(self):
        if os.path.exists(self.keys_file):
            with open(self.keys_file, "r", encoding="utf-8") as f:
                for k in f.read().splitlines(): self.key_manager.add_key(k)
            self.lbl_key_count.configure(text=f"Kho đạn: {len(self.key_manager.api_keys)} Key")

    def save_keys_to_file(self):
        with open(self.keys_file, "w", encoding="utf-8") as f: f.write("\n".join(self.key_manager.api_keys))

    def gui_add_key(self):
        if self.key_manager.add_key(self.entry_key.get()):
            self.lbl_key_count.configure(text=f"Kho đạn: {len(self.key_manager.api_keys)} Key")
            self.entry_key.delete(0, 'end')
            self.save_keys_to_file()

    def select_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("SRT files", "*.srt")])
        if self.file_path:
            self.lbl_file.configure(text=os.path.basename(self.file_path))
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.txt_orig.delete("1.0", "end")
                self.txt_orig.insert("1.0", f.read())

    def save_translated_file(self):
        content = self.txt_trans.get("1.0", "end").strip()
        if not content: return
        save_path = filedialog.asksaveasfilename(defaultextension=".srt", filetypes=[("SRT files", "*.srt")])
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f: f.write(content)
            msg.showinfo("Thành công", "Đã lưu file thành công!")

    def format_srt_time(self, seconds):
        h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    # =================================================================================
    # =============== NEW PROFESSIONAL SUBTITLE EXTRACTION ENGINE =====================
    # =================================================================================

    def correct_asr_with_gemini(self, scenes_batch, api_key):
        """
        AI chỉ làm đúng 1 việc: Sửa lỗi chính tả/ngữ cảnh của ASR.
        TUYỆT ĐỐI không chia dòng, không làm mất chữ.
        """
        if not api_key: return scenes_batch
        
        numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(scenes_batch))
        prompt = f"""Bạn là chuyên gia sửa lỗi nhận dạng giọng nói (ASR) tiếng Trung.
Dưới đây là các câu transcript thô từ Whisper.

{numbered}

Nhiệm vụ BẮT BUỘC:
1. Sửa lỗi từ đồng âm, sai chính tả do Whisper nghe nhầm.
2. TUYỆT ĐỐI GIỮ NGUYÊN cấu trúc câu, số lượng từ ngữ tương đương nguyên bản.
3. KHÔNG THÊM BỚT ý, KHÔNG ngắt dòng bừa bãi, KHÔNG dịch.
4. Trả về đúng số lượng dòng, giữ nguyên định dạng [số].
"""
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=0.0) # Đưa temp về 0 để deterministic
            )
            lines = [l.strip() for l in response.text.strip().splitlines() if l.strip()]
            corrected = {}
            for line in lines:
                m = re.match(r'^\[(\d+)\]\s*(.*)', line)
                if m:
                    corrected[int(m.group(1)) - 1] = m.group(2).strip()
            
            # Fallback an toàn: Nếu AI làm mất câu hoặc sửa quá khác biệt, trả về nguyên bản
            result = []
            for i in range(len(scenes_batch)):
                ai_text = corrected.get(i, "")
                raw_text = scenes_batch[i]
                # Nếu AI trả về rỗng hoặc độ dài chênh lệch quá 2 lần -> Fallback
                if not ai_text or len(ai_text) > len(raw_text) * 2 or len(ai_text) < len(raw_text) / 2:
                    result.append(raw_text)
                else:
                    result.append(ai_text)
            return result
        except Exception:
            return scenes_batch

    def align_text_to_timestamps(self, raw_words, corrected_text):
        """
        Word Alignment Tool: Khớp từng ký tự của văn bản đã sửa (từ AI) 
        vào đúng Timestamp gốc của Whisper bằng thuật toán Diff.
        """
        char_map = []
        original_text = ""
        
        # Trải phẳng raw_words thành từng ký tự với timestamp đều nhau
        for wd in raw_words:
            w_text = wd.word.strip()
            if not w_text: continue
            char_dur = (wd.end - wd.start) / len(w_text)
            for i, ch in enumerate(w_text):
                char_map.append({
                    'char': ch,
                    'start': wd.start + i * char_dur,
                    'end': wd.start + (i + 1) * char_dur
                })
                original_text += ch

        corrected_text = corrected_text.replace(" ", "")
        
        # Fallback hoàn toàn nếu không có chữ
        if not corrected_text or not original_text:
            return char_map

        matcher = difflib.SequenceMatcher(None, original_text, corrected_text)
        
        # Nếu AI sửa đổi đến mức phá hỏng cấu trúc (tỷ lệ giống < 40%) -> Từ chối AI, lấy Whisper gốc
        if matcher.ratio() < 0.4:
            return char_map

        aligned_chars = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for k in range(j2 - j1):
                    aligned_chars.append({
                        'char': corrected_text[j1 + k],
                        'start': char_map[i1 + k]['start'],
                        'end': char_map[i1 + k]['end']
                    })
            elif tag == 'replace' or tag == 'insert':
                # Nội suy timestamp cho các từ AI sửa/thêm vào dựa trên ranh giới liền kề
                t_start = char_map[i1]['start'] if i1 < len(char_map) else (char_map[-1]['end'] if char_map else 0)
                t_end = char_map[i2-1]['end'] if (i2-1 < len(char_map) and i2 > i1) else t_start + 0.1
                dur = max(0.01, t_end - t_start)
                char_dur = dur / max(1, (j2 - j1))
                for k in range(j2 - j1):
                    aligned_chars.append({
                        'char': corrected_text[j1 + k],
                        'start': t_start + k * char_dur,
                        'end': t_start + (k + 1) * char_dur
                    })
        
        # Căn chỉnh lại để timeline luôn tịnh tiến (Monotonic)
        for i in range(1, len(aligned_chars)):
            if aligned_chars[i]['start'] < aligned_chars[i-1]['end']:
                aligned_chars[i]['start'] = aligned_chars[i-1]['end']
            if aligned_chars[i]['end'] < aligned_chars[i]['start']:
                aligned_chars[i]['end'] = aligned_chars[i]['start'] + 0.05

        return aligned_chars

    def segment_subtitles_algorithmically(self, aligned_chars, max_chars):
        """
        Subtitle Segmentation Tool: Cắt subtitle thuần túy bằng thuật toán dựa trên:
        - Giới hạn số ký tự.
        - Khoảng lặng âm thanh (Pause Detection).
        - Ngữ pháp (Dấu câu).
        """
        if not aligned_chars: return []
        
        STRONG_PUNCT = set('。？！?!')
        WEAK_PUNCT = set('，、；,;')
        PAUSE_THRESHOLD = 0.4  # Khoảng lặng > 0.4s thì ngắt dòng
        
        entries = []
        current_chunk = []
        
        for i, char_info in enumerate(aligned_chars):
            current_chunk.append(char_info)
            
            is_last = (i == len(aligned_chars) - 1)
            next_char = aligned_chars[i+1] if not is_last else None
            pause_after = (next_char['start'] - char_info['end']) if next_char else 0
            
            # Phân tích điều kiện ngắt
            hit_max_chars = len(current_chunk) >= max_chars
            is_strong_punct = char_info['char'] in STRONG_PUNCT
            is_weak_and_pause = (char_info['char'] in WEAK_PUNCT) and (pause_after >= 0.25)
            is_long_pause = pause_after >= PAUSE_THRESHOLD
            
            if is_last or hit_max_chars or is_strong_punct or is_weak_and_pause or is_long_pause:
                # Chống tạo subtitle 1 ký tự rác (trừ khi là ký tự cuối cùng)
                if len(current_chunk) == 1 and not is_last and not is_long_pause:
                    continue
                    
                text = "".join([c['char'] for c in current_chunk]).strip()
                if text:
                    entries.append({
                        'text': text,
                        'start': current_chunk[0]['start'],
                        'end': current_chunk[-1]['end']
                    })
                current_chunk = []
                
        return entries

    def validate_and_optimize_subtitles(self, entries):
        """
        Validation Tool: Trạm kiểm duyệt cuối cùng, tự động fix lỗi Overlap, 
        Subtitle rỗng, Negative duration và merge các sub quá ngắn.
        """
        valid = []
        MIN_GAP = 0.001
        
        for entry in entries:
            text = entry['text'].strip()
            if not text: continue  # Xóa sub rỗng
            
            start = entry['start']
            end = entry['end']
            
            # Fix Negative Duration
            if end <= start:
                end = start + 0.1
                
            # Xóa Duplicate (trùng text và timeline sát nhau)
            if valid and valid[-1]['text'] == text and (start - valid[-1]['end'] < 0.3):
                valid[-1]['end'] = max(valid[-1]['end'], end)
                continue
                
            # Fix Overlap Timeline thần thánh
            if valid and start < valid[-1]['end']:
                start = valid[-1]['end'] + MIN_GAP
                if end <= start:
                    end = start + 0.1
                    
            valid.append({'text': text, 'start': start, 'end': end})
            
        # Tối ưu hóa Reading Speed (CPS) & Gộp sub 1 ký tự
        optimized = []
        for i, entry in enumerate(valid):
            # Nếu sub chỉ có 1-2 chữ và khoảng cách rất gần sub trước -> Merge
            if len(entry['text']) <= 2 and optimized:
                prev = optimized[-1]
                gap = entry['start'] - prev['end']
                if gap < 0.25 and not any(p in prev['text'] for p in '。？！?!'):
                    prev['text'] += entry['text']
                    prev['end'] = max(prev['end'], entry['end'])
                    continue
            optimized.append(entry)
            
        return optimized

    def check_coverage_and_fill(self, video_path, wmodel, entries, total_duration, api_key):
        """
        Coverage Checker: Quét lại toàn bộ timeline, phát hiện các khoảng trống (gaps)
        bị VAD bỏ sót. Nếu có gap > 2 giây, chạy Whisper cưỡng chế (tắt VAD) vào vùng đó.
        """
        if not entries: return entries
        
        # Tìm khoảng trống (gaps) > 2.0s
        gaps = []
        last_end = 0.0
        for e in entries:
            if e['start'] - last_end > 2.0:
                gaps.append({'start': last_end, 'end': e['start']})
            last_end = e['end']
            
        if total_duration - last_end > 2.0:
            gaps.append({'start': last_end, 'end': total_duration})
            
        if not gaps: return entries
        
        self.after(0, lambda: self.lbl_status.configure(
            text=f"[4/5] Coverage Checker: Phát hiện {len(gaps)} khoảng trống. Đang quét sâu...", text_color="#e67e22"))
            
        # Chạy Whisper với mode Aggressive (Bỏ VAD, giảm ngưỡng lọc rác)
        segments, _ = wmodel.transcribe(
            video_path, language="zh", word_timestamps=True,
            vad_filter=False,  # Tắt VAD để nghe tất cả
            no_speech_threshold=0.95,
            log_prob_threshold=-2.5
        )
        
        fill_words = []
        for seg in segments:
            if not seg.words: continue
            for w in seg.words:
                # Chỉ lấy những từ rơi vào bên trong vùng bị gap
                for g in gaps:
                    if g['start'] + 0.2 <= w.start <= g['end'] - 0.2:
                        fill_words.append(w)
                        break
                        
        if not fill_words:
            return entries
            
        # Đưa các từ lấp đầy qua pipeline rút gọn
        raw_text = "".join(w.word.strip() for w in fill_words)
        corrected_text = self.correct_asr_with_gemini([raw_text], api_key)[0] if api_key else raw_text
        aligned_chars = self.align_text_to_timestamps(fill_words, corrected_text)
        max_chars = int(self.entry_max_chars.get().strip()) if self.entry_max_chars.get().strip().isdigit() else 18
        new_segs = self.segment_subtitles_algorithmically(aligned_chars, max_chars)
        
        # Nối và Validate lại tổng thể
        all_entries = entries + new_segs
        all_entries.sort(key=lambda x: x['start'])
        return self.validate_and_optimize_subtitles(all_entries)

    def extract_sub_from_video(self):
        """
        Main Engine Orchestrator
        """
        video_path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov")])
        if not video_path: return
        save_path = filedialog.asksaveasfilename(defaultextension=".srt", filetypes=[("SRT files", "*.srt")])
        if not save_path: return

        try: speed_factor = float(self.entry_speed.get().strip())
        except: speed_factor = 1.0

        api_key = self.key_manager.get_key()
        
        self.btn_video.configure(state="disabled")
        self.lbl_status.configure(text="Đang tải model Faster-Whisper...", text_color="orange")

        def process():
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                model_dir = os.path.join(current_dir, "models")
                os.makedirs(model_dir, exist_ok=True)

                self.after(0, lambda: self.lbl_status.configure(text="[1/5] Whisper đang đọc sóng âm...", text_color="#007bff"))
                wmodel = WhisperModel("large-v3-turbo", device="auto", compute_type="default", download_root=model_dir)

                # ================= BƯỚC 1: NHẬN DẠNG GỐC =================
                segments_generator, info = wmodel.transcribe(
                    video_path,
                    language="zh",
                    word_timestamps=True,
                    condition_on_previous_text=True,
                    initial_prompt="简体中文。表达自然，标点准确。",
                    no_speech_threshold=0.6,
                    log_prob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=250)
                )

                total_duration = info.duration
                all_scenes = []
                current_words = []
                prev_end = 0.0
                SCENE_PAUSE = 1.5

                for seg in segments_generator:
                    percent = min((seg.end / total_duration) * 100, 100.0)
                    self.after(0, lambda p=percent: self.lbl_status.configure(
                        text=f"[1/5] Whisper Extracting: {p:.1f}%", text_color="#007bff"))

                    if not seg.words: continue
                    for wd in seg.words:
                        if current_words and (wd.start - prev_end) >= SCENE_PAUSE:
                            raw = "".join(w.word.strip() for w in current_words)
                            all_scenes.append((current_words[:], raw))
                            current_words = []
                        current_words.append(wd)
                        prev_end = wd.end

                if current_words:
                    all_scenes.append((current_words[:], "".join(w.word.strip() for w in current_words)))

                # ================= BƯỚC 2 & 3: ASR CORRECTION & ALIGNMENT =================
                max_chars = int(self.entry_max_chars.get().strip()) if self.entry_max_chars.get().strip().isdigit() else 18
                raw_srt_entries = []
                total_scenes = len(all_scenes)
                ASR_BATCH = 5

                raw_texts = [raw for _, raw in all_scenes]
                corrected_texts = []
                
                if api_key:
                    for b_start in range(0, len(raw_texts), ASR_BATCH):
                        batch = raw_texts[b_start:b_start + ASR_BATCH]
                        self.after(0, lambda s=b_start, t=total_scenes: self.lbl_status.configure(
                            text=f"[2/5] AI Correction: Đoạn {s+1}–{min(s+ASR_BATCH, t)}/{t}...", text_color="#9b59b6"))
                        corrected_batch = self.correct_asr_with_gemini(batch, api_key)
                        corrected_texts.extend(corrected_batch)
                else:
                    corrected_texts = raw_texts

                for idx, (word_list, raw_text) in enumerate(all_scenes):
                    self.after(0, lambda i=idx, t=total_scenes: self.lbl_status.configure(
                        text=f"[3/5] Thuật toán chia Subtitle: {i+1}/{t}...", text_color="#f39c12"))
                    
                    c_text = corrected_texts[idx] if idx < len(corrected_texts) else raw_text
                    
                    # Cốt lõi: Căn chỉnh chữ theo timestamp của Whisper, sau đó chia dòng bằng thuật toán
                    aligned_chars = self.align_text_to_timestamps(word_list, c_text)
                    entries = self.segment_subtitles_algorithmically(aligned_chars, max_chars)
                    raw_srt_entries.extend(entries)

                # ================= BƯỚC 4: VALIDATION =================
                self.after(0, lambda: self.lbl_status.configure(
                    text="[4/5] Validator: Đang làm sạch và tối ưu Timeline...", text_color="#3498db"))
                optimized_entries = self.validate_and_optimize_subtitles(raw_srt_entries)

                # ================= BƯỚC 5: COVERAGE CHECK =================
                final_entries = self.check_coverage_and_fill(video_path, wmodel, optimized_entries, total_duration, api_key)

                # ================= XUẤT FILE SRT =================
                self.after(0, lambda: self.lbl_status.configure(
                    text="[5/5] Hoàn tất! Đang xuất file...", text_color="#2ecc71"))
                    
                srt_content = ""
                for idx, entry in enumerate(final_entries, 1):
                    # Điều chỉnh speed video xuất ra (Chỉ tác động ở đầu ra Text, giữ nguyên logic lõi)
                    start_str = self.format_srt_time(entry['start'] / speed_factor)
                    end_str = self.format_srt_time(entry['end'] / speed_factor)
                    srt_content += f"{idx}\n{start_str} --> {end_str}\n{entry['text']}\n\n"

                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                    
                self.file_path = save_path
                self.after(0, lambda: self.txt_orig.delete("1.0", "end"))
                self.after(0, lambda: self.txt_orig.insert("1.0", srt_content))
                self.after(0, lambda: self.lbl_status.configure(
                    text="✅ HOÀN TẤT: Subtitle chuẩn Studio!", text_color="#28a745"))

            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                self.after(0, lambda m=error_msg: msg.showerror("Lỗi bóc tách", f"Lỗi System: {m}"))
                self.after(0, lambda: self.lbl_status.configure(text="❌ Có lỗi xảy ra.", text_color="red"))
            finally:
                self.after(0, lambda: self.btn_video.configure(state="normal"))

        threading.Thread(target=process, daemon=True).start()

    # =================================================================================
    # =============== KẾT THÚC NEW ENGINE =============================================
    # =================================================================================

    def translate_block_standard(self, block, context, provider, model):
        retries = 0
        max_retries = 50
        
        while not self.stop_event.is_set():
            if retries >= max_retries: 
                return f"{block}\n\n[LỖI: API quá tải sau nhiều lần thử]"
                
            api_key = self.key_manager.get_key()
            if not api_key: return "[LỖI: Thiếu Key]"

            if provider == "Gemini":
                try:
                    client = genai.Client(api_key=api_key)
                    system_instruction = (
                        f"Bạn là dịch giả SRT chuyên nghiệp. BỐI CẢNH XƯNG HÔ: {context}. "
                        "NHIỆM VỤ BẮT BUỘC: Dịch 100% nội dung chữ sang Tiếng Việt. KHÔNG ĐƯỢC để lại tiếng nước ngoài. "
                        "TUYỆT ĐỐI giữ nguyên định dạng số thứ tự và mốc thời gian SRT (00:00:00,000 --> 00:00:00,000)."
                    )
                    response = client.models.generate_content(
                        model=model, 
                        contents=block, 
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_instruction, 
                            temperature=0.1
                        )
                    )
                    
                    result_text = response.text.strip()
                    if not result_text:
                        raise ValueError("API trả về chuỗi rỗng")
                        
                    return result_text
                except Exception as e:
                    time.sleep(4)
                    self.key_manager.rotate()
                    retries += 1
                    continue

            url = ""
            if provider == "Groq": url = "https://api.groq.com/openai/v1/chat/completions"
            elif provider == "OpenRouter": url = "https://openrouter.ai/api/v1/chat/completions"
            elif provider == "GitHub": url = "https://models.inference.ai.azure.com/chat/completions"
            
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            system_prompt = (
                f"Dịch phụ đề SRT sang Tiếng Việt. XƯNG HÔ: {context}. "
                "BẮT BUỘC: Phải dịch hết chữ sang Tiếng Việt, giữ nguyên format SRT, KHÔNG giữ lại nguyên bản."
            )
            payload = {
                "model": model, 
                "messages": [
                    {"role": "system", "content": system_prompt}, 
                    {"role": "user", "content": block}
                ], 
                "temperature": 0.1
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                if resp.status_code != 200: 
                    time.sleep(4)
                    self.key_manager.rotate()
                    retries += 1
                    continue
                    
                result_text = resp.json()['choices'][0]['message']['content'].strip()
                if not result_text:
                    raise ValueError("API trả về chuỗi rỗng")
                return result_text
            except:
                time.sleep(4)
                self.key_manager.rotate()
                retries += 1
                continue
                
        return "[ĐÃ DỪNG]"

    def review_block_with_gemini(self, original, translated, context):
        retries = 0
        max_retries = 50
        while not self.stop_event.is_set():
            if retries >= max_retries: return translated
            
            api_key = self.key_manager.get_key()
            if not api_key: return "[LỖI: Thiếu Key]"
            
            try:
                client = genai.Client(api_key=api_key)
                system_instruction = (
                    f"Hiệu đính phụ đề SRT dựa theo bối cảnh: {context}. "
                    "Nhiệm vụ: Sửa lỗi dùng từ, đảm bảo văn phong mượt mà tự nhiên bằng Tiếng Việt. "
                    "Tuyệt đối xuất ra SRT chuẩn, giữ nguyên mốc thời gian."
                )
                prompt = f"[NGUYÊN BẢN]:\n{original}\n\n[BẢN DỊCH THÔ]:\n{translated}"
                response = client.models.generate_content(
                    model='gemini-2.5-flash', 
                    contents=prompt, 
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_instruction, 
                        temperature=0.1
                    )
                )
                
                result_text = response.text.strip()
                if not result_text:
                    raise ValueError("API trả về chuỗi rỗng")
                return result_text
            except:
                time.sleep(4)
                self.key_manager.rotate()
                retries += 1
                continue
                
        return "[ĐÃ DỪNG]"

    def toggle_translation(self):
        if self.is_translating:
            self.stop_event.set(); self.is_translating = False
            self.btn_run.configure(text="▶ BẮT ĐẦU DỊCH", fg_color="#dc3545")
            self.lbl_status.configure(text="Đã dừng.", text_color="red")
        else:
            self.stop_event.clear(); self.is_translating = True
            self.btn_run.configure(text="⏹ DỪNG LẠI", fg_color="#f39c12")
            self.txt_trans.delete("1.0", "end")
            threading.Thread(target=self.run_translation_loop, daemon=True).start()

    def run_translation_loop(self):
        raw_text = self.txt_orig.get("1.0", "end").strip()
        if not raw_text: 
            self.after(0, self.toggle_translation)
            return
            
        raw_blocks = re.split(r'\n\n+', raw_text)
        clean_blocks = [b.strip() for b in raw_blocks if b.strip()]
        
        try: start_index = int(self.entry_start_block.get().strip()) - 1
        except: start_index = 0
        
        clean_blocks = clean_blocks[max(0, start_index):]
        chunks = [clean_blocks[i:i + 15] for i in range(0, len(clean_blocks), 15)]
        
        mode = self.combo_mode.get()
        context = self.entry_context.get().strip()
        provider = self.combo_provider.get()
        model = self.combo_model.get()
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            if self.stop_event.is_set(): break
            
            self.after(0, lambda current=i+1, total=total_chunks: self.lbl_status.configure(
                text=f"Đang dịch: {current}/{total} đoạn...", text_color="#007bff"))
            
            block = "\n\n".join(chunk)
            
            if mode == "Kết hợp (Dịch + Review)":
                if provider == "Gemini": 
                    final_text = self.translate_block_standard(block, context, provider, model)
                else:
                    raw_trans = self.translate_block_standard(block, context, provider, model)
                    final_text = self.review_block_with_gemini(block, raw_trans, context) if "[LỖI:" not in raw_trans else raw_trans
            elif mode == "Chỉ Dịch (Tốc độ cao)": 
                final_text = self.translate_block_standard(block, context, provider, model)
            else: 
                final_text = self.review_block_with_gemini("(Chỉ review)", block, context)

            if final_text:
                self.after(0, lambda b=final_text: self.txt_trans.insert("end", b + "\n\n"))
                self.after(0, lambda: self.txt_trans.see("end"))
                
        if not self.stop_event.is_set():
            self.after(0, lambda: self.lbl_status.configure(text="Hoàn tất bóc tách & dịch!", text_color="#4CAF50"))
            
            auto_save_msg = ""
            if hasattr(self, 'file_path') and self.file_path:
                try:
                    save_path = self.file_path.rsplit('.', 1)[0] + "_translated.srt"
                    content = self.txt_trans.get("1.0", "end").strip()
                    
                    with open(save_path, "w", encoding="utf-8") as f: 
                        f.write(content)
                        
                    auto_save_msg = f"\n\nĐã tự động lưu tại:\n{save_path}"
                except Exception as e:
                    auto_save_msg = f"\n\nLỗi khi tự động lưu: {str(e)}"
            
            self.after(0, lambda: msg.showinfo("Thành công", f"Quá trình dịch đã hoàn tất!{auto_save_msg}"))
            
        self.after(0, self.toggle_translation)

    def on_closing(self):
        self.stop_event.set()
        self.tk_cancel_event.set() 
        self.tk_post_event.set()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()