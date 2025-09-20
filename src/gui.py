# -*- coding: utf-8 -*-
import wx

class TimeInputDialog(wx.Dialog):
    """Diálogo para que el usuario ingrese el tiempo."""
    def __init__(self, parent, video_duration_seconds=0.0):
        super().__init__(parent, title="Ingresar Tiempo", size=(350, 200))
        self.video_duration_seconds = video_duration_seconds
        self.time_in_seconds = 0.0
        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        time_format_label = wx.StaticText(panel, label="Tiempo (HH:MM:SS):")
        self.time_text_ctrl = wx.TextCtrl(panel, value="00:00:00")
        self.time_text_ctrl.Bind(wx.EVT_TEXT, self.on_time_text_change)
        seconds_label = wx.StaticText(panel, label="Tiempo (segundos):")
        self.seconds_spin_ctrl = wx.SpinCtrlDouble(panel, value="0.0", min=0, max=self.video_duration_seconds, inc=0.1)
        self.seconds_spin_ctrl.SetDigits(1)
        self.seconds_spin_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_seconds_spin_change)
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
        self.seconds_spin_ctrl.SetRange(0, self.video_duration_seconds)

    def on_time_text_change(self, event):
        time_str = self.time_text_ctrl.GetValue()
        try:
            parts = list(map(int, time_str.split(':')))
            h, m, s = (0, 0, 0)
            if len(parts) == 3: h, m, s = parts
            elif len(parts) == 2: m, s = parts
            elif len(parts) == 1: s = parts[0]
            else: raise ValueError("Formato inválido")
            total_seconds = h * 3600 + m * 60 + s
            if 0 <= total_seconds <= self.video_duration_seconds:
                self.seconds_spin_ctrl.SetValue(total_seconds)
                self.time_in_seconds = total_seconds
            else:
                self.seconds_spin_ctrl.SetValue(self.video_duration_seconds)
                self.time_in_seconds = self.video_duration_seconds
        except ValueError: pass

    def on_seconds_spin_change(self, event):
        self.time_in_seconds = self.seconds_spin_ctrl.GetValue()
        self.time_text_ctrl.SetValue(self.format_time(self.time_in_seconds))

    def get_time_in_seconds(self):
        return self.time_in_seconds

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02}:{m:02}:{s:02}"

class AudioSourceDialog(wx.Dialog):
    """Diálogo para seleccionar el origen de la audiodescripción.""" 
    def __init__(self, parent):
        super().__init__(parent, title="Seleccionar Origen del Audio", size=(350, 150))
        self.source = None  # 'file' or 'tts'
        self.init_ui()

    def init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        instructions = wx.StaticText(panel, label="¿Cómo deseas agregar la audiodescripción?")
        main_sizer.Add(instructions, 0, wx.ALL | wx.CENTER, 15)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        file_btn = wx.Button(panel, label="Desde Archivo de Audio")
        file_btn.Bind(wx.EVT_BUTTON, self.on_select_file)
        
        tts_btn = wx.Button(panel, label="Sintetizar con Voz (TTS)")
        tts_btn.Bind(wx.EVT_BUTTON, self.on_select_tts)

        btn_sizer.Add(file_btn, 1, wx.ALL | wx.EXPAND, 5)
        btn_sizer.Add(tts_btn, 1, wx.ALL | wx.EXPAND, 5)

        main_sizer.Add(btn_sizer, 1, wx.ALL | wx.EXPAND, 5)
        
        panel.SetSizer(main_sizer)
        self.CenterOnParent()

    def on_select_file(self, event):
        self.source = 'file'
        self.EndModal(wx.ID_OK)

    def on_select_tts(self, event):
        self.source = 'tts'
        self.EndModal(wx.ID_OK)

    def get_source(self):
        return self.source
