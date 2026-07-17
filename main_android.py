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
from kivy.clock import Clock

class MainScreen(Screen):
    pass

class HistoryScreen(Screen):
    pass

class HistoryItem(BoxLayout):
    """Элемент в окне истории на телефоне"""
    item_text = StringProperty("")
    is_file = False

    def action_press(self):
        clean_text = str(self.item_text).strip("()',\"[]")
        if self.is_file and os.path.exists(clean_text):
            # На Android открываем файл через системный веб-браузер/просмотрщик
            webbrowser.open(f"file://{clean_text}")
        else:
            Clipboard.copy(clean_text)
            App.get_running_app().set_status("Текст скопирован!")

class MainApp(App):
    detected_link = StringProperty("")  
    received_items = ListProperty([])  # Список принятых объектов

    def build(self):
        self.title = "Wi-Fi Обменник (Мобильный)"
        
        # Официальный запрос прав на сеть при старте на Android
        if sys.platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.INTERNET, 
                    Permission.ACCESS_NETWORK_STATE,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE
                ])
            except Exception as e:
                print(f"Ошибка запроса прав: {e}")

        # Запуск фонового сервера приема данных по Wi-Fi
        threading.Thread(target=self.start_network_server, daemon=True).start()
        
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(HistoryScreen(name='history'))
        return sm

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
        """Быстрая вставка текста из буфера обмена телефона"""
        self.root.get_screen('main').ids.input_field.text = Clipboard.paste()

    def send_data(self):
        """Отправка текста с телефона на ПК в изолированном потоке"""
        text = str(self.root.get_screen('main').ids.input_field.text).strip()

        if not text:
            self.set_status("Поле ввода пустое!")
            return

        threading.Thread(target=self.network_send_worker, args=(text,), daemon=True).start()

        self.root.get_screen('main').ids.input_field.text = ""
        self.check_for_links("")
        self.set_status("Отправка на ПК...")

    def network_send_worker(self, text):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            payload = f"TEXT:{text}".encode('utf-8')
            s.sendto(payload, ('255.255.255.255', 55555))
            s.close()
            Clock.schedule_once(lambda dt: self.set_status("Успешно отправлено на ПК!"), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"Ошибка сети: {str(e)}"), 0)

    def start_network_server(self):
        """Сервер приема файлов и текстов с ноутбука"""
        udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_server.bind(('0.0.0.0', 55555))
        except:
            return
            
        while True:
            try:
                data, addr = udp_server.recvfrom(1024 * 1024 * 50) # Лимит 50МБ
                
                # Фильтруем эхо от самого себя, чтобы телефон не принимал свои же сообщения
                try:
                    my_ips = socket.gethostbyname_ex(socket.gethostname())
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
                    file_name = parts[1].decode('utf-8')
                    file_bytes = parts[2]
                    
                    # На Android сохраняем строго в системную папку Download
                    save_dir = '/sdcard/Download' if os.path.exists('/sdcard') else './'
                    if not os.path.exists(save_dir): 
                        os.makedirs(save_dir)
                    
                    full_path = os.path.join(save_dir, file_name)
                    with open(full_path, 'wb') as f:
                        f.write(file_bytes)
                        
                    Clock.schedule_once(lambda dt: self.add_to_history(full_path, is_file=True), 0)
            except:
                pass

    def add_to_history(self, content, is_file):
        self.received_items.append({"text": content, "is_file": is_file})
        disp_text = f"📁 Принят файл: {os.path.basename(str(content))}" if is_file else f"💬 Принят текст: {content}"
        item_widget = HistoryItem(item_text=str(content))
        item_widget.is_file = is_file
        item_widget.ids.display_label.text = disp_text
        self.root.get_screen('history').ids.history_container.add_widget(item_widget)
        self.set_status("Приняты новые данные с ПК!")

    def set_status(self, text):
        self.root.get_screen('main').ids.status_label.text = text

if __name__ == "__main__":
    MainApp().run()
