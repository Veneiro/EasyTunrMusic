import flet as ft

ACCENTS = {
    "orange": ft.Colors.DEEP_ORANGE,  # color del icono de la app
    "red": ft.Colors.RED,
    "indigo": ft.Colors.INDIGO,
    "blue": ft.Colors.BLUE,
    "teal": ft.Colors.TEAL,
    "green": ft.Colors.GREEN,
    "pink": ft.Colors.PINK,
    "purple": ft.Colors.DEEP_PURPLE,
}

THEME_MODES = {
    "system": ft.ThemeMode.SYSTEM,
    "light": ft.ThemeMode.LIGHT,
    "dark": ft.ThemeMode.DARK,
}


def apply(page, config):
    seed = ACCENTS.get(config.get("accent"), ACCENTS["orange"])
    page.theme = ft.Theme(color_scheme_seed=seed, use_material3=True)
    page.dark_theme = ft.Theme(color_scheme_seed=seed, use_material3=True)
    page.theme_mode = THEME_MODES.get(config.get("theme_mode"), ft.ThemeMode.SYSTEM)
