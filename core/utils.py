import re


def clean_folder_name(name):
    """Quita los caracteres no válidos en nombres de archivo de Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name or '')
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', cleaned).strip().rstrip('.')
    return cleaned or "Lista_Sin_Nombre"
