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

        # Botón para la previsualización normal (todo el video)
        self.preview_full_btn = wx.Button(panel, label="&Previsualizar Video Completo")
        self.preview_full_btn.Bind(wx.EVT_BUTTON, self.on_preview_full_video)
        self.preview_full_btn.Enable(False) # Deshabilitado hasta que haya video y descripciones
        final_action_sizer.Add(self.preview_full_btn, 0, wx.ALL, 5)

        # Nuevo botón para previsualizar sección específica
        self.preview_section_btn = wx.Button(panel, label="Previsualizar &Sección Específica...")
        self.preview_section_btn.Bind(wx.EVT_BUTTON, self.on_preview_specific_section)
        self.preview_section_btn.Enable(False) # Deshabilitado hasta que haya video y descripciones
        final_action_sizer.Add(self.preview_section_btn, 0, wx.ALL, 5)

        # Barra de progreso
        self.progress = wx.Gauge(panel, range=100)
        self.status_text = wx.StaticText(panel, label="Listo")

        # Layout principal
        main_sizer.Add(title, 0, wx.ALL|wx.CENTER, 10)
        main_sizer.Add(video_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(audio_sizer, 1, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(output_sizer, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(final_action_sizer, 0, wx.ALL|wx.CENTER, 10)
        main_sizer.Add(self.progress, 0, wx.ALL|wx.EXPAND, 5)
        main_sizer.Add(self.status_text, 0, wx.ALL, 5)

        panel.SetSizer(main_sizer)

        # Centrar ventana
        self.Center()

    def format_time(self, seconds):
        """Formatea segundos a HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"


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
            self.preview_full_btn.Enable(False)
            self.preview_section_btn.Enable(False)

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
        can_action = bool(MOVIEPY_AVAILABLE and self.video_file and os.path.exists(self.video_file) and self.audiodescriptions)
        self.generate_btn.Enable(can_action)
        self.preview_full_btn.Enable(can_action)
        self.preview_section_btn.Enable(can_action)

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
                project_path = dialog.GetPath()
                if not project_path.lower().endswith('.json'):
                    project_path += '.json'
                self.save_project_state(project_path)

    def on_save_as_project(self, event):
        """Maneja la acción de guardar el proyecto como un nuevo archivo."""
        with wx.FileDialog(self, "Guardar proyecto como...",
                          wildcard="Archivos JSON (*.json)|*.json",
                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                file_path = dialog.GetPath()
                if not file_path.lower().endswith('.json'):
                    file_path += '.json'
                self.save_project_state(file_path)

    def on_clear_project(self, event):
        """Limpia todos los datos del proyecto actual con confirmación."""
        confirm_dialog = wx.MessageBox(
            "¿Estás seguro de que quieres limpiar todo el proyecto?\n"
            "Esto borrará el video, las audiodescripciones y la configuración de salida.",
            "Confirmar Limpieza de Proyecto",
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
            self.update_ad_list_ctrl()
            self.update_action_buttons_state()
            self.status_text.SetLabel("Proyecto limpiado.")
            self.current_project_name = None
            self.SetTitle(self.app_title_base) # Restablecer título
        else:
            wx.MessageBox("Operación cancelada.", "Información", wx.OK | wx.ICON_INFORMATION)

    def on_generate(self, event):
        """Inicia la generación del video final."""
        if not self._common_preview_checks(): # Reutilizamos las mismas validaciones
            return

        output_path = self.output_ctrl.GetValue()
        if not output_path:
            wx.MessageBox("Por favor, especifica un nombre para el archivo de salida.",
                          "Error de Salida", wx.OK | wx.ICON_ERROR)
            return

        if os.path.exists(output_path):
            overwrite = wx.MessageBox(f"El archivo '{output_path}' ya existe. ¿Deseas sobrescribirlo?",
                                      "Confirmar Sobrescribir", wx.YES_NO | wx.ICON_WARNING)
            if overwrite == wx.NO:
                return

        self.generate_btn.Enable(False)
        self.preview_full_btn.Enable(False)
        self.preview_section_btn.Enable(False)
        self.progress.SetValue(0)
        self.status_text.SetLabel("Iniciando generación del video...")

        # Ejecutar la generación en un hilo separado (video completo)
        thread = threading.Thread(target=self.generate_video_thread, args=(False, 0.0, None)) # No es previsualización, rango completo
        thread.daemon = True
        thread.start()

    def _common_preview_checks(self):
        """Realiza las validaciones comunes antes de cualquier previsualización o generación."""
        if not self.video_file or not os.path.exists(self.video_file):
            wx.MessageBox("Selecciona un archivo de video válido primero.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return False
        if not self.audiodescriptions:
            wx.MessageBox("Agrega al menos una audiodescripción para procesar.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return False
        if not MOVIEPY_AVAILABLE:
            wx.MessageBox("MoviePy no está disponible. Instala las dependencias.",
                         "Error", wx.OK | wx.ICON_ERROR)
            return False

        # Validar archivos de audio
        missing_files = []
        for item in self.audiodescriptions:
            if not item.archivo_audio or not os.path.exists(item.archivo_audio):
                missing_files.append(f"Tiempo {self.format_time(item.tiempo)}: {os.path.basename(item.archivo_audio)}")

        if missing_files:
            message = "Los siguientes archivos de audio no existen o no son accesibles:\n\n" + "\n".join(missing_files) + "\n\nPor favor, corrígelos o elimínalos."
            wx.MessageBox(message, "Archivos faltantes", wx.OK | wx.ICON_ERROR)
            return False
        return True

    def on_preview_full_video(self, event):
        """Maneja la previsualización del video completo."""
        if not self._common_preview_checks():
            return

        self.generate_btn.Enable(False)
        self.preview_full_btn.Enable(False)
        self.preview_section_btn.Enable(False)
        self.progress.SetValue(0)
        self.status_text.SetLabel("Generando previsualización completa...")

        # Iniciar el hilo de generación con los parámetros por defecto (video completo)
        thread = threading.Thread(target=self.generate_video_thread, args=(True, 0.0, self.video_duration))
        thread.daemon = True
        thread.start()

    def on_preview_specific_section(self, event):
        """Abre un diálogo para seleccionar el rango de tiempo de previsualización."""
        if not self._common_preview_checks():
            return

        with PreviewSectionDialog(self, self.video_duration) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                start_time = dialog.get_start_time_in_seconds()
                end_time = dialog.get_end_time_in_seconds()

                if end_time <= start_time:
                    wx.MessageBox("El tiempo de fin debe ser mayor que el tiempo de inicio.",
                                  "Error de Rango", wx.OK | wx.ICON_ERROR)
                    return
                if start_time < 0 or end_time > self.video_duration:
                     wx.MessageBox(f"El rango de tiempo ({self.format_time(start_time)} - {self.format_time(end_time)}) está fuera de la duración del video ({self.format_time(self.video_duration)}).",
                                  "Error de Rango", wx.OK | wx.ICON_ERROR)
                     return


                # Ejecutar la generación en un hilo separado con el rango de tiempo
                self.generate_btn.Enable(False)
                self.preview_full_btn.Enable(False)
                self.preview_section_btn.Enable(False)
                self.progress.SetValue(0)
                self.status_text.SetLabel(f"Generando previsualización de {self.format_time(start_time)} a {self.format_time(end_time)}...")

                thread = threading.Thread(target=self.generate_video_thread, args=(True, start_time, end_time))
                thread.daemon = True
                thread.start()
            else:
                wx.MessageBox("Previsualización de sección cancelada.", "Información", wx.OK | wx.ICON_INFORMATION)


    def generate_video_thread(self, is_preview=False, start_time_sec=0.0, end_time_sec=None):
        """
        Función que se ejecuta en un hilo separado para generar el video (o previsualización).
        Ahora acepta un tiempo de inicio y fin para el clip.
        """
        output_path = self.output_ctrl.GetValue()
        if is_preview:
            temp_dir = Path(wx.StandardPaths.Get().GetTempDir())
            output_path = str(temp_dir / f"preview_audiodesc_{Path(self.video_file).stem}_{int(time.time())}.mp4")
            # Asegurarse de que el archivo temporal sea mp4 para compatibilidad
            if not output_path.lower().endswith('.mp4'):
                output_path = Path(output_path).with_suffix('.mp4')
            self.temp_preview_files.append(output_path)

        try:
            wx.CallAfter(self.status_text.SetLabel, "Cargando video...")
            wx.CallAfter(self.progress.SetValue, 10)

            video_clip_full = VideoFileClip(self.video_file)
            video_duration_full = video_clip_full.duration

            # Si end_time_sec es None, significa que queremos el rango completo del video
            # para la generación final, o hasta la última AD si es previsualización sin fin definido.
            if end_time_sec is None:
                if is_preview and self.audiodescriptions:
                    # En previsualización sin fin explícito, ir hasta la última AD + un colchón
                    last_ad_time = max([ad.tiempo for ad in self.audiodescriptions])
                    end_time_actual = min(video_duration_full, last_ad_time + 5) # +5 segundos por si el audio es más largo
                else:
                    end_time_actual = video_duration_full
            else:
                end_time_actual = end_time_sec

            # Asegurarse de que el rango sea válido y dentro de la duración del video
            start_time_actual = max(0.0, start_time_sec)
            end_time_actual = min(video_duration_full, end_time_actual)

            if start_time_actual >= end_time_actual:
                wx.CallAfter(wx.MessageBox, "El rango de tiempo seleccionado es inválido o vacío.", "Error", wx.OK | wx.ICON_ERROR)
                video_clip_full.close()
                return # Salir si el rango no es válido

            video = video_clip_full.subclip(start_time_actual, end_time_actual)
            video_duration_current_clip = video.duration # La duración del clip actual

            wx.CallAfter(self.status_text.SetLabel, "Cargando audiodescripciones...")
            wx.CallAfter(self.progress.SetValue, 20)

            clips_audio_descripcion = []
            # Filtrar audiodescripciones relevantes para la sección actual
            relevant_descriptions = []
            for item in self.audiodescriptions:
                # Calculamos el final probable del audio de la descripción
                try:
                    ad_audio_duration = AudioFileClip(item.archivo_audio).duration
                except Exception:
                    ad_audio_duration = 0 # Fallback si no se puede leer el audio

                ad_end_time = item.tiempo + ad_audio_duration

                # Condición para incluir la AD:
                # 1. Empieza dentro del rango del clip recortado
                # 2. Empieza antes del rango pero termina dentro o después del inicio del rango
                if (start_time_actual <= item.tiempo < end_time_actual) or \
                   (item.tiempo < start_time_actual and ad_end_time > start_time_actual):
                    relevant_descriptions.append(item)

            # Ordenar por tiempo
            sorted_relevant_descriptions = sorted(relevant_descriptions, key=lambda x: x.tiempo)

            last_audio_actual_end_time_in_clip = 0.0 # Tiempo relativo al inicio del clip recortado

            for i, item in enumerate(sorted_relevant_descriptions):
                if not os.path.exists(item.archivo_audio):
                    continue

                try:
                    clip_audio_raw = AudioFileClip(item.archivo_audio)
                    clip_audio_raw_duration = clip_audio_raw.duration

                    # Calcular el tiempo de inicio de la AD *relativo al inicio del clip recortado*
                    relative_ad_start_time = item.tiempo - start_time_actual

                    # Ajustar el inicio de la AD si se superpone con una anterior
                    # o si empieza antes del clip recortado pero su audio se extiende hasta él
                    actual_start_in_clip = max(relative_ad_start_time, last_audio_actual_end_time_in_clip)
                    
                    # Si el inicio ajustado es negativo (la AD comienza mucho antes del clip) o
                    # si el inicio ajustado es más allá del final del clip, la saltamos.
                    if actual_start_in_clip < 0 or actual_start_in_clip >= video_duration_current_clip:
                        continue

                    # Recortar el audio de la descripción si su inicio original es antes de start_time_actual
                    # y solo queremos la parte que cae dentro del clip actual.
                    trim_offset = 0.0
                    if item.tiempo < start_time_actual:
                        trim_offset = start_time_actual - item.tiempo
                        if trim_offset >= clip_audio_raw_duration: # Si el audio termina antes del start_time_actual
                            continue
                        clip_audio_raw = clip_audio_raw.subclip(trim_offset)

                    # Asegurarse de que el audio no se extienda más allá del final del clip de video actual
                    remaining_duration_in_clip = video_duration_current_clip - actual_start_in_clip
                    if clip_audio_raw.duration > remaining_duration_in_clip:
                        clip_audio_raw = clip_audio_raw.subclip(0, remaining_duration_in_clip)
                        if clip_audio_raw.duration <= 0: # Si después del recorte no queda nada
                            continue

                    clip_audio = clip_audio_raw.set_start(actual_start_in_clip)
                    clips_audio_descripcion.append(clip_audio)
                    last_audio_actual_end_time_in_clip = actual_start_in_clip + clip_audio.duration

                    progress_step = 30 / len(sorted_relevant_descriptions) if len(sorted_relevant_descriptions) > 0 else 0
                    wx.CallAfter(self.progress.SetValue, int(20 + (i + 1) * progress_step))

                except Exception as e:
                    print(f"Error al procesar audio para previsualización {item.archivo_audio}: {e}")
                    wx.CallAfter(wx.MessageBox, f"Error al procesar audio {os.path.basename(item.archivo_audio)} para previsualización: {str(e)}",
                                 "Error de Audio", wx.OK | wx.ICON_ERROR)
                    continue

            wx.CallAfter(self.status_text.SetLabel, "Combinando audios...")
            wx.CallAfter(self.progress.SetValue, 60)

            if clips_audio_descripcion:
                audio_descripcion_completo = CompositeAudioClip(clips_audio_descripcion).volumex(
                    self.vol_desc_ctrl.GetValue()
                )
            else:
                audio_descripcion_completo = None

            # Audio original del clip recortado
            audio_original_clip = video_clip_full.audio.subclip(start_time_actual, end_time_actual).volumex(self.vol_orig_ctrl.GetValue()) if video_clip_full.audio else None

            if audio_original_clip is not None:
                audio_final = audio_original_clip
                if audio_descripcion_completo:
                    # Usar CompositeAudioClip para mezclar si ambos existen
                    audio_final = CompositeAudioClip([audio_final, audio_descripcion_completo])
            else:
                # Si no hay audio original, el audio final es solo la audiodescripción
                audio_final = audio_descripcion_completo

            # Ajustar duración del audio final al clip de video si es necesario
            if audio_final:
                audio_final = audio_final.set_duration(video_duration_current_clip)
            else:
                wx.CallAfter(wx.MessageBox, "El video resultante no tendrá audio (ni original ni audiodescripciones).",
                             "Advertencia", wx.OK | wx.ICON_WARNING)

            wx.CallAfter(self.status_text.SetLabel, "Creando video final...")
            wx.CallAfter(self.progress.SetValue, 80)

            video_final = video.set_audio(audio_final)

            wx.CallAfter(self.status_text.SetLabel, "Exportando...")
            wx.CallAfter(self.progress.SetValue, 90)

            # Usar un logger para MoviePy para evitar que imprima mucho en consola
            # o si quieres ver más detalles, cambiar logger=None a 'bar' o 'full'
            video_final.write_videofile(
                str(output_path), # Convertir Path a string explícitamente
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                verbose=False,
                logger=None # Suprimir la salida de MoviePy en la consola
            )

            wx.CallAfter(self.progress.SetValue, 100)
            if is_preview:
                wx.CallAfter(self.status_text.SetLabel, f"Previsualización lista: {os.path.basename(output_path)}")
                try:
                    if sys.platform == "win32":
                        os.startfile(str(output_path)) # Convertir Path a string
                    elif sys.platform == "darwin": # macOS
                        subprocess.call(('open', str(output_path)))
                    else: # Linux
                        subprocess.call(('xdg-open', str(output_path)))
                except Exception as e:
                    wx.CallAfter(wx.MessageBox(f"No se pudo abrir el archivo de previsualización: {str(e)}",
                                               "Error al Abrir Previsualización", wx.OK | wx.ICON_ERROR))
            else:
                wx.CallAfter(self.status_text.SetLabel, f"¡Completado! Video guardado: {output_path}")
                wx.CallAfter(wx.MessageBox, f"Video con audiodescripción creado exitosamente:\n{output_path}",
                            "Éxito", wx.OK | wx.ICON_INFORMATION)

            # Limpiar recursos de moviepy
            video_clip_full.close()
            video.close()
            if audio_original_clip: audio_original_clip.close()
            if audio_descripcion_completo: audio_descripcion_completo.close()
            if audio_final: audio_final.close() # Asegurarse de cerrar el clip final de audio

        except Exception as e:
            error_message = f"Error durante la generación {'de previsualización' if is_preview else ''}: {str(e)}"
            print(error_message) # Imprimir en consola para depuración
            wx.CallAfter(wx.MessageBox, error_message, "Error", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.status_text.SetLabel, f"Error en la generación {'de previsualización' if is_preview else ''}")
        finally:
            wx.CallAfter(self.generate_btn.Enable, True)
            wx.CallAfter(self.preview_full_btn.Enable, True)
            wx.CallAfter(self.preview_section_btn.Enable, True)

    def clean_temp_files(self):
        """Elimina los archivos temporales de previsualización."""
        for f_path in self.temp_preview_files:
            try:
                if os.path.exists(f_path):
                    os.remove(f_path)
                    print(f"Archivo temporal eliminado: {f_path}")
            except Exception as e:
                print(f"Error al eliminar archivo temporal {f_path}: {e}")
        self.temp_preview_files.clear()


class PreviewSectionDialog(wx.Dialog):
    """
    Diálogo para que el usuario ingrese el rango de tiempo (inicio y fin)
    para la previsualización de una sección.
    """
    def __init__(self, parent, video_duration_seconds=0.0):
        super().__init__(parent, title="Previsualizar Sección Específica", size=(400, 250))
        self.video_duration_seconds = video_duration_seconds
        self.start_time_in_seconds = 0.0
        self.end_time_in_seconds = video_duration_seconds # Por defecto, hasta el final del video

        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Tiempo de Inicio
        start_label = wx.StaticText(panel, label="Tiempo de Inicio (HH:MM:SS / segundos):")
        self.start_time_text_ctrl = wx.TextCtrl(panel, value="00:00:00")
        self.start_seconds_spin_ctrl = wx.SpinCtrlDouble(panel, value="0.0", min=0, max=self.video_duration_seconds, inc=0.1)
        self.start_seconds_spin_ctrl.SetDigits(1)

        # Tiempo de Fin
        end_label = wx.StaticText(panel, label="Tiempo de Fin (HH:MM:SS / segundos):")
        self.end_time_text_ctrl = wx.TextCtrl(panel, value=self.format_time(self.video_duration_seconds))
        self.end_seconds_spin_ctrl = wx.SpinCtrlDouble(panel, value=str(self.video_duration_seconds), min=0, max=self.video_duration_seconds, inc=0.1)
        self.end_seconds_spin_ctrl.SetDigits(1)

        # Vincular eventos
        self.start_time_text_ctrl.Bind(wx.EVT_TEXT, self.on_start_time_text_change)
        self.start_seconds_spin_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_start_seconds_spin_change)
        self.end_time_text_ctrl.Bind(wx.EVT_TEXT, self.on_end_time_text_change)
        self.end_seconds_spin_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_end_seconds_spin_change)

        # Botones
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "&Aceptar")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "&Cancelar")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        main_sizer.Add(start_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.start_time_text_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.start_seconds_spin_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.AddSpacer(10)
        main_sizer.Add(end_label, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.end_time_text_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.end_seconds_spin_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        panel.SetSizer(main_sizer)
        self.CenterOnParent()

        # Inicializar los spin controls con la duración máxima del video
        self.start_seconds_spin_ctrl.SetRange(0, self.video_duration_seconds)
        self.end_seconds_spin_ctrl.SetRange(0, self.video_duration_seconds)


    def on_start_time_text_change(self, event):
        self.start_time_in_seconds = self._parse_time_str(self.start_time_text_ctrl.GetValue(), is_start=True)
        self.start_seconds_spin_ctrl.SetValue(self.start_time_in_seconds)

    def on_start_seconds_spin_change(self, event):
        self.start_time_in_seconds = self.start_seconds_spin_ctrl.GetValue()
        self.start_time_text_ctrl.SetValue(self.format_time(self.start_time_in_seconds))

    def on_end_time_text_change(self, event):
        self.end_time_in_seconds = self._parse_time_str(self.end_time_text_ctrl.GetValue(), is_start=False)
        self.end_seconds_spin_ctrl.SetValue(self.end_time_in_seconds)

    def on_end_seconds_spin_change(self, event):
        self.end_time_in_seconds = self.end_seconds_spin_ctrl.GetValue()
        self.end_time_text_ctrl.SetValue(self.format_time(self.end_time_in_seconds))

    def _parse_time_str(self, time_str, is_start=True):
        try:
            parts = list(map(int, time_str.split(':')))
            total_seconds = 0
            if len(parts) == 3:
                h, m, s = parts
                total_seconds = h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = parts
                total_seconds = m * 60 + s
            elif len(parts) == 1:
                total_seconds = parts[0]
            else:
                raise ValueError("Formato de tiempo inválido")

            # Asegurar que el tiempo esté dentro del rango del video
            if is_start:
                return max(0.0, min(total_seconds, self.video_duration_seconds))
            else:
                return max(0.0, min(total_seconds, self.video_duration_seconds))

        except ValueError:
            return 0.0 if is_start else self.video_duration_seconds # Valor por defecto en caso de error

    def get_start_time_in_seconds(self):
        return self.start_time_in_seconds

    def get_end_time_in_seconds(self):
        return self.end_time_in_seconds

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"


class MyApp(wx.App):
    def OnInit(self):
        self.frame = MainFrame()
        self.frame.Show()
        return True

if __name__ == '__main__':
    app = MyApp()
    app.MainLoop()