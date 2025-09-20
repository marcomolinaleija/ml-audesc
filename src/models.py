# -*- coding: utf-8 -*-

class AudioDescriptionItem:
    """Clase para representar un elemento de audiodescripción"""
    def __init__(self, tiempo=0.0, archivo_audio="", descripcion=""):
        self.tiempo = tiempo
        self.archivo_audio = archivo_audio
        self.descripcion = descripcion
