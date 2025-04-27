import tkinter as tk
from downloader_app import DownloaderApp
import os
import ctypes

if __name__ == "__main__":
    root = tk.Tk()

    # Ruta al ícono
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    
    # Establecer el ícono de la ventana principal
    root.iconbitmap(icon_path)

    # Establecer el ícono del proceso en la barra de tareas (solo en Windows)
    if os.name == "nt":  # Verifica si el sistema operativo es Windows
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EasyTunrMusic")  # Identificador único
        ctypes.windll.user32.LoadIconW(0, icon_path)
    
    app = DownloaderApp(root)
    root.mainloop()