import webbrowser
import re
import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from plyer import filechooser as file_chooser

class FileItem(BoxLayout):
    """Класс для визуального квадратика файла с динамической иконкой"""
    file_path = StringProperty("")
    file_name = StringProperty("")
    icon_source = StringProperty("")  # Путь к картинке (если это фото)
    icon_text = StringProperty("")    # Эмодзи-иконка (если это документ)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Определяем тип файла по расширению
        ext = os.path.splitext(self.file_path)[1].lower()
        
        # Список популярных расширений картинок
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        
        if ext in image_extensions:
            # Если это картинка, Kivy сам сожмет её в миниатюру
            self.icon_source = self.file_path
            self.icon_text = ""
        else:
            # Если это документ, отключаем картинку и ставим текстовую иконку
            self.icon_source = ""
            if ext == '.txt':
                self.icon_text = "📝"  # Блокнот
            elif ext in ['.doc', '.docx']:
                self.icon_text = "🟦"  # Word (Синий квадратик)
            elif ext in ['.xls', '.xlsx']:
                self.icon_text = "🟩"  # Excel (Зеленый квадратик)
            elif ext == '.exe':
                self.icon_text = "⚙️"  # Настройки/Шестеренка для EXE
            elif ext == '.pdf':
                self.icon_text = "🟥"  # PDF (Красный)
            elif ext in ['.zip', '.rar', '.7z']:
                self.icon_text = "📦"  # Архив
            else:
                self.icon_text = "📄"  # Любой другой файл

    def remove_self(self):
        app = App.get_running_app()
        if self.file_path in app.root.selected_files:
            app.root.selected_files.remove(self.file_path)
        self.parent.remove_widget(self)

class ClipboardWindow(BoxLayout):
    detected_link = StringProperty("")  
    selected_files = ListProperty([])  

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_key_down=self.on_keyboard_down)

    def on_keyboard_down(self, window, key, scancode, codepoint, modifiers):
        if key == 13 and 'ctrl' in modifiers:
            self.send_data()
            return True

    def check_for_links(self, text):
        urls = re.findall(r'(https?://\S+)', text)
        if urls:
            self.detected_link = urls
            self.ids.link_button.opacity = 1
            self.ids.link_button.disabled = False
        else:
            self.detected_link = ""
            self.ids.link_button.opacity = 0
            self.ids.link_button.disabled = True

    def open_link(self):
        if self.detected_link:
            webbrowser.open(self.detected_link)
            self.ids.status_label.text = f"Открываю: {self.detected_link}"

    def paste_from_system(self):
        system_text = Clipboard.paste()
        self.ids.input_field.text = system_text
        self.check_for_links(system_text)
        self.ids.status_label.text = "Текст вставлен!"

    def choose_file(self):
        try:
            file_chooser.open_file(on_selection=self.on_file_selected, multiple=True)
        except Exception as e:
            self.ids.status_label.text = f"Ошибка: {str(e)}"

    def on_file_selected(self, selection):
        if selection:
            for path in selection:
                # Разрешаем добавлять даже файлы с одинаковыми именами, проверяя полный путь
                if path not in self.selected_files:
                    self.selected_files.append(path)
                    name = os.path.basename(path)
                    item = FileItem(file_path=path, file_name=name)
                    self.ids.files_scroll_container.add_widget(item)
            
            self.ids.status_label.text = f"Файлов к отправке: {len(self.selected_files)}"

    def send_data(self):
        text = self.ids.input_field.text.strip()
        files = self.selected_files

        if not text and not files:
            self.ids.status_label.text = "Нечего отправлять!"
            return

        if files:
            print(f"Отправляем файлы: {files}")
        if text:
            print(f"Отправляем текст: {text}")

        self.ids.status_label.text = "Все данные успешно отправлены!"
        
        self.ids.input_field.text = ""
        self.selected_files.clear()
        self.ids.files_scroll_container.clear_widgets()
        self.check_for_links("")

class MainApp(App):
    def build(self):
        self.title = "Wi-Fi Обменник"
        return ClipboardWindow()

if __name__ == "__main__":
    MainApp().run()
