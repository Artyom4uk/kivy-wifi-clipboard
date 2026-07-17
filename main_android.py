import os
import sys
import socket
import threading
import re
import webbrowser
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import StringProperty, ListProperty
from kivy.core.clipboard import Clipboard
from plyer import filechooser as file_chooser
from kivy.clock import Clock
from kivy.core.window import Window

class MainScreen(Screen):
    pass

class HistoryScreen(Screen):
    pass

class FileItem(BoxLayout):
    file_path = StringProperty("")
    file_name = StringProperty("")
    icon_source = StringProperty("")
    icon_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Очищаем путь от скобок, которые ломали lower()
        clean_path = str(self.file_path).strip("()',\"[]")
        ext = os.path.splitext(clean_path).lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            self.icon_source = clean_path
            self.icon_text = ""
        else:
            self.icon_source = ""
            if ext == '.txt': self.icon_text = "📝"
            elif ext in ['.doc', '.docx']: self.icon_text = "🟦"
            elif ext in ['.xls', '.xlsx']: self.icon_text = "🟩"
            elif ext == '.exe': self.icon_text = "⚙️"
            else: self.icon_text = "📄"

    def remove_self(self):
        app = App.get_running_app()
        if self.file_path in app.selected_files:
            app.selected_files.remove(self.file_path)
        self.parent.remove_widget(self)

class HistoryItem(BoxLayout):
    item_text = StringProperty("")
    is_file = False

    def action_press(self):
        clean_text = str(self.item_text).strip("()',\"[]")
        if self.is_file and os.path.exists(clean_text):
            webbrowser.open(f"file://{clean_text}")
        else:
            Clipboard.copy(clean_text)
            App.get_running_app().set_status("Текст скопирован!")

class MainApp(App):
    detected_link = StringProperty("")  
    selected_files = ListProperty([])  
    received_items = ListProperty([])  

    def build(self):
        self.title = "Wi-Fi Обменник (Мобильный)"
        Window.bind(on_key_down=self.on_keyboard_down)
        
        # КРИТИЧЕСКИ ВАЖНО: Принудительный вызов системного окна разрешений Android
        if sys.platform == 'android':
            Clock.schedule_once(self.request_android_permissions, 0)

        threading.Thread(target=self.start_network_server, daemon=True).start()
        
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(HistoryScreen(name='history'))
        return sm

    def request_android_permissions(self, dt):
        """Запрашиваем права у Android всплывающим окном"""
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.INTERNET, 
                Permission.ACCESS_NETWORK_STATE,
                Permission.ACCESS_WIFI_STATE,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE
            ])
        except Exception as e:
            print(f"Ошибка запроса прав: {e}")

    def on_keyboard_down(self, window, key, scancode, codepoint, modifiers):
        if key == 13 and 'ctrl' in modifiers:
            self.send_data()
            return True

    def check_for_links(self, text):
        urls = re.findall(r'(https?://\S+)', text)
        if urls:
            self.detected_link = urls
            self.root.get_screen('main').ids.link_button.opacity = 1
            self.root.get_screen('main').ids.link_button.disabled = False
        else:
            self.detected_link = ""
            self.root.get_screen('main').ids.link_button.opacity = 0
            self.root.get_screen('main').ids.link_button.disabled = True

    def open_link(self):
        if self.detected_link:
            webbrowser.open(self.detected_link)

    def paste_from_system(self):
        self.root.get_screen('main').ids.input_field.text = Clipboard.paste()

    def choose_file(self):
        try:
            file_chooser.open_file(on_selection=self.on_file_selected, multiple=True)
        except Exception as e:
            self.set_status(f"Ошибка проводника: {str(e)}")

    def on_file_selected(self, selection):
        """Очищаем пути Android-проводника"""
        if selection:
            if isinstance(selection, (list, tuple)):
                paths = [str(p).strip("()',\"[]") for p in selection]
            else:
                paths = [str(selection).strip("()',\"[]")]

            for path in paths:
                if path and path not in self.selected_files:
                    self.selected_files.append(path)
                    name = os.path.basename(path)
                    item = FileItem(file_path=path, file_name=name)
                    self.root.get_screen('main').ids.files_scroll_container.add_widget(item)

    def send_data(self):
        text = str(self.root.get_screen('main').ids.input_field.text).strip()
        files = list(self.selected_files)

        if not text and not files:
            self.set_status("Нечего отправлять!")
            return

        threading.Thread(target=self.network_send_worker, args=(text, files), daemon=True).start()

        self.root.get_screen('main').ids.input_field.text = ""
        self.selected_files.clear()
        self.root.get_screen('main').ids.files_scroll_container.clear_widgets()
        self.check_for_links("")
        self.set_status("Отправка на ПК...")

    def network_send_worker(self, text, files):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            if text:
                payload = f"TEXT:{text}".encode('utf-8')
                s.sendto(payload, ('255.255.255.255', 55555))
            
            for f_path in files:
                clean_path = str(f_path).strip("()',\"[]")
                if os.path.exists(clean_path):
                    f_name = os.path.basename(clean_path)
                    with open(clean_path, 'rb') as f:
                        file_data = f.read()
                    payload = b"FILE:" + f_name.encode('utf-8') + b":" + file_data
                    s.sendto(payload, ('255.255.255.255', 55555))
            s.close()
            Clock.schedule_once(lambda dt: self.set_status("Успешно отправлено!"), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"Ошибка сети: {str(e)}"), 0)

    def start_network_server(self):
        udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_server.bind(('0.0.0.0', 55555))
        except:
            return
            
        while True:
            try:
                data, addr = udp_server.recvfrom(1024 * 1024 * 50)
                
                try:
                    hostname = socket.gethostname()
                    my_ips = socket.gethostbyname_ex(hostname)
                except:
                    my_ips = []
                my_ips.extend(['127.0.0.1', 'localhost'])
                
                if addr in my_ips:
                    continue

                if data.startswith(b"TEXT:"):
                    text_msg = data[5:].decode('utf-8')
                    Clock.schedule_once(lambda dt: self.add_to_history(text_msg, is_file=False), 0)
                elif data.startswith(b"FILE:"):
                    parts = data.split(b":", 2)
                    file_name = parts.decode('utf-8')
                    file_bytes = parts
                    
                    save_dir = '/sdcard/Download' if os.path.exists('/sdcard') else './'
                    if not os.path.exists(save_dir): os.makedirs(save_dir)
                    
                    full_path = os.path.join(save_dir, file_name)
                    with open(full_path, 'wb') as f:
                        f.write(file_bytes)
                        
                    Clock.schedule_once(lambda dt: self.add_to_history(full_path, is_file=True), 0)
            except:
                pass

    def add_to_history(self, content, is_file):
        self.received_items.append({"text": content, "is_file": is_file})
        disp_text = f"📁 Файл: {os.path.basename(str(content))}" if is_file else f"💬 Текст: {content}"
        item_widget = HistoryItem(item_text=str(content))
        item_widget.is_file = is_file
        item_widget.ids.display_label.text = disp_text
        self.root.get_screen('history').ids.history_container.add_widget(item_widget)
        self.set_status("Приняты новые данные с ПК!")

    def set_status(self, text):
        self.root.get_screen('main').ids.status_label.text = text

if __name__ == "__main__":
    MainApp().run()
