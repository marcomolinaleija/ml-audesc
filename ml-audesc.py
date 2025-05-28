# -*- coding: utf-8 -*-
"""
Generador de Audiodescripciones para Video - Interfaz Gráfica
Permite crear audiodescripciones personalizadas con interfaz visual intuitiva.

Dependencias:
pip install wxpython moviepy
"""

import wx
import wx.adv # Importar para el diálogo "Acerca de"
import os
import sys
import json
import threading
import time
from pathlib import Path
import subprocess # Para abrir archivos con el reproductor predeterminado

# Intentar importar MoviePy
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

class AudioDescriptionItem:
    """Clase para representar un elemento de audiodescripción"""
    def __init__(self, tiempo=0.0, archivo_audio="", descripcion=""):
        self.tiempo = tiempo  # Tiempo en segundos
        self.archivo_audio = archivo_audio
        self.descripcion = descripcion

class TimeInputDialog(wx.Dialog):
    """
    Diálogo para que el usuario ingrese el tiempo en formato HH:MM:SS o segundos.
    """
    def __init__(self, parent, video_duration_seconds=0.0):
        super().__init__(parent, title="Ingresar Tiempo", size=(350, 200))
        self.video_duration_seconds = video_duration_seconds
        self.time_in_seconds = 0.0

        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Entrada para el tiempo en formato HH:MM:SS
        time_format_label = wx.StaticText(panel, label="Tiempo (HH:MM:SS):")
        self.time_text_ctrl = wx.TextCtrl(panel, value="00:00:00")
        self.time_text_ctrl.Bind(wx.EVT_TEXT, self.on_time_text_change)

        # Entrada para el tiempo en segundos
        seconds_label = wx.StaticText(panel, label="Tiempo (segundos):")
        self.seconds_spin_ctrl = wx.SpinCtrlDouble(panel, value="0.0", min=0, max=self.video_duration_seconds, inc=0.1)
        self.seconds_spin_ctrl.SetDigits(1)
        self.seconds_spin_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_seconds_spin_change)

        # Botones
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "&Aceptar")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "&Cancelar")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        main_sizer.Add(time_format_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.time_text_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(seconds_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.seconds_spin_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        panel.SetSizer(main_sizer)
        self.CenterOnParent()

        # Inicializar el spin control con la duración máxima del video
        self.seconds_spin_ctrl.SetRange(0, self.video_duration_seconds)

    def on_time_text_change(self, event):
        """Actualiza el spin control de segundos cuando se cambia el texto HH:MM:SS."""
        time_str = self.time_text_ctrl.GetValue()
        try:
            parts = list(map(int, time_str.split(':')))
            if len(parts) == 3:
                h, m, s = parts
            elif len(parts) == 2:
                h, m = 0, parts[0]
                s = parts[1]
            elif len(parts) == 1:
                h, m = 0, 0
                s = parts[0]
            else:
                raise ValueError("Formato de tiempo inválido")

            total_seconds = h * 3600 + m * 60 + s
            if 0 <= total_seconds <= self.video_duration_seconds:
                self.seconds_spin_ctrl.SetValue(total_seconds)
                self.time_in_seconds = total_seconds
            else:
                # Si el tiempo excede la duración del video, ajustarlo al máximo
                self.seconds_spin_ctrl.SetValue(self.video_duration_seconds)
                self.time_in_seconds = self.video_duration_seconds
                wx.MessageBox(f"El tiempo excede la duración del video ({self.format_time(self.video_duration_seconds)}). Se ajustó al máximo.",
                              "Advertencia de Tiempo", wx.OK | wx.ICON_WARNING)
        except ValueError:
            # Ignorar errores de formato mientras el usuario escribe
            pass

    def on_seconds_spin_change(self, event):
        """Actualiza el texto HH:MM:SS cuando se cambia el spin control de segundos."""
        self.time_in_seconds = self.seconds_spin_ctrl.GetValue()
        self.time_text_ctrl.SetValue(self.format_time(self.time_in_seconds))

    def get_time_in_seconds(self):
        return self.time_in_seconds

    def format_time(self, seconds):
        """Formatea segundos a HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"

class FileDropTarget(wx.FileDropTarget):
    """Clase para manejar el arrastre y soltado de archivos."""
    def __init__(self, window, callback):
        wx.FileDropTarget.__init__(self)
        self.window = window
        self.callback = callback

    def OnDropFiles(self, x, y, filenames):
        """Se llama cuando se sueltan archivos sobre el objetivo."""
        if filenames and len(filenames) == 1:
            self.callback(filenames[0])
            return True
        else:
            wx.MessageBox("Por favor, arrastra solo un archivo de video a la vez.",
                          "Error de Arrastre y Suelta", wx.OK | wx.ICON_ERROR)
            return False

class MainFrame(wx.Frame):
    """Ventana principal de la aplicación"""
    def __init__(self):
        super().__init__(None, title="Generador de Audiodescripciones", size=(1000, 700))
        self.app_title_base = "Generador de Audiodescripciones" # Título base de la aplicación
        self.current_project_name = None # Para almacenar el nombre del proyecto actual (sin extensión)

        self.video_file = ""
        self.video_duration = 0.0 # Duración del video en segundos
        self.audiodescriptions = []
        self.temp_preview_files = [] # Lista para almacenar rutas de archivos temporales de previsualización

        self.init_ui()
        self.check_dependencies()
        self.load_project_state() # Cargar el estado del proyecto al iniciar
        self.Bind(wx.EVT_CLOSE, self.save_project_state_and_exit) # Guardar estado y limpiar al cerrar

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Menú de la aplicación
        menu_bar = wx.MenuBar()

        # Menú Archivo
        file_menu = wx.Menu()
        save_as_item = file_menu.Append(wx.ID_SAVEAS, "&Guardar proyecto como...", "Guardar el proyecto actual con un nuevo nombre")
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "&Cerrar\tAlt+F4", "Cerrar la aplicación")
        self.Bind(wx.EVT_MENU, self.on_save_as_project, save_as_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        menu_bar.Append(file_menu, "&Archivo")

        # Menú Ayuda
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "&Acerca de...", "Información sobre esta aplicación")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menu_bar.Append(help_menu, "&Ayuda")
        self.SetMenuBar(menu_bar)

        # Título
        title = wx.StaticText(panel, label="Generador de Audiodescripciones para Video")
        title_font = wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)

        # Sección de archivo de video
        video_box = wx.StaticBox(panel, label="Archivo de Video")
        video_sizer = wx.StaticBoxSizer(video_box, wx.HORIZONTAL)

        self.video_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        # Configurar arrastrar y soltar para el control de video
        dt = FileDropTarget(self.video_ctrl, self.on_drop_video_file)
        self.video_ctrl.SetDropTarget(dt)

        video_browse_btn = wx.Button(panel, label="&Seleccionar Video...")
        video_browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_video)

        self.video_duration_label = wx.StaticText(panel, label="Duración: 00:00:00")

        video_sizer.Add(self.video_ctrl, 1, wx.ALL|wx.EXPAND, 5)
        video_sizer.Add(video_browse_btn, 0, wx.ALL, 5)
        video_sizer.Add(self.video_duration_label, 0, wx.ALL|wx.CENTER, 5)

        # Sección de audiodescripciones
        audio_box = wx.StaticBox(panel, label="Audiodescripciones")
        audio_sizer = wx.StaticBoxSizer(audio_box, wx.VERTICAL)

        # Botones de control
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="&Agregar Audiodescripción")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_audiodescription)

        import_btn = wx.Button(panel, label="&Importar Proyecto")
        import_btn.Bind(wx.EVT_BUTTON, self.on_import_project)

        export_btn = wx.Button(panel, label="&Exportar Proyecto")
        export_btn.Bind(wx.EVT_BUTTON, self.on_export_project)

        clear_btn = wx.Button(panel, label="&Limpiar Proyecto")
        clear_btn.Bind(wx.EVT_BUTTON, self.on_clear_project)

        control_sizer.Add(add_btn, 0, wx.ALL, 5)
        control_sizer.Add(import_btn, 0, wx.ALL, 5)
        control_sizer.Add(export_btn, 0, wx.ALL, 5)
        control_sizer.Add(clear_btn, 0, wx.ALL, 5)

        # ListCtrl para mostrar las audiodescripciones
        self.ad_list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES)
        self.ad_list_ctrl.InsertColumn(0, "Tiempo", width=100)
        self.ad_list_ctrl.InsertColumn(1, "Archivo de Audio", width=300)
        self.ad_list_ctrl.InsertColumn(2, "Descripción", width=400)
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit_audiodescription) # Doble click para editar

        # Manejar selección de elementos para habilitar/deshabilitar botones
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_ad_list_selection_change)
        self.ad_list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_ad_list_selection_change)


        # Nuevo sizer para la lista y los botones de acción
        list_and_buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        list_and_buttons_sizer.Add(self.ad_list_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        # Botones para editar/eliminar audiodescripciones
        ad_action_buttons_sizer = wx.BoxSizer(wx.VERTICAL)
        self.edit_ad_btn = wx.Button(panel, label="&Editar")
        self.edit_ad_btn.Bind(wx.EVT_BUTTON, self.on_edit_audiodescription)
        self.edit_ad_btn.Enable(False) # Inicialmente deshabilitado

        self.delete_ad_btn = wx.Button(panel, label="&Borrar")
        self.delete_ad_btn.Bind(wx.EVT_BUTTON, self.on_remove_audiodescription_from_list)
        self.delete_ad_btn.Enable(False) # Inicialmente deshabilitado

        ad_action_buttons_sizer.Add(self.edit_ad_btn, 0, wx.ALL, 5)
        ad_action_buttons_sizer.Add(self.delete_ad_btn, 0, wx.ALL, 5)

        list_and_buttons_sizer.Add(ad_action_buttons_sizer, 0, wx.EXPAND | wx.ALL, 5)

        audio_sizer.Add(control_sizer, 0, wx.ALL, 5)
        audio_sizer.Add(list_and_buttons_sizer, 1, wx.ALL|wx.EXPAND, 5) # Usar el nuevo sizer aquí

        # Configuración de salida
        output_box = wx.StaticBox(panel, label="Configuración de Salida")
        output_sizer = wx.StaticBoxSizer(output_box, wx.HORIZONTAL)

        output_label = wx.StaticText(panel, label="Archivo de salida:")
        self.output_ctrl = wx.TextCtrl(panel, value="video_con_audiodescripcion.mp4")

        vol_orig_label = wx.StaticText(panel, label="Volumen original:")
        self.vol_orig_ctrl = wx.SpinCtrlDouble(panel, value="0.6", min=0, max=2, inc=0.1)
        self.vol_orig_ctrl.SetDigits(1)

        vol_desc_label = wx.StaticText(panel, label="Volumen descripción:")
        self.vol_desc_ctrl = wx.SpinCtrlDouble(panel, value="1.5", min=0, max=3, inc=0.1)
        self.vol_desc_ctrl.SetDigits(1)

        output_sizer.Add(output_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.output_ctrl, 1, wx.ALL|wx.EXPAND, 5)
        output_sizer.Add(vol_orig_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.vol_orig_ctrl, 0, wx.ALL, 5)
        output_sizer.Add(vol_desc_label, 0, wx.ALL|wx.CENTER, 5)
        output_sizer.Add(self.vol_desc_ctrl, 0, wx.ALL, 5)

        # Botones de acción final (Generar y Previsualizar)
        final_action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.generate_btn = wx.Button(panel, label="&Generar Video con Audiodescripción")
        self.generate_btn.Bind(wx.EVT_BUTTON, self.on_generate)
        final_action_sizer.Add(self.generate_btn, 0, wx.ALL, 5)

        self.preview_btn = wx.Button(panel, label="&Previsualizar Video")
        self.preview_btn.Bind(wx.EVT_BUTTON, self.on_preview_video)
        self.preview_btn.Enable(False) # Deshabilitado hasta que haya video y descripciones
        final_action_sizer.Add(self.preview_btn, 0, wx.ALL, 5)


        # Barra de progreso
        self.progress = wx.Gauge(panel, range=100)
        self.status_text = wx.StaticText(panel, label="Listo")

        # Layout principal
        main_sizer.Add(title, 0, wx.ALL|wx.CENTER, 10)
        main_sizer.Add(video_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(audio_sizer, 1, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(output_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(final_action_sizer, 0, wx.ALL|wx.CENTER, 10) # Usar el nuevo sizer aquí
        main_sizer.Add(self.progress, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(self.status_text, 0, wx.ALL, 5)

        panel.SetSizer(main_sizer)

        # Centrar ventana
        self.Center()

    def check_dependencies(self):
        """Verifica si MoviePy está instalado y deshabilita la generación si no."""
        if not MOVIEPY_AVAILABLE:
            wx.MessageBox(
                "MoviePy no está instalado.\n\n"
                "Instala las dependencias:\n"
                "pip install moviepy\n\n"
                "Algunas funciones no estarán disponibles.",
                "Dependencias faltantes",
                wx.OK | wx.ICON_WARNING
            )
            self.generate_btn.Enable(False)
            self.preview_btn.Enable(False) # También deshabilitar previsualizar

    def on_about(self, event):
        """Muestra el diálogo 'Acerca de' la aplicación."""
        info = wx.adv.AboutDialogInfo()
        info.SetName(self.app_title_base)
        info.SetVersion("1.0.0")
        info.SetDescription("Herramienta para generar audiodescripciones personalizadas para videos.")
        info.SetCopyright("(C) 2025 MarcoML")
        info.AddDeveloper("MarcoML")
        info.SetWebSite("https://web.marco-ml.com") # Tu sitio web, carnal
        wx.adv.AboutBox(info)

    def on_exit(self, event):
        """Cierra la aplicación."""
        self.Close() # Esto activará el evento EVT_CLOSE y save_project_state_and_exit

    def on_browse_video(self, event):
        """Maneja la selección del archivo de video y obtiene su duración."""
        wildcard = "Archivos de video (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv"
        with wx.FileDialog(self, "Seleccionar archivo de video",
                          wildcard=wildcard,
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.on_drop_video_file(dialog.GetPath()) # Reutilizar la lógica de carga

    def on_drop_video_file(self, file_path):
        """Maneja el archivo de video arrastrado y soltado o seleccionado."""
        self.video_file = file_path
        self.video_ctrl.SetValue(self.video_file)

        # Obtener duración del video
        self.update_video_duration() # Llamar a la nueva función para actualizar la duración

        # Actualizar nombre de salida por defecto
        video_path = Path(self.video_file)
        output_name = f"{video_path.stem}_con_audiodescripcion{video_path.suffix}"
        self.output_ctrl.SetValue(output_name)
        self.update_action_buttons_state() # Actualizar estado de botones de acción

    def update_video_duration(self):
        """Recalcula y actualiza la duración del video."""
        if self.video_file and os.path.exists(self.video_file):
            try:
                video_clip = VideoFileClip(self.video_file)
                self.video_duration = video_clip.duration
                video_clip.close() # Liberar el archivo
                self.video_duration_label.SetLabel(f"Duración: {self.format_time(self.video_duration)}")
            except Exception as e:
                self.video_duration = 0.0
                self.video_duration_label.SetLabel("Duración: Error")
                wx.MessageBox(f"No se pudo obtener la duración del video: {str(e)}",
                              "Error de Video", wx.OK | wx.ICON_ERROR)
        else:
            self.video_duration = 0.0
            self.video_duration_label.SetLabel("Duración: N/A")
        self.update_action_buttons_state() # Asegurar que los botones se actualicen después de cambiar la duración

    def on_add_audiodescription(self, event):
        """Abre un diálogo para agregar una nueva audiodescripción."""
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Primero selecciona un archivo de video válido para obtener su duración.",
                          "Error", wx.OK | wx.ICON_ERROR)
            return

        with TimeInputDialog(self, self.video_duration) as time_dialog:
            if time_dialog.ShowModal() == wx.ID_OK:
                tiempo_seleccionado = time_dialog.get_time_in_seconds()

                # Pedir archivo de audio
                wildcard = "Archivos de audio (*.wav;*.mp3;*.m4a;*.aac)|*.wav;*.mp3;*.m4a;*.aac"
                with wx.FileDialog(self, "Seleccionar archivo de audio",
                                  wildcard=wildcard,
                                  style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as audio_dialog:
                    if audio_dialog.ShowModal() == wx.ID_OK:
                        audio_path = audio_dialog.GetPath()
                        # Opcional: pedir descripción de texto
                        desc_text = wx.GetTextFromUser("Ingresa una breve descripción (opcional):",
                                                       "Descripción de Audiodescripción", "")

                        item = AudioDescriptionItem(tiempo=tiempo_seleccionado,
                                                    archivo_audio=audio_path,
                                                    descripcion=desc_text)
                        self.audiodescriptions.append(item)
                        self.update_ad_list_ctrl()
                        self.update_action_buttons_state() # Actualizar estado de botones de acción
                    else:
                        wx.MessageBox("No se seleccionó archivo de audio. Audiodescripción no agregada.",
                                      "Advertencia", wx.OK | wx.ICON_WARNING)
            else:
                wx.MessageBox("No se ingresó el tiempo. Audiodescripción no agregada.",
                              "Advertencia", wx.OK | wx.ICON_WARNING)

    def on_edit_audiodescription(self, event):
        """Maneja la edición de una audiodescripción existente."""
        index = self.ad_list_ctrl.GetFirstSelected()
        if index != wx.NOT_FOUND:
            item_to_edit = self.audiodescriptions[index]

            if not self.video_file or not os.path.exists(self.video_file):
                wx.MessageBox("No hay un archivo de video válido cargado para editar la descripción.",
                              "Error", wx.OK | wx.ICON_ERROR)
                return

            with TimeInputDialog(self, self.video_duration) as time_dialog:
                # Establecer el tiempo actual en el diálogo
                time_dialog.seconds_spin_ctrl.SetValue(item_to_edit.tiempo)
                time_dialog.time_text_ctrl.SetValue(time_dialog.format_time(item_to_edit.tiempo))

                if time_dialog.ShowModal() == wx.ID_OK:
                    item_to_edit.tiempo = time_dialog.get_time_in_seconds()

                    # Pedir archivo de audio (opcional, si quiere cambiarlo)
                    wildcard = "Archivos de audio (*.wav;*.mp3;*.m4a;*.aac)|*.wav;*.mp3;*.m4a;*.aac"
                    with wx.FileDialog(self, "Seleccionar nuevo archivo de audio (opcional)",
                                      wildcard=wildcard,
                                      defaultDir=os.path.dirname(item_to_edit.archivo_audio) if item_to_edit.archivo_audio else "",
                                      defaultFile=os.path.basename(item_to_edit.archivo_audio) if item_to_edit.archivo_audio else "",
                                      style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as audio_dialog:
                        if audio_dialog.ShowModal() == wx.ID_OK:
                            item_to_edit.archivo_audio = audio_dialog.GetPath()

                    # Pedir descripción de texto
                    new_desc_text = wx.GetTextFromUser("Edita la descripción:",
                                                       "Descripción de Audiodescripción",
                                                       item_to_edit.descripcion)
                    if new_desc_text is not None: # Si el usuario no cancela el diálogo de texto
                        item_to_edit.descripcion = new_desc_text

                    self.update_ad_list_ctrl()

    def on_ad_list_selection_change(self, event):
        """Habilita/deshabilita los botones de edición/eliminación según la selección."""
        selected_count = self.ad_list_ctrl.GetSelectedItemCount()
        self.edit_ad_btn.Enable(selected_count > 0)
        self.delete_ad_btn.Enable(selected_count > 0)
        event.Skip() # Importante para que el evento se siga procesando

    def on_remove_audiodescription_from_list(self, event):
        """Elimina la audiodescripción seleccionada de la lista con confirmación."""
        index = self.ad_list_ctrl.GetFirstSelected()
        if index != wx.NOT_FOUND:
            # Pedir confirmación al usuario
            confirm_dialog = wx.MessageBox(
                "¿Estás seguro de que quieres eliminar esta audiodescripción?",
                "Confirmar Eliminación",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if confirm_dialog == wx.YES:
                del self.audiodescriptions[index]
                self.update_ad_list_ctrl()
                self.update_action_buttons_state() # Actualizar estado de botones de acción
            else:
                wx.MessageBox("Operación cancelada.", "Información", wx.OK | wx.ICON_INFORMATION)

    def update_ad_list_ctrl(self):
        """Actualiza el ListCtrl con las audiodescripciones actuales."""
        self.ad_list_ctrl.DeleteAllItems()
        # Ordenar por tiempo antes de mostrar
        sorted_descriptions = sorted(self.audiodescriptions, key=lambda x: x.tiempo)
        self.audiodescriptions = sorted_descriptions # Actualizar la lista interna también

        has_items = len(self.audiodescriptions) > 0
        self.edit_ad_btn.Enable(has_items) # Habilitar/deshabilitar botones según si hay elementos
        self.delete_ad_btn.Enable(has_items)

        for item in self.audiodescriptions:
            index = self.ad_list_ctrl.InsertItem(self.ad_list_ctrl.GetItemCount(), self.format_time(item.tiempo))
            self.ad_list_ctrl.SetItem(index, 1, os.path.basename(item.archivo_audio))
            self.ad_list_ctrl.SetItem(index, 2, item.descripcion)

        self.update_action_buttons_state() # Asegurar que los botones de acción final se actualicen

    def update_action_buttons_state(self):
        """Actualiza el estado de los botones de Generar y Previsualizar."""
        # Convertir el resultado de la condición a un booleano explícitamente
        can_generate = bool(MOVIEPY_AVAILABLE and self.video_file and os.path.exists(self.video_file) and self.audiodescriptions)
        self.generate_btn.Enable(can_generate)
        self.preview_btn.Enable(can_generate) # Habilitar previsualizar si se puede generar

    def get_project_state_path(self):
        """Obtiene la ruta para guardar/cargar el estado del proyecto."""
        app_data_dir = wx.StandardPaths.Get().GetUserDataDir()
        if not os.path.exists(app_data_dir):
            os.makedirs(app_data_dir)
        return os.path.join(app_data_dir, "audiodescription_project_autosave.json")

    def save_project_state_and_exit(self, event):
        """Guarda el estado actual del proyecto automáticamente y limpia archivos temporales antes de cerrar."""
        self.save_project_state()
        self.clean_temp_files() # Llama a la nueva función de limpieza
        event.Skip() # Permitir que la ventana se cierre

    def save_project_state(self, file_path=None):
        """Guarda el estado actual del proyecto."""
        data = {
            'video_file': self.video_file,
            'audiodescriptions': [
                {'tiempo': item.tiempo, 'archivo_audio': item.archivo_audio, 'descripcion': item.descripcion}
                for item in self.audiodescriptions
            ],
            'output_file': self.output_ctrl.GetValue(),
            'volume_original': self.vol_orig_ctrl.GetValue(),
            'volume_description': self.vol_desc_ctrl.GetValue()
        }
        try:
            if file_path is None: # Guardado automático
                file_path = self.get_project_state_path()
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("Estado del proyecto guardado automáticamente.")
            else: # Guardar como...
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.status_text.SetLabel(f"Proyecto guardado como: {os.path.basename(file_path)}")
                self.current_project_name = Path(file_path).stem # Actualizar el nombre del proyecto actual
                self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")
                print(f"Proyecto guardado como: {file_path}")

        except Exception as e:
            print(f"Error al guardar el estado del proyecto: {e}")
            wx.MessageBox(f"Error al guardar el proyecto: {str(e)}",
                          "Error de Guardado", wx.OK | wx.ICON_ERROR)


    def load_project_state(self):
        """Carga el estado del proyecto guardado automáticamente al inicio."""
        project_state_path = self.get_project_state_path()
        if os.path.exists(project_state_path):
            try:
                with open(project_state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.video_file = data.get('video_file', '')
                self.video_ctrl.SetValue(self.video_file)
                self.output_ctrl.SetValue(data.get('output_file', 'video_con_audiodescripcion.mp4'))
                self.vol_orig_ctrl.SetValue(data.get('volume_original', 0.6))
                self.vol_desc_ctrl.SetValue(data.get('volume_description', 1.5))

                self.audiodescriptions.clear()
                for desc_data in data.get('audiodescriptions', []):
                    item = AudioDescriptionItem(
                        tiempo=desc_data.get('tiempo', 0),
                        archivo_audio=desc_data.get('archivo_audio', ''),
                        descripcion=desc_data.get('descripcion', '')
                    )
                    self.audiodescriptions.append(item)

                self.update_ad_list_ctrl()
                self.update_video_duration() # Recalcular duración del video al cargar el estado

                # Actualizar título de la ventana para proyecto anterior
                if self.video_file or self.audiodescriptions:
                    self.current_project_name = "Proyecto anterior"
                    self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")
                else:
                    self.current_project_name = None
                    self.SetTitle(self.app_title_base) # Restablecer a título base si no hay proyecto cargado

                self.update_action_buttons_state() # Actualizar estado de botones de acción
                self.status_text.SetLabel("Estado del proyecto cargado automáticamente.")

            except Exception as e:
                print(f"Error al cargar el estado del proyecto: {e}")
                wx.MessageBox(f"Error al cargar el proyecto guardado automáticamente: {str(e)}",
                              "Error de Carga", wx.OK | wx.ICON_ERROR)
                self.current_project_name = None
                self.SetTitle(self.app_title_base) # Restablecer a título base si hay error
        else:
            self.current_project_name = None
            self.SetTitle(self.app_title_base) # Asegurar título base si no existe archivo de estado

    def on_import_project(self, event):
        """Importa un proyecto de audiodescripciones desde un archivo JSON."""
        with wx.FileDialog(self, "Importar proyecto",
                          wildcard="Archivos JSON (*.json)|*.json",
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                project_path = dialog.GetPath()
                try:
                    with open(project_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Limpiar audiodescripciones actuales
                    self.audiodescriptions.clear()

                    # Cargar datos
                    self.video_file = data.get('video_file', '')
                    self.video_ctrl.SetValue(self.video_file)
                    self.output_ctrl.SetValue(data.get('output_file', ''))
                    self.vol_orig_ctrl.SetValue(data.get('volume_original', 0.6))
                    self.vol_desc_ctrl.SetValue(data.get('volume_description', 1.5))

                    self.update_video_duration() # Recalcular duración del video al importar

                    # Cargar audiodescripciones
                    for desc_data in data.get('audiodescriptions', []):
                        item = AudioDescriptionItem(
                            tiempo=desc_data.get('tiempo', 0),
                            archivo_audio=desc_data.get('archivo_audio', ''),
                            descripcion=desc_data.get('descripcion', '')
                        )
                        self.audiodescriptions.append(item)

                    self.update_ad_list_ctrl()
                    self.status_text.SetLabel("Proyecto importado correctamente")

                    # Actualizar el título de la ventana con el nombre del proyecto (sin extensión)
                    self.current_project_name = Path(project_path).stem
                    self.SetTitle(f"{self.current_project_name} - {self.app_title_base}")
                    self.update_action_buttons_state() # Actualizar estado de botones de acción

                except Exception as e:
                    wx.MessageBox(f"Error al importar proyecto: {str(e)}",
                                "Error", wx.OK | wx.ICON_ERROR)
                    self.current_project_name = None
                    self.SetTitle(self.app_title_base) # Restablecer a título base si hay error

    def on_export_project(self, event):
        """Exporta el proyecto de audiodescripciones a un archivo JSON."""
        with wx.FileDialog(self, "Exportar proyecto",
                          wildcard="Archivos JSON (*.json)|*.json",
                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.save_project_state(dialog.GetPath()) # Reutilizar la función de guardado

    def on_save_as_project(self, event):
        """Guarda el proyecto actual con un nuevo nombre."""
        with wx.FileDialog(self, "Guardar proyecto como...",
                          wildcard="Archivos JSON (*.json)|*.json",
                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.save_project_state(dialog.GetPath())

    def on_clear_project(self, event):
        """Limpia todos los datos del proyecto actual."""
        confirm_dialog = wx.MessageBox(
            "¿Estás seguro de que quieres limpiar todo el proyecto actual?",
            "Confirmar Limpieza",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if confirm_dialog == wx.YES:
            self.video_file = ""
            self.video_duration = 0.0
            self.audiodescriptions.clear()

            self.video_ctrl.SetValue("")
            self.video_duration_label.SetLabel("Duración: 00:00:00")
            self.output_ctrl.SetValue("video_con_audiodescripcion.mp4")
            self.vol_orig_ctrl.SetValue(0.6)
            self.vol_desc_ctrl.SetValue(1.5)

            self.update_ad_list_ctrl() # Esto también deshabilitará los botones
            self.status_text.SetLabel("Proyecto limpiado.")
            self.current_project_name = None # Limpiar el nombre del proyecto actual
            self.SetTitle(self.app_title_base) # Restablecer el título de la ventana
            self.update_action_buttons_state() # Actualizar estado de botones de acción
        else:
            wx.MessageBox("Operación cancelada.", "Información", wx.OK | wx.ICON_INFORMATION)

    def on_generate(self, event):
        """Inicia el proceso de generación del video en un hilo separado."""
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Selecciona un archivo de video válido primero",
                         "Error", wx.OK | wx.ICON_ERROR)
            return

        if not self.audiodescriptions:
            wx.MessageBox("Agrega al menos una audiodescripción",
                         "Error", wx.OK | wx.ICON_ERROR)
            return

        if not MOVIEPY_AVAILABLE:
            wx.MessageBox("MoviePy no está disponible. Instala las dependencias.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return

        # Validar archivos de audio
        missing_files = []
        for item in self.audiodescriptions:
            if not item.archivo_audio or not os.path.exists(item.archivo_audio):
                missing_files.append(f"Tiempo {self.format_time(item.tiempo)}: {os.path.basename(item.archivo_audio)}")

        if missing_files:
            message = "Los siguientes archivos de audio no existen o no son accesibles:\n\n" + "\n".join(missing_files)
            wx.MessageBox(message, "Archivos faltantes", wx.OK | wx.ICON_ERROR)
            return

        # Ejecutar generación en hilo separado
        self.generate_btn.Enable(False)
        self.preview_btn.Enable(False) # Deshabilitar preview también durante la generación
        self.progress.SetValue(0)
        self.status_text.SetLabel("Iniciando generación...")

        thread = threading.Thread(target=self.generate_video_thread)
        thread.daemon = True
        thread.start()

    def generate_video_thread(self, is_preview=False):
        """Función que se ejecuta en un hilo separado para generar el video (o previsualización)."""
        output_path = self.output_ctrl.GetValue()
        if is_preview:
            temp_dir = Path(wx.StandardPaths.Get().GetTempDir())
            output_path = str(temp_dir / f"preview_audiodesc_{Path(self.video_file).stem}_{int(time.time())}.mp4") # Añadir timestamp
            # Asegurarse de que el archivo de previsualización tenga una extensión de video
            if not output_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                output_path += '.mp4' # Añadir .mp4 por defecto si no tiene una extensión de video
            self.temp_preview_files.append(output_path) # Guarda la ruta del archivo temporal

        try:
            wx.CallAfter(self.status_text.SetLabel, "Cargando video...")
            wx.CallAfter(self.progress.SetValue, 10)

            video = VideoFileClip(self.video_file)
            video_duration = video.duration # Usar la duración real del video

            wx.CallAfter(self.status_text.SetLabel, "Cargando audiodescripciones...")
            wx.CallAfter(self.progress.SetValue, 20)

            # Ordenar por tiempo
            sorted_descriptions = sorted(self.audiodescriptions, key=lambda x: x.tiempo)

            clips_audio_descripcion = []
            last_audio_end_time = 0.0

            for i, item in enumerate(sorted_descriptions):
                if not os.path.exists(item.archivo_audio):
                    continue # Ya se validó antes, pero por si acaso

                try:
                    clip_audio_raw = AudioFileClip(item.archivo_audio)
                    # Asegurarse de que el audio no empiece antes del audio anterior si se superponen
                    # O si el tiempo de inicio es anterior al final del audio anterior
                    actual_start_time = max(item.tiempo, last_audio_end_time) if item.tiempo < last_audio_end_time else item.tiempo

                    # Asegurarse de que el audio no se extienda más allá de la duración del video
                    if actual_start_time + clip_audio_raw.duration > video_duration:
                        # Recortar el clip de audio si se excede la duración del video
                        clip_audio_raw = clip_audio_raw.subclip(0, video_duration - actual_start_time)
                        if clip_audio_raw.duration <= 0: # Si no queda duración, saltar este clip
                            continue

                    clip_audio = clip_audio_raw.set_start(actual_start_time)
                    clips_audio_descripcion.append(clip_audio)
                    last_audio_end_time = actual_start_time + clip_audio.duration

                    progress_step = 30 / len(sorted_descriptions) if len(sorted_descriptions) > 0 else 0
                    wx.CallAfter(self.progress.SetValue, int(20 + (i + 1) * progress_step))

                except Exception as e:
                    print(f"Error al procesar audio {item.archivo_audio}: {e}")
                    wx.CallAfter(wx.MessageBox, f"Error al procesar audio {os.path.basename(item.archivo_audio)}: {str(e)}",
                                 "Error de Audio", wx.OK | wx.ICON_ERROR)
                    # Si hay un error con un audio, se puede optar por continuar o abortar
                    # Aquí optamos por continuar para no detener todo el proceso
                    continue

            if not clips_audio_descripcion and self.audiodescriptions: # Si había descripciones pero ninguna se cargó
                wx.CallAfter(wx.MessageBox, "No se pudieron cargar clips de audio válidos para las audiodescripciones. Asegúrate de que los archivos de audio son compatibles.",
                           "Error", wx.OK | wx.ICON_ERROR)
                return

            wx.CallAfter(self.status_text.SetLabel, "Combinando audios...")
            wx.CallAfter(self.progress.SetValue, 60)

            # Combinar audiodescripciones
            if clips_audio_descripcion:
                audio_descripcion_completo = CompositeAudioClip(clips_audio_descripcion).volumex(
                    self.vol_desc_ctrl.GetValue()
                )
            else:
                audio_descripcion_completo = None # No hay audiodescripciones para combinar

            # Combinar con audio original
            if video.audio is not None:
                audio_final = video.audio.volumex(self.vol_orig_ctrl.GetValue())
                if audio_descripcion_completo:
                    audio_final = CompositeAudioClip([audio_final, audio_descripcion_completo])
            else:
                if audio_descripcion_completo:
                    audio_final = audio_descripcion_completo
                else:
                    audio_final = None # No hay audio original ni audiodescripciones

            if audio_final:
                # Asegurarse de que el audio final tenga la misma duración que el video
                audio_final = audio_final.set_duration(video_duration)
            else:
                wx.CallAfter(wx.MessageBox, "El video resultante no tendrá audio (ni original ni audiodescripciones).",
                             "Advertencia", wx.OK | wx.ICON_WARNING)


            wx.CallAfter(self.status_text.SetLabel, "Creando video final...")
            wx.CallAfter(self.progress.SetValue, 80)

            video_final = video.set_audio(audio_final)

            wx.CallAfter(self.status_text.SetLabel, "Exportando...")
            wx.CallAfter(self.progress.SetValue, 90)

            video_final.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                verbose=False,
                logger=None
            )

            wx.CallAfter(self.progress.SetValue, 100)
            if is_preview:
                wx.CallAfter(self.status_text.SetLabel, f"Previsualización lista: {os.path.basename(output_path)}")
                # Abrir el archivo de previsualización con el reproductor predeterminado
                try:
                    if sys.platform == "win32":
                        os.startfile(output_path)
                    elif sys.platform == "darwin": # macOS
                        subprocess.call(('open', output_path))
                    else: # Linux
                        subprocess.call(('xdg-open', output_path))
                except Exception as e:
                    wx.CallAfter(wx.MessageBox(f"No se pudo abrir el archivo de previsualización: {str(e)}",
                                               "Error al Abrir Previsualización", wx.OK | wx.ICON_ERROR))
            else:
                wx.CallAfter(self.status_text.SetLabel, f"¡Completado! Video guardado: {output_path}")
                wx.CallAfter(wx.MessageBox, f"Video con audiodescripción creado exitosamente:\n{output_path}",
                            "Éxito", wx.OK | wx.ICON_INFORMATION)

            # Limpiar recursos de moviepy
            video.close()
            if audio_final:
                audio_final.close()
            for clip in clips_audio_descripcion:
                clip.close()

        except Exception as e:
            wx.CallAfter(wx.MessageBox, f"Error durante la generación {'de previsualización' if is_preview else ''}: {str(e)}",
                        "Error", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, f"Error en la generación {'de previsualización' if is_preview else ''}")
        finally:
            wx.CallAfter(self.generate_btn.Enable, True)
            wx.CallAfter(self.preview_btn.Enable, True) # Asegurar que el botón de previsualizar se re-habilite

    def on_preview_video(self, event):
        """Inicia el proceso de previsualización del video en un hilo separado."""
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Selecciona un archivo de video válido primero para previsualizar.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return
        if not self.audiodescriptions:
            wx.MessageBox("Agrega al menos una audiodescripción para previsualizar.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return
        if not MOVIEPY_AVAILABLE:
            wx.MessageBox("MoviePy no está disponible. Instala las dependencias para previsualizar.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return

        # Validar archivos de audio (misma lógica que en generar)
        missing_files = []
        for item in self.audiodescriptions:
            if not item.archivo_audio or not os.path.exists(item.archivo_audio):
                missing_files.append(f"Tiempo {self.format_time(item.tiempo)}: {os.path.basename(item.archivo_audio)}")

        if missing_files:
            message = "Los siguientes archivos de audio no existen o no son accesibles para la previsualización:\n\n" + "\n".join(missing_files)
            wx.MessageBox(message, "Archivos faltantes para Previsualización", wx.OK | wx.ICON_ERROR)
            return

        self.generate_btn.Enable(False)
        self.preview_btn.Enable(False)
        self.progress.SetValue(0)
        self.status_text.SetLabel("Generando previsualización...")

        thread = threading.Thread(target=self.generate_video_thread, args=(True,)) # Pasar True para indicar que es previsualización
        thread.daemon = True
        thread.start()

    def clean_temp_files(self):
        """Elimina los archivos temporales de previsualización generados."""
        if self.temp_preview_files:
            print("Limpiando archivos temporales de previsualización...")
            for f_path in self.temp_preview_files:
                try:
                    if os.path.exists(f_path):
                        os.remove(f_path)
                        print(f"Borrado: {f_path}")
                    else:
                        print(f"Archivo temporal no encontrado (ya borrado o no existe): {f_path}")
                except Exception as e:
                    print(f"Error al borrar archivo temporal {f_path}: {e}")
            self.temp_preview_files.clear() # Limpiar la lista después de intentar borrar

    def format_time(self, seconds):
        """Formatea segundos a HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"

class AudioDescriptionApp(wx.App):
    def OnInit(self):
        frame = MainFrame()
        frame.Show()
        return True

if __name__ == "__main__":
    app = AudioDescriptionApp()
    app.MainLoop()
