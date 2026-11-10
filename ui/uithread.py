"""Actualizar la interfaz de Flet desde otros hilos.

Flet envía los cambios a la ventana con una cola de asyncio que no es segura
entre hilos: un control.update() hecho desde un hilo normal se queda en la cola
hasta que el bucle de eventos se despierta por otro motivo, y la interfaz parece
congelada. call_ui() ejecuta la función dentro del propio bucle de eventos.
"""
import logging

logger = logging.getLogger(__name__)


def call_ui(page, fn, *args):
    async def run():
        try:
            fn(*args)
        except Exception:
            logger.exception("Error al actualizar la interfaz")

    try:
        page.run_task(run)
    except Exception:
        logger.exception("No se pudo programar la actualización de la interfaz")
