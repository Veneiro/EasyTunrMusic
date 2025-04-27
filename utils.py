import re

def clean_folder_name(name):
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', cleaned).strip()
    return cleaned if cleaned else "Lista_Sin_Nombre"