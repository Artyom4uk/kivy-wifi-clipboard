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

# Если программа запущена как .exe, ищем main.kv во временной папке
if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

class MainScreen(Screen):
    """Главный экран для отправки текста и файлов"""
    pass

class HistoryScreen(Screen):
    """Экран со списком всех принятых файлов и текстов"""
    pass

class FileItem(BoxLayout):
    """Визуальная плиточка файла для отправки"""
    file_path = StringProperty("")
    file_name = StringProperty("")
    icon_source = StringProperty("")
    icon_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ext = os.path.splitext(self.file_path).lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            self.icon_source = self.file_path
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
    """Строка в истории принятого (текст или путь к файлу)"""
    item_text = StringProperty("")
    is_file = False

    def action_press(self):
        """При нажатии: открывает файл или копирует текст в буфер"""
        if self.is_file and os.path.exists(self.item_text):
            # Открываем принятый файл в системе
            if sys.platform == 'win32': os.startfile(self.item_text)
            else: webbrowser.open(self.item_text)
        else:
            Clipboard.copy(self.item_text)
            App.get_running_app().root.get_screen('main').ids.status_label.text = "Текст скопирован в буфер!"

class MainApp(App):
    detected_link = StringProperty("")  
    selected_files = ListProperty([])  
    received_items = ListProperty([])  # Список принятых объектов

    def build(self):
        self.title = "Wi-Fi Обменник PRO"
        
        # Запускаем фоновый сетевой сервер для приема данных
        threading.Thread(target=self.start_network_server, daemon=True).start()
        
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(HistoryScreen(name='history'))
        return sm

    def check_for_links(self, text):
        urls = re.findall(r'(https?://\S+)', text)
        if urls:
            self.detected_link = urls[0]
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
        system_text = Clipboard.paste()
        self.root.get_screen('main').ids.input_field.text = system_text

    def choose_file(self):
        try:
            file_chooser.open_file(on_selection=self.on_file_selected, multiple=True)
        except Exception as e:
            self.root.get_screen('main').ids.status_label.text = f"Ошибка проводника: {str(e)}"

    def on_file_selected(self, selection):
        if selection:
            for path in selection:
                if path not in self.selected_files:
                    self.selected_files.append(path)
                    name = os.path.basename(path)
                    item = FileItem(file_path=path, file_name=name)
                    self.root.get_screen('main').ids.files_scroll_container.add_widget(item)

    def send_data(self):
        """Функция отправки данных по локальной сети Wi-Fi"""
        text = self.root.get_screen('main').ids.input_field.text.strip()
        files = self.selected_files

        if not text and not files:
            self.root.get_screen('main').ids.status_label.text = "Нечего отправлять!"
            return

        # Находим IP-адрес второго устройства (сканируем локалку или шлем бродкаст)
        threading.Thread(target=self.network_send_worker, args=(text, list(files)), daemon=True).start()

        # Очищаем интерфейс
        self.root.get_screen('main').ids.input_field.text = ""
        self.selected_files.clear()
        self.root.get_screen('main').ids.files_scroll_container.clear_widgets()
        self.check_for_links("")
        self.root.get_screen('main').ids.status_label.text = "Отправка..."

    def network_send_worker(self, text, files):
        """Фоновый поток для отправки данных без зависания интерфейса"""
        try:
            # Ищем все устройства в домашней сети на порту 55555
            # Для упрощения шлем на широковещательный адрес локалки (Broadcast)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Формируем пакет данных: Сначала текст
            if text:
                payload = f"TEXT:{text}".encode('utf-8')
                s.sendto(payload, ('255.255.255.255', 55555))
            
            # Отправка файлов
            for f_path in files:
                if os.path.exists(f_path):
                    f_name = os.path.basename(f_path)
                    with open(f_path, 'rb') as f:
                        file_data = f.read()
                    # Пакет файла: FILE : имя_файла : содержимое
                    payload = b"FILE:" + f_name.encode('utf-8') + b":" + file_data
                    s.sendto(payload, ('255.255.255.255', 55555))

            Clock.schedule_once(lambda dt: self.set_status("Успешно отправлено по Wi-Fi!"), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"Ошибка сети: {str(e)}"), 0)

    def start_network_server(self):
        """Фоновый сервер, который слушает Wi-Fi сеть и принимает данные"""
        udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Биндимся на порт 55555 для приема сообщений со всех IP
        try:
            udp_server.bind(('0.0.0.0', 55555))
        except:
            return # Порт занят
            
        while True:
            try:
                data, addr = udp_server.recvfrom(1024 * 1024 * 50) # Лимит 50МБ на пакет
                if data.startswith(b"TEXT:"):
                    text_msg = data[5:].decode('utf-8')
                    Clock.schedule_once(lambda dt: self.add_to_history(text_msg, is_file=False), 0)
                elif data.startswith(b"FILE:"):
                    # Разбиваем байты по разделителю
                    parts = data.split(b":", 2)
                    file_name = parts[1].decode('utf-8')
                    file_bytes = parts[2]
                    
                    # Путь для сохранения: в папку Загрузки (работает и на ПК, и на Android)
                    save_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
                    if not os.path.exists(save_dir): os.makedirs(save_dir)
                    
                    full_path = os.path.join(save_dir, file_name)
                    with open(full_path, 'wb') as f:
                        f.write(file_bytes)
                        
                    Clock.schedule_once(lambda dt: self.add_to_history(full_path, is_file=True), 0)
            except:
                pass

    def add_to_history(self, content, is_file):
        """Добавляет элемент в окно истории и обновляет счетчик"""
        self.received_items.append({"text": content, "is_file": is_file})
        
        # Создаем виджет строки истории
        disp_text = f"📁 Файл: {os.path.basename(content)}" if is_file else f"💬 Текст: {content}"
        item_widget = HistoryItem(item_text=content)
        item_widget.ids.display_label.text = disp_text
        
        self.root.get_screen('history').ids.history_container.add_widget(item_widget)
        self.set_status(f"Приняты новые данные! Всего в истории: {len(self.received_items)}")

    def set_status(self, text):
        self.root.get_screen('main').ids.status_label.text = text

if __name__ == "__main__":
    MainApp().run()
