
from math import log10, floor
from matplotlib import cm
import numpy as np
import math
import pickle
import pyqtgraph as pg
import os
import markdown
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtWidgets import QMessageBox
from qtpy import uic
from pyqtgraph import PlotWidget
import functools 

from core.module import Connector, StatusVar
from core.configoption import ConfigOption
from qtwidgets.scan_plotwidget import ScanPlotWidget
from qtwidgets.scientific_spinbox import ScienDSpinBox
from qtwidgets.scan_plotwidget import ScanImageItem
from gui.guiutils import ColorBar
from gui.colordefs import QudiPalettePale as palette
from gui.color_schemes.color_schemes import ColorScaleGen

from gui.guibase import GUIBase

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut

"""
Implementation Steps/TODOs:
- add default saveview as a file, which should be saved in the gui.
- check the colorbar implementation for smaller values => 32bit problem, quite hard...
"""

class SettingsDialog(QtWidgets.QDialog):
    """ Create the SettingsDialog window, based on the corresponding *.ui file."""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'transport_settings_gui.ui')

        # Load it
        super(SettingsDialog, self).__init__()
        uic.loadUi(ui_file, self)

class TransportMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'transport_gui.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()

class TransportGUI(GUIBase):
    """ GUI to control the qAFM Scan. """

    ## declare connectors
    transportlogic = Connector(interface='TransportLogic') 

    sigConstantOn = QtCore.Signal()
    sigConstantOff = QtCore.Signal()

    sigColorBarChanged = QtCore.Signal(str)  # emit a dockwidget object.

    saved_default_view = ConfigOption('saved_default_view', b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01\x04\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x03\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x01\x00\x00\x00D\x00\x00\x01\xd3\x00\x00\x01\xd3\x00\x07\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00p\x00t\x00i\x00_\x00x\x00y\x01\x00\x00\x02\x17\x00\x00\x01\x10\x00\x00\x01\x10\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00p\x00t\x00i\x00_\x00z\x01\x00\x00\x03+\x00\x00\x00\xba\x00\x00\x00f\x00\xff\xff\xff\x00\x00\x00\x01\x00\x00\x06x\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x02\xfb\x00\x00\x00\x1e\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00i\x00s\x00o\x00b\x00\x00\x00\x00D\x00\x00\x00\xa7\x00\x00\x00y\x00\xff\xff\xff\xfc\x00\x00\x00D\x00\x00\x03\xa1\x00\x00\x02\xc8\x00\xff\xff\xff\xfc\x01\x00\x00\x00\x03\xfc\x00\x00\x01\x08\x00\x00\x02\xb5\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0e\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00y\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00y\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfc\x00\x00\x03\xc1\x00\x00\x02\xbf\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0b\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00a\x00f\x00m\x01\x00\x00\x06\x84\x00\x00\x00\xfc\x00\x00\x00\xfc\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\x03\xa1\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x04\x00\x00\x00"\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00p\x00t\x00i\x00m\x00i\x00z\x00e\x00r\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x002\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x00h\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00t\x00o\x00p\x01\x00\x00\x01G\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00,\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00a\x00m\x00p\x00l\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x01\x82\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00')
    _config_color_map = ConfigOption('color_map')  # user specification in config file

    _dock_state = 'double'  # possible: single and double

    _image_container = {}
    _cb_container = {}
    _plot_container = {}
    _dockwidget_container = {}

    # status variables (will be saved at shutdown)
    _color_map = StatusVar('color_map', default='inferno')  # possible saved color map config
    _save_display_view = StatusVar('save_display_view', default=None) # It is a bytearray

    use_sample_current = StatusVar('use_sample_current', default= False)
    dc_sample_current = StatusVar('dc_sample_current', default= 0)

    use_sample_voltage = StatusVar('use_sample_voltage', default= False)
    dc_sample_voltage = StatusVar('dc_sample_voltage', default=0)

    use_backgate_voltage = StatusVar('use_backgate_voltage', default=False)
    dc_sample_voltage = StatusVar('dc_sample_voltage', default= 0)

    dimension_index = StatusVar('dimension_index', default=0)

    x_axis_parameter_index = StatusVar('x_axis_parameter_index', default=0)
    x_axis_start = StatusVar('x_axis_start', default = 0)
    x_axis_stop = StatusVar('x_axis_stop', default=1)
    x_axis_points = StatusVar('x_axis_points', default=1)

    y_axis_parameter_index = StatusVar('y_axis_parameter_index', default=0)
    y_axis_start = StatusVar('y_axis_start', default = 0)
    y_axis_stop = StatusVar('y_axis_stop', default=1)
    y_axis_points = StatusVar('y_axis_points', default=1)

    # status variables for setting dialog
    sd_gate_voltage_ramp_speed = StatusVar('sd_gate_voltage_ramp_speed', default = 0.1)
    sd_gate_voltage_upper_limit = StatusVar('sd_gate_voltage_upper_limit', default= 1)
    sd_gate_voltage_lower_limit = StatusVar('sd_gate_voltage_lower_limit', default= -1)
    sd_gate_voltage_autorange = StatusVar('sd_gate_voltage_autorange', default =False)

    sd_sample_voltage_ramp_speed = StatusVar('sd_sample_voltage_ramp_speed', default = 0.1)
    sd_sample_voltage_upper_limit = StatusVar('sd_sample_voltage_upper_limit', default= 1)
    sd_sample_voltage_lower_limit = StatusVar('sd_sample_voltage_lower_limit', default= -1)

    sd_sample_current_ramp_speed = StatusVar('sd_sample_current_ramp_speed', default= 0.01)
    sd_sample_current_upper_limit = StatusVar('sd_sample_current_upper_limit', default= 0.1)
    sd_sample_current_lower_limit = StatusVar('sd_sample_current_lower_limit', default= -0.1)

    sd_sample_transport_autorange = StatusVar('sd_sample_transport_autorange', default= False)

    sensing_function_index = StatusVar('sensing_function_index', default=0)
    sd_sensing_autorange = StatusVar('sd_sensing_autorange', default=False)
    sd_sensing_autozero = StatusVar('sd_sensing_autozero', default= False)
    sd_sensing_four_port = StatusVar('sd_sensing_four_port', default=False)
    sd_sensing_achange = StatusVar('sd_sensing_achange', default= False)

    sd_transport_integration_time = StatusVar('sd_transport_integration_time', default= 0.1)

    sd_timetrace_timestep = StatusVar('sd_timetrace_timestep', default = 1)
    sd_timetrace_measure_temperature = StatusVar('sd_timetrace_measure_temperature', default= True)

    sd_auto_save = StatusVar('sd_auto_save', default= True)
    sd_2D_gwyddion_save = StatusVar('sd_2D_gwyddion_save', default= True)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)


    def on_activate(self):
        """ Definition and initialization of the GUI. """
        self._transport_logic = self.transportlogic()

        if self._config_color_map is not None:
            self._color_map = self._config_color_map

        self._current_cs = ColorScaleGen(self._color_map)
        self._transport_logic.set_color_map(self._color_map)

        # initialize the settings stuff
        self.initMainUI()      # initialize the main GUI
        self.initSettingsUI()    
        #self.default_view()

        self._mw.save_tag_LineEdit = QtWidgets.QLineEdit(self._mw)
        self._mw.save_tag_LineEdit.setMaximumWidth(500)
        self._mw.save_tag_LineEdit.setMinimumWidth(200)
        self._mw.save_tag_LineEdit.setToolTip('Enter a nametag which will be\n'
                                              'added to the filename.')
        self._mw.save_ToolBar.addWidget(self._mw.save_tag_LineEdit)

        self._transport_logic.sigScanFinished.connect(self.enable_scan_actions)
        self._transport_logic.sig1DScanStarted.connect(self.enable_stop_action)
        self._transport_logic.sig1DScanStarted.connect(self.adjust_1D_transport_image)
        self._transport_logic.sig2DScanStarted.connect(self.enable_stop_action)
        self._transport_logic.sig2DScanStarted.connect(self.adjust_2D_transport_image)
        self._transport_logic.sig2DScanStarted.connect(self.enable_stop_action)
        self._transport_logic.sig2DScanStarted.connect(self.adjust_2D_transport_image)
        self._transport_logic.sigTimetraceStarted.connect(self.enable_stop_action)
        self._transport_logic.sigTimetraceStarted.connect(self.adjust_timetrace_transport_image)
        self._transport_logic.sig1DScanPointFinished.connect(self._update_1D_transport_data)
        self._transport_logic.sig2DScanPointFinished.connect(self._update_2D_transport_data)
        self._transport_logic.sigTimetracePointFinished.connect(self._update_timetrace_transport_data)

        self._transport_logic.sigScanAutoSave.connect(self.autosave_transport_data)
        self._transport_logic.sigDataSaved.connect(self.enable_save_actions)

        self.sigColorBarChanged.connect(self._update_data_from_dockwidget)

        self.scan_type = ''

        self.load_view()
        self.retrieve_status_var()
        self.fix_constant_output_parameters()

         

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        self.store_status_var()
        self.store_settings_status_var()
        self.saveWindowGeometry(self._mw)
        self._mw.close()
        self._sd.close()


    def show(self):
        """Make window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()
    
    def initMainUI(self):
        """ Definition, configuration and initialisation of the confocal GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values.
        """
        self._mw = TransportMainWindow()
        self.restoreWindowPos(self._mw)

        self.setup_mw_elements()

        self._mw.actionDefault_Display.triggered.connect(self.default_view)
        self._mw.actionSave_Display.triggered.connect(self.save_view)
        self._mw.actionLoad_Display.triggered.connect(self.load_view)

        self._mw.action_run.triggered.connect(self.run_transport_measurement)
        self._mw.action_stop.triggered.connect(self.stop_transport_measurement)
        self._mw.action_Save.triggered.connect(self.save_transport_data_clicked)
        self._mw.action_toggle_constant_output.triggered.connect(self.toggle_constant_output)

        self._mw.constant_sample_current_checkBox.clicked.connect(self.constant_sample_current_checkBox_isClicked)
        self._mw.constant_sample_voltage_checkBox.clicked.connect(self.constant_sample_voltage_checkBox_isClicked)
        self._mw.constant_backgate_voltage_checkBox.clicked.connect(self.constant_backgate_voltage_checkBox_isClicked)

        self._mw.dimension_comboBox.currentIndexChanged.connect(self.dimension_comboBox_indexChanged)

        self.setup_axis_sweep_parameter_comboBox()
        self._mw.x_axis_sweep_parameter_comboBox.currentTextChanged.connect(self.x_axis_sweep_parameter_comboBox_textChanged)
        self._mw.y_axis_sweep_parameter_comboBox.currentTextChanged.connect(self.y_axis_sweep_parameter_comboBox_textChanged)

        self.setup_sensing_function_comboBox()

        ###################################################################
        #               Configuring the dock widgets                      #
        ###################################################################
        # All our gui elements are dockable, and so there should be no "central" widget.
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)
        self._create_dockwidgets()
        self._update_1D_transport_data()
        self._update_2D_transport_data()
        self._set_aspect_ratio_images()

    def setup_mw_elements(self):
        self._mw.constant_sample_current_DoubleSpinBox.setEnabled(False)
        self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(False)
        self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(False)
        self._mw.y_axis_label.setEnabled(False)
        self._mw.y_axis_sweep_parameter_comboBox.setEnabled(False)
        self._mw.y_start_label.setEnabled(False)
        self._mw.y_axis_start_DoubleSpinBox.setEnabled(False)
        self._mw.y_stop_label.setEnabled(False)
        self._mw.y_axis_stop_DoubleSpinBox.setEnabled(False)
        self._mw.y_axis_points_label.setEnabled(False)
        self._mw.y_axis_points_DoubleSpinBox.setEnabled(False)

    def fix_constant_output_parameters(self):
        self._mw.constant_sample_current_DoubleSpinBox.setEnabled(self._mw.constant_sample_current_checkBox.isChecked())
        self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(self._mw.constant_sample_voltage_checkBox.isChecked())
        self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(self._mw.constant_backgate_voltage_checkBox.isChecked())

    def run_transport_measurement(self, is_checked):
        self.disable_scan_actions()
        if self._mw.dimension_comboBox.currentIndex() == 1: #2D scan
            self.start_2D_transport_scan()
        elif self._mw.dimension_comboBox.currentIndex() == 2: #Timetrace
            self.start_transport_timetrace()
        else:
            self.start_1D_transport_scan()

    def stop_transport_measurement(self, is_checked):
        self._transport_logic._stop_request = True

    def toggle_constant_output(self, is_checked):
        """ Starts or stops constant output if no measurement is running. """
        self._mw.action_toggle_constant_output.blockSignals(True)
        self._mw.action_toggle_constant_output.setEnabled(False)
        error = False
        if is_checked:
            self._mw.action_run.setEnabled(False)
            self._mw.constant_sample_current_checkBox.setEnabled(False)
            self._mw.constant_sample_current_DoubleSpinBox.setEnabled(False)
            self._mw.constant_sample_voltage_checkBox.setEnabled(False)
            self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(False)
            self._mw.constant_backgate_voltage_checkBox.setEnabled(False)
            self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(False)

            self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setEnabled(False)
            self._sd.gate_voltage_upper_limit_DoubleSpinBox.setEnabled(False)
            self._sd.gate_voltage_lower_limit_DoubleSpinBox.setEnabled(False)
            self._sd.gate_voltage_autorange_checkBox.setEnabled(False)
            self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setEnabled(False)
            self._sd.sample_voltage_upper_limit_DoubleSpinBox.setEnabled(False)
            self._sd.sample_voltage_lower_limit_DoubleSpinBox.setEnabled(False)
            self._sd.sample_current_ramp_speed_DoubleSpinBox.setEnabled(False)
            self._sd.sample_current_upper_limit_DoubleSpinBox.setEnabled(False)
            self._sd.sample_current_lower_limit_DoubleSpinBox.setEnabled(False)
            self._sd.sample_transport_autorange_checkBox.setEnabled(False)

            if self._mw.constant_sample_current_checkBox.isChecked():
                is_setted = self._transport_logic.set_sample_DC_current(self._mw.constant_sample_current_DoubleSpinBox.value())
                if not is_setted:
                    error = True
            if self._mw.constant_sample_voltage_checkBox.isChecked():
                is_setted =self._transport_logic.set_sample_DC_voltage(self._mw.constant_sample_voltage_DoubleSpinBox.value())
                if not is_setted:
                    error = True
            if self._mw.constant_backgate_voltage_checkBox.isChecked():
                is_setted = self._transport_logic.set_backgate_DC_voltage(self._mw.constant_backgate_voltage_DoubleSpinBox.value())
                if not is_setted:
                    error = True
            if error:
                self._transport_logic.reset_outputs()
                self._mw.action_run.setEnabled(True)
                self._mw.constant_sample_current_checkBox.setEnabled(True)
                self._mw.constant_sample_current_DoubleSpinBox.setEnabled(self._mw.constant_sample_current_checkBox.isChecked())
                self._mw.constant_sample_voltage_checkBox.setEnabled(True)
                self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(self._mw.constant_sample_voltage_checkBox.isChecked())
                self._mw.constant_backgate_voltage_checkBox.setEnabled(True)
                self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(self._mw.constant_backgate_voltage_checkBox.isChecked())

                self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
                self._sd.gate_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
                self._sd.gate_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
                self._sd.gate_voltage_autorange_checkBox.setEnabled(True)
                self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
                self._sd.sample_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
                self._sd.sample_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
                self._sd.sample_current_ramp_speed_DoubleSpinBox.setEnabled(True)
                self._sd.sample_current_upper_limit_DoubleSpinBox.setEnabled(True)
                self._sd.sample_current_lower_limit_DoubleSpinBox.setEnabled(True)
                self._sd.sample_transport_autorange_checkBox.setEnabled(True)

                self._mw.action_toggle_constant_output.setChecked(False)
            else:
                self._transport_logic.outputs_on()

        else:
            self._transport_logic.reset_outputs()
            self._mw.action_run.setEnabled(True)
            self._mw.constant_sample_current_checkBox.setEnabled(True)
            self._mw.constant_sample_current_DoubleSpinBox.setEnabled(self._mw.constant_sample_current_checkBox.isChecked())
            self._mw.constant_sample_voltage_checkBox.setEnabled(True)
            self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(self._mw.constant_sample_voltage_checkBox.isChecked())
            self._mw.constant_backgate_voltage_checkBox.setEnabled(True)
            self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(self._mw.constant_backgate_voltage_checkBox.isChecked())

            self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
            self._sd.gate_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
            self._sd.gate_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
            self._sd.gate_voltage_autorange_checkBox.setEnabled(True)
            self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
            self._sd.sample_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
            self._sd.sample_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
            self._sd.sample_current_ramp_speed_DoubleSpinBox.setEnabled(True)
            self._sd.sample_current_upper_limit_DoubleSpinBox.setEnabled(True)
            self._sd.sample_current_lower_limit_DoubleSpinBox.setEnabled(True)
            self._sd.sample_transport_autorange_checkBox.setEnabled(True)

        self._mw.action_toggle_constant_output.blockSignals(False)
        self._mw.action_toggle_constant_output.setEnabled(True)
        return

    def constant_sample_current_checkBox_isClicked(self, state):
        if state:
            self._mw.constant_sample_current_DoubleSpinBox.setEnabled(True)
            self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(False)
            self._mw.constant_sample_voltage_checkBox.setChecked(False)
        else:
            self._mw.constant_sample_current_DoubleSpinBox.setEnabled(False)

    def constant_sample_voltage_checkBox_isClicked(self, state):
        if state:
            self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(True)
            self._mw.constant_sample_current_DoubleSpinBox.setEnabled(False)
            self._mw.constant_sample_current_checkBox.setChecked(False)
        else:
            self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(False)
    
    def constant_backgate_voltage_checkBox_isClicked(self, state):
        if state:
            self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(True)
        else:
            self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(False)

    def dimension_comboBox_indexChanged(self, index):
        if index == 0: #Dimension is 1D
            self._mw.x_axis_label.setEnabled(True)
            self._mw.x_axis_sweep_parameter_comboBox.setEnabled(True)
            self._mw.x_start_label.setEnabled(True)
            self._mw.x_axis_start_DoubleSpinBox.setEnabled(True)
            self._mw.x_stop_label.setEnabled(True)
            self._mw.x_axis_stop_DoubleSpinBox.setEnabled(True)
            self._mw.x_axis_points_label.setEnabled(True)
            self._mw.x_axis_points_DoubleSpinBox.setEnabled(True)
            self._mw.y_axis_label.setEnabled(False)
            self._mw.y_axis_sweep_parameter_comboBox.setEnabled(False)
            self._mw.y_start_label.setEnabled(False)
            self._mw.y_axis_start_DoubleSpinBox.setEnabled(False)
            self._mw.y_stop_label.setEnabled(False)
            self._mw.y_axis_stop_DoubleSpinBox.setEnabled(False)
            self._mw.y_axis_points_label.setEnabled(False)
            self._mw.y_axis_points_DoubleSpinBox.setEnabled(False)

        elif index == 1: #Dimension is 2D
            self._mw.x_axis_label.setEnabled(True)
            self._mw.x_axis_sweep_parameter_comboBox.setEnabled(True)
            self._mw.x_start_label.setEnabled(True)
            self._mw.x_axis_start_DoubleSpinBox.setEnabled(True)
            self._mw.x_stop_label.setEnabled(True)
            self._mw.x_axis_stop_DoubleSpinBox.setEnabled(True)
            self._mw.x_axis_points_label.setEnabled(True)
            self._mw.x_axis_points_DoubleSpinBox.setEnabled(True)
            self._mw.y_axis_label.setEnabled(True)
            self._mw.y_axis_sweep_parameter_comboBox.setEnabled(True)
            self._mw.y_start_label.setEnabled(True)
            self._mw.y_axis_start_DoubleSpinBox.setEnabled(True)
            self._mw.y_stop_label.setEnabled(True)
            self._mw.y_axis_stop_DoubleSpinBox.setEnabled(True)
            self._mw.y_axis_points_label.setEnabled(True)
            self._mw.y_axis_points_DoubleSpinBox.setEnabled(True)

        elif index == 2: #Timetrace
            self._mw.x_axis_label.setEnabled(False)
            self._mw.x_axis_sweep_parameter_comboBox.setEnabled(False)
            self._mw.x_start_label.setEnabled(False)
            self._mw.x_axis_start_DoubleSpinBox.setEnabled(False)
            self._mw.x_stop_label.setEnabled(False)
            self._mw.x_axis_stop_DoubleSpinBox.setEnabled(False)
            self._mw.x_axis_points_label.setEnabled(False)
            self._mw.x_axis_points_DoubleSpinBox.setEnabled(False)
            self._mw.y_axis_label.setEnabled(False)
            self._mw.y_axis_sweep_parameter_comboBox.setEnabled(False)
            self._mw.y_start_label.setEnabled(False)
            self._mw.y_axis_start_DoubleSpinBox.setEnabled(False)
            self._mw.y_stop_label.setEnabled(False)
            self._mw.y_axis_stop_DoubleSpinBox.setEnabled(False)
            self._mw.y_axis_points_label.setEnabled(False)
            self._mw.y_axis_points_DoubleSpinBox.setEnabled(False)

    def setup_axis_sweep_parameter_comboBox(self):
        axis_units = self._transport_logic.axis_units
        axis_units_keys = list(axis_units.keys())
        for axis_unit in axis_units_keys:
            self._mw.x_axis_sweep_parameter_comboBox.addItem(axis_unit)
            self._mw.y_axis_sweep_parameter_comboBox.addItem(axis_unit)

    def x_axis_sweep_parameter_comboBox_textChanged(self, text):
        self._mw.x_axis_start_DoubleSpinBox.setSuffix(self._transport_logic.axis_units[text]['si_units'])
        self._mw.x_axis_stop_DoubleSpinBox.setSuffix(self._transport_logic.axis_units[text]['si_units'])
        self._mw.x_axis_start_DoubleSpinBox.setRange(self._transport_logic.axis_units[text]['lower_limit'],self._transport_logic.axis_units[text]['upper_limit'])
        self._mw.x_axis_stop_DoubleSpinBox.setRange(self._transport_logic.axis_units[text]['lower_limit'],self._transport_logic.axis_units[text]['upper_limit'])

    def y_axis_sweep_parameter_comboBox_textChanged(self, text):
        self._mw.y_axis_start_DoubleSpinBox.setSuffix(self._transport_logic.axis_units[text]['si_units'])
        self._mw.y_axis_stop_DoubleSpinBox.setSuffix(self._transport_logic.axis_units[text]['si_units'])
        self._mw.y_axis_start_DoubleSpinBox.setRange(self._transport_logic.axis_units[text]['lower_limit'],self._transport_logic.axis_units[text]['upper_limit'])
        self._mw.y_axis_stop_DoubleSpinBox.setRange(self._transport_logic.axis_units[text]['lower_limit'],self._transport_logic.axis_units[text]['upper_limit'])

    def initSettingsUI(self):
        """ Initialize and set up the Settings Dialog. """

        self._sd = SettingsDialog()

        sample_source_limits = self._transport_logic.get_sample_source_limits()
        gate_source_limits = self._transport_logic.get_gate_source_limits()

        self._sd.gate_voltage_upper_limit_DoubleSpinBox.editingFinished.connect(self.set_gate_voltage_limits)
        self._sd.gate_voltage_upper_limit_DoubleSpinBox.setRange(0, gate_source_limits.max_voltage)
        self._sd.gate_voltage_lower_limit_DoubleSpinBox.editingFinished.connect(self.set_gate_voltage_limits)
        self._sd.gate_voltage_lower_limit_DoubleSpinBox.setRange(gate_source_limits.min_voltage, 0)

        self._sd.sample_voltage_upper_limit_DoubleSpinBox.editingFinished.connect(self.set_sample_voltage_limits)
        self._sd.sample_voltage_upper_limit_DoubleSpinBox.setRange(0, sample_source_limits.max_voltage)
        self._sd.sample_voltage_lower_limit_DoubleSpinBox.editingFinished.connect(self.set_sample_voltage_limits)
        self._sd.sample_voltage_lower_limit_DoubleSpinBox.setRange(sample_source_limits.min_voltage, 0)

        self._sd.sample_current_upper_limit_DoubleSpinBox.editingFinished.connect(self.set_sample_current_limits)
        self._sd.sample_current_upper_limit_DoubleSpinBox.setRange(0, sample_source_limits.max_current)
        self._sd.sample_current_lower_limit_DoubleSpinBox.editingFinished.connect(self.set_sample_current_limits)
        self._sd.sample_current_lower_limit_DoubleSpinBox.setRange(sample_source_limits.min_current, 0)

        self._sd.sensing_delay_DoubleSpinBox.setRange(sample_source_limits.min_sens_delay, sample_source_limits.max_sens_delay)

        self.retrieve_settings_status_var()

        self.set_gate_voltage_limits()
        self.set_sample_voltage_limits()
        self.set_sample_current_limits()

        self._mw.action_open_settings.triggered.connect(self.show_settings_window)

    def set_gate_voltage_limits(self):
        gate_voltage_upper_limit = self._sd.gate_voltage_upper_limit_DoubleSpinBox.value()
        gate_voltage_lower_limit = self._sd.gate_voltage_lower_limit_DoubleSpinBox.value()
        self._transport_logic.set_gate_voltage_limits(gate_voltage_lower_limit, gate_voltage_upper_limit)
        self._mw.constant_backgate_voltage_DoubleSpinBox.setRange(gate_voltage_lower_limit, gate_voltage_upper_limit)
        self.x_axis_sweep_parameter_comboBox_textChanged(self._mw.x_axis_sweep_parameter_comboBox.currentText())
        self.y_axis_sweep_parameter_comboBox_textChanged(self._mw.y_axis_sweep_parameter_comboBox.currentText())

    def set_sample_voltage_limits(self):
        sample_voltage_upper_limit = self._sd.sample_voltage_upper_limit_DoubleSpinBox.value()
        sample_voltage_lower_limit = self._sd.sample_voltage_lower_limit_DoubleSpinBox.value()
        self._transport_logic.set_sample_voltage_limits(sample_voltage_lower_limit, sample_voltage_upper_limit)
        self._mw.constant_sample_voltage_DoubleSpinBox.setRange(sample_voltage_lower_limit, sample_voltage_upper_limit)
        self.x_axis_sweep_parameter_comboBox_textChanged(self._mw.x_axis_sweep_parameter_comboBox.currentText())
        self.y_axis_sweep_parameter_comboBox_textChanged(self._mw.y_axis_sweep_parameter_comboBox.currentText())

    def set_sample_current_limits(self):
        sample_current_upper_limit = self._sd.sample_current_upper_limit_DoubleSpinBox.value()
        sample_current_lower_limit = self._sd.sample_current_lower_limit_DoubleSpinBox.value()
        self._transport_logic.set_sample_current_limits(sample_current_lower_limit, sample_current_upper_limit)
        self._mw.constant_sample_current_DoubleSpinBox.setRange(sample_current_lower_limit, sample_current_upper_limit)
        self.x_axis_sweep_parameter_comboBox_textChanged(self._mw.x_axis_sweep_parameter_comboBox.currentText())
        self.y_axis_sweep_parameter_comboBox_textChanged(self._mw.y_axis_sweep_parameter_comboBox.currentText())

    def setup_sensing_function_comboBox(self):
        self.meas_params_units = self._transport_logic.meas_params_units
        meas_params_units_keys = list(self.meas_params_units.keys())
        for meas_param_unit in meas_params_units_keys:
            self._mw.sensing_function_comboBox.addItem(meas_param_unit)

    def show_settings_window(self):
        """ Show and open the settings window. """
        self._sd.show()
        self._sd.raise_()

    def retrieve_status_var(self):
        """ Obtain variables from file. """

        self._mw.constant_sample_current_checkBox.setChecked(self.use_sample_current)
        self._mw.constant_sample_current_DoubleSpinBox.setValue(self.dc_sample_current)

        self._mw.constant_sample_voltage_checkBox.setChecked(self.use_sample_voltage)
        self._mw.constant_sample_voltage_DoubleSpinBox.setValue(self.dc_sample_voltage)

        self._mw.constant_backgate_voltage_checkBox.setChecked(self.use_backgate_voltage)
        self._mw.constant_backgate_voltage_DoubleSpinBox.setValue(self.dc_sample_voltage)

        self._mw.dimension_comboBox.setCurrentIndex(self.dimension_index)

        self._mw.x_axis_sweep_parameter_comboBox.setCurrentIndex(self.x_axis_parameter_index)
        self._mw.x_axis_start_DoubleSpinBox.setValue(self.x_axis_start)
        self._mw.x_axis_stop_DoubleSpinBox.setValue(self.x_axis_stop)
        self._mw.x_axis_points_DoubleSpinBox.setValue(self.x_axis_points)

        self._mw.y_axis_sweep_parameter_comboBox.setCurrentIndex(self.y_axis_parameter_index)
        self._mw.y_axis_start_DoubleSpinBox.setValue(self.y_axis_start)
        self._mw.y_axis_stop_DoubleSpinBox.setValue(self.y_axis_stop)
        self._mw.y_axis_points_DoubleSpinBox.setValue(self.y_axis_points)

        self._mw.sensing_function_comboBox.setCurrentIndex(self.sensing_function_index)

    def store_status_var(self):
        """ Store all those variables to file. """

        self.use_sample_current = self._mw.constant_sample_current_checkBox.isChecked()
        self.dc_sample_current = self._mw.constant_sample_current_DoubleSpinBox.value()

        self.use_sample_voltage = self._mw.constant_sample_voltage_checkBox.isChecked()
        self.dc_sample_voltage = self._mw.constant_sample_voltage_DoubleSpinBox.value()

        self.use_backgate_voltage = self._mw.constant_backgate_voltage_checkBox.isChecked()
        self.dc_sample_voltage = self._mw.constant_backgate_voltage_DoubleSpinBox.value()

        self.dimension_index = self._mw.dimension_comboBox.currentIndex()

        self.x_axis_parameter_index = self._mw.x_axis_sweep_parameter_comboBox.currentIndex()
        self.x_axis_start = self._mw.x_axis_start_DoubleSpinBox.value()
        self.x_axis_stop = self._mw.x_axis_stop_DoubleSpinBox.value()
        self.x_axis_points = self._mw.x_axis_points_DoubleSpinBox.value()

        self.y_axis_parameter_index = self._mw.y_axis_sweep_parameter_comboBox.currentIndex()
        self.y_axis_start = self._mw.y_axis_start_DoubleSpinBox.value()
        self.y_axis_stop = self._mw.y_axis_stop_DoubleSpinBox.value()
        self.y_axis_points = self._mw.y_axis_points_DoubleSpinBox.value()

        self.sensing_function_index = self._mw.sensing_function_comboBox.currentIndex()

    def retrieve_settings_status_var(self):
        """ Obtain variables from file. """

        self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setValue(self.sd_gate_voltage_ramp_speed)
        self._sd.gate_voltage_upper_limit_DoubleSpinBox.setValue(self.sd_gate_voltage_upper_limit)
        self._sd.gate_voltage_lower_limit_DoubleSpinBox.setValue(self.sd_gate_voltage_lower_limit)
        self._sd.gate_voltage_autorange_checkBox.setChecked(self.sd_gate_voltage_autorange)

        self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setValue(self.sd_sample_voltage_ramp_speed)
        self._sd.sample_voltage_upper_limit_DoubleSpinBox.setValue(self.sd_sample_voltage_upper_limit)
        self._sd.sample_voltage_lower_limit_DoubleSpinBox.setValue(self.sd_sample_voltage_lower_limit)

        self._sd.sample_current_ramp_speed_DoubleSpinBox.setValue(self.sd_sample_current_ramp_speed)
        self._sd.sample_current_upper_limit_DoubleSpinBox.setValue(self.sd_sample_current_upper_limit)
        self._sd.sample_current_lower_limit_DoubleSpinBox.setValue(self.sd_sample_current_lower_limit)

        self._sd.sample_transport_autorange_checkBox.setChecked(self.sd_sample_transport_autorange)

        self._sd.sensing_autorange_checkBox.setChecked(self.sd_sensing_autorange)
        self._sd.sensing_autozero_checkBox.setChecked(self.sd_sensing_autozero)
        self._sd.sensing_four_port_checkBox.setChecked(self.sd_sensing_four_port)
        self._sd.sensing_achange_checkBox.setChecked(self.sd_sensing_achange)

        self._sd.int_time_transport_DoubleSpinBox.setValue(self.sd_transport_integration_time)

        self._sd.timetrace_timestep_DoubleSpinBox.setValue(self.sd_timetrace_timestep)
        self._sd.timetrace_measure_temperature_checkBox.setChecked(self.sd_timetrace_measure_temperature)

        self._sd.auto_save_qafm_CheckBox.setChecked(self.sd_auto_save)
        self._sd.save_to_gwyddion_CheckBox.setChecked(self.sd_2D_gwyddion_save)

    def store_settings_status_var(self):
        """ Store all those variables to file. """

        self.sd_gate_voltage_ramp_speed = self._sd.gate_voltage_ramp_speed_DoubleSpinBox.value()
        self.sd_gate_voltage_upper_limit = self._sd.gate_voltage_upper_limit_DoubleSpinBox.value()
        self.sd_gate_voltage_lower_limit = self._sd.gate_voltage_lower_limit_DoubleSpinBox.value()
        self.sd_gate_voltage_autorange = self._sd.gate_voltage_autorange_checkBox.isChecked()

        self.sd_sample_voltage_ramp_speed = self._sd.sample_voltage_ramp_speed_DoubleSpinBox.value()
        self.sd_sample_voltage_upper_limit = self._sd.sample_voltage_upper_limit_DoubleSpinBox.value()
        self.sd_sample_voltage_lower_limit = self._sd.sample_voltage_lower_limit_DoubleSpinBox.value()

        self.sd_sample_current_ramp_speed = self._sd.sample_current_ramp_speed_DoubleSpinBox.value()
        self.sd_sample_current_upper_limit = self._sd.sample_current_upper_limit_DoubleSpinBox.value()
        self.sd_sample_current_lower_limit = self._sd.sample_current_lower_limit_DoubleSpinBox.value()

        self.sd_sample_transport_autorange = self._sd.sample_transport_autorange_checkBox.isChecked()

        self.sd_sensing_autorange = self._sd.sensing_autorange_checkBox.isChecked()
        self.sd_sensing_autozero = self._sd.sensing_autozero_checkBox.isChecked()
        self.sd_sensing_four_port = self._sd.sensing_four_port_checkBox.isChecked()
        self.sd_sensing_achange = self._sd.sensing_achange_checkBox.isChecked()
        self.sd_sensing_delay_time = self._sd.sensing_delay_DoubleSpinBox.value()
        self.sd_transport_integration_time = self._sd.int_time_transport_DoubleSpinBox.value()

        self.sd_timetrace_timestep = self._sd.timetrace_timestep_DoubleSpinBox.value()
        self.sd_timetrace_measure_temperature = self._sd.timetrace_measure_temperature_checkBox.isChecked()

        self.sd_auto_save = self._sd.auto_save_qafm_CheckBox.isChecked()
        self.sd_2D_gwyddion_save = self._sd.save_to_gwyddion_CheckBox.isChecked()

    def get_all_data_matrices(self):
        """ more of a helper method to get all the data matrices. """

        data_dict = {}
        data_dict.update(self._transport_logic.get_1D_data())
        data_dict.update(self._transport_logic.get_2D_data())

        return data_dict
    
    def initialize_all_data_matrices(self):
        """ more of a helper method to get all the data matrices. """

        data_dict = {}
        transport_1D_array = self._transport_logic.initialize_transport_1D_array(-10, 10, 11, None, None)

        transport_2D_array = self._transport_logic.initialize_transport_2D_array(-10, 10, 11, -10, 10, 11, None, None, None)

        transport_timetrace_array = self._transport_logic.initialize_transport_timetrace_array(None)
        data_dict.update(transport_1D_array)
        data_dict.update(transport_2D_array)
        data_dict.update(transport_timetrace_array)

        return data_dict

    def _create_colorbar(self, name, colorscale):
        """ Helper method to create Colorbar. 
        @param str name: the name of the colorbar object
        @param ColorScale colorscale: contains definition for colormap (colormap), 
                                  normalized colormap (cmap_normed) and Look Up 
                                  Table (lut).

        @return: Colorbar object
        """

        # store for convenience all the colorbars in a container
        self._cb_container[name] = ColorBar(colorscale.cmap_normed, width=100, 
                                            cb_min=0, cb_max=100)

        return self._cb_container[name]


    def _create_image_item(self, name, data_matrix):
        """ Helper method to create an Image Item.

        @param str name: the name of the image object
        @param np.array data_matrix: the data matrix for the image

        @return: ScanImageItem object
        """

        # store for convenience all the colorbars in a container
        self._image_container[name] = ScanImageItem(image=data_matrix, 
                                                    axisOrder='row-major')
        return self._image_container[name]


    def setColorMap(self, cmap_name):
        """ Sets the current color map, and then color scale based on 
            Matplotlib colormap name

        @param str cmap_name: sets the colormap name and colorscale
        """
        self._color_map = cmap_name
        self._qafm_logic.set_color_map(self._color_map)
        color_scheme = ColorScaleGen(cmap_name)
        self.setColorScale(color_scheme)

    def getColorMap(self):
        """ Gets the current color map definition in use 

            'colormap' --> matplotlib colormap definition
            'colorscale' ('._current_cs') --> equivalent color scale for pyqtgraph

        @return str colormap_name
        """
        return self._color_map


    def setColorScale(self, cscale):
        """ Replace the current color scale. 

        @param ColorScale cscale: object which contains all the relevant 
                                  definition of a color scale.

        @return object ColorScale: current ColorScale object
        """
        self._current_cs = cscale

        for key, image_item in self._image_container.items():
            image_item = self._image_container[key]
            colorbar = self._cb_container[key]

            colorbar.setColorMap(cscale.cmap_normed)
            image_item.setLookupTable(cscale.lut)

        return self.getColorScale()


    def getColorScale(self):
        """ Obtain the currently used ColorScale. 

        @return object ColorScale: current ColorScale object
        """
        return self._current_cs


    def _create_plot_item(self, name, x_axis, y_axis):
        """ Create a plot item to display 1D measurements.

        @param str name: The name for the Plot Item
        @param np.array x_axis: 1D array containing values for x axis (in SI)
        @param np.array y_axis: 1D array containing values for y axis (in SI)

        @return pyqtgraph.PlotDataItem: object holding the 1D measurement.
        """
        _pen = pg.mkPen(palette.c1,style=QtCore.Qt.DotLine)
        _palette = palette.c1
        _width = 4
        _symbolSize = 7
        _symbol = 'o'
        if 'fit' in name:
            _pen = pg.mkPen(palette.c2,style=QtCore.Qt.SolidLine)
            _palette = palette.c2
            _width = 2
            _symbol = 'd'
            _symbolSize = 3
        self._plot_container[name] = pg.PlotDataItem(x=x_axis, y=y_axis,
                                                     pen=_pen,
                                                     symbol=_symbol,
                                                     symbolPen=_palette,
                                                     symbolBrush=_palette,
                                                     symbolSize=_symbolSize,
                                                     width=_width
                                                    )
        return self._plot_container[name]
    
    def create_linked_timetrace_plot(self, dockwidget, data_dict, obj_name):

        plot_item = self._create_timetrace_plot_item(obj_name, 
                        data_dict[obj_name]['x_axis'], 
                        data_dict[obj_name]['data'])
        plot_item_temperature = self._create_linked_timetrace_plot_item(obj_name+'_temperature', 
                        data_dict[obj_name]['x_axis'], 
                        data_dict[obj_name]['temperature_data'])

        dockwidget.graphicsView.addItem(plot_item)
        data_name = data_dict[obj_name]['data_info']['nice_name']
        meas_units = data_dict[obj_name]['data_info']['si_units']
        temperature_data_name = data_dict[obj_name]['temperature_info']['nice_name']
        temperature_units = data_dict[obj_name]['temperature_info']['si_units']
        x_axis_name = data_dict[obj_name]['x_axis_info']['nice_name']
        x_axis_units = data_dict[obj_name]['x_axis_info']['si_units']
        dockwidget.graphicsView.setLabel('bottom', x_axis_name, units=x_axis_units)
        dockwidget.graphicsView.setLabel('left', data_name, units=meas_units, color = palette.c1.name())
        dockwidget.graphicsView.showAxis('right')
        dockwidget.graphicsView.getAxis('right').setLabel(temperature_data_name, units=temperature_units, color = palette.c2.name())
        linked_plot = pg.ViewBox()
        dockwidget.graphicsView.scene().addItem(linked_plot)
        dockwidget.graphicsView.getAxis('right').linkToView(linked_plot)
        linked_plot.setXLink(dockwidget.graphicsView)
        linked_plot.addItem(plot_item_temperature)
        def updateViews():
            linked_plot.setGeometry(dockwidget.graphicsView.getViewBox().sceneBoundingRect())
            linked_plot.linkedViewChanged(dockwidget.graphicsView.getViewBox(), linked_plot.XAxis)
        dockwidget.updateViews = updateViews
        updateViews()
        dockwidget.graphicsView.getViewBox().sigResized.connect(updateViews)
    
    def _create_timetrace_plot_item(self, name, x_axis, y_axis):
        _pen = pg.mkPen(palette.c1,style=QtCore.Qt.SolidLine)
        _width = 4
        self._plot_container[name] = pg.PlotDataItem(x=x_axis, y=y_axis,
                                                     pen=_pen,
                                                     symbol=None,
                                                     width=_width
                                                    )
        return self._plot_container[name]
    
    def _create_linked_timetrace_plot_item(self, name, x_axis, y_axis):
        _pen = pg.mkPen(palette.c2,style=QtCore.Qt.SolidLine)
        _width = 4
        self._plot_container[name] = pg.PlotDataItem(x=x_axis, y=y_axis,
                                                     pen=_pen,
                                                     symbol=None,
                                                     width=_width
                                                    )
        return self._plot_container[name]

    def _set_aspect_ratio_images(self):
        for entry in self._image_container:
            self._image_container[entry].getViewBox().setAspectLocked(lock=True, ratio=1.0)
        
    # ========================================================================== 
    #         BEGIN: Creation and Adaptation of Display Widget
    # ========================================================================== 

    def _create_dockwidgets(self):
        """ Generate all the required DockWidgets. 

        To understand the creation procedure of the Display Widgets, it is 
        instructive to consider the file 'simple_dockwidget_example.ui'. The file 
        'simple_dockwidget_example.py' is the translated python file of the ui 
        file. The translation can be repeated with the pyui5 tool (usually an 
        *.exe or a *.bat file in the 'Scripts' folder of your python distribution)
        by running
              pyui5.exe simple_dockwidget_example.ui > simple_dockwidget_example.py
        From the 'simple_dockwidget_example.py' you will get the understanding
        how to create the dockwidget and its internal widgets in a correct way 
        (i.e. how to connect all of them properly together).
        The idea of the following methods are based on this creating process.

        The hierarchy looks like this

        DockWidget
            DockWidgetContent
                GraphicsView_1 (for main data)
                GraphicsView_2 (for colorbar)
                QDoubleSpinBox_1 (for minimal abs value)
                QDoubleSpinBox_2 (for minimal percentile)
                QDoubleSpinBox_3 (for maximal abs value)
                QDoubleSpinBox_4 (for maximal percentile)
                QRadioButton_1 (to choose abs value)
                QRadioButton_2 (to choose percentile)
                QCheckBox_1 (to set tilt correction)
              
        DockWidgetContent is a usual QWidget, hosting the internal content of the 
        DockWidget.

        Another good reference:
          https://www.geeksforgeeks.org/pyqt5-qdockwidget-setting-multiple-widgets-inside-it/

        """

        self._dock_state = ''

        ref_last_dockwidget = None
        is_first = True

        data_dict = self.initialize_all_data_matrices()
        c_scale = self.getColorScale()

        for obj_name in data_dict:

            # connect all dock widgets to the central widget
            dockwidget = QtWidgets.QDockWidget(self._mw.centralwidget)

            self._dockwidget_container[obj_name] = dockwidget
            setattr(self._mw,  f'dockWidget_{obj_name}', dockwidget)
            dockwidget.name = obj_name # store the original name. 

            # take a different creation style for line widgets
            if '1D' in obj_name or 'Timetrace' in obj_name:
                self._create_internal_line_widgets(dockwidget)
            else: 
                self._create_internal_widgets(dockwidget)

            dockwidget.setWindowTitle(obj_name)
            dockwidget.setObjectName(f'dockWidget_{obj_name}')

            # set size policy for dock widget
            sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                               QtWidgets.QSizePolicy.Preferred)
            sizePolicy.setHorizontalStretch(0)
            sizePolicy.setVerticalStretch(0)
            sizePolicy.setHeightForWidth(dockwidget.sizePolicy().hasHeightForWidth())
            dockwidget.setSizePolicy(sizePolicy)

            if is_first:
                self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), dockwidget)
                # QtCore.Qt.Orientation(1): horizontal orientation
                is_first = False
            else:
                self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(4), dockwidget)
                self._mw.tabifyDockWidget(ref_last_dockwidget, dockwidget)

            # for optimizer, the creation is a line item, not an 2d image
            if '1D' in obj_name:

                plot_item = self._create_plot_item(obj_name, 
                               data_dict[obj_name]['x_axis'], 
                               data_dict[obj_name]['data'])

                dockwidget.graphicsView.addItem(plot_item)
                data_name = data_dict[obj_name]['data_info']['nice_name']
                meas_units = data_dict[obj_name]['data_info']['si_units']
                x_axis_name = data_dict[obj_name]['x_axis_info']['nice_name']
                x_axis_units = data_dict[obj_name]['x_axis_info']['si_units']
                dockwidget.graphicsView.setLabel('bottom', x_axis_name, units=x_axis_units)
                dockwidget.graphicsView.setLabel('left', data_name, units=meas_units)

            elif 'Timetrace' in obj_name:
                self.create_linked_timetrace_plot(dockwidget, data_dict, obj_name)

            else:
                image_item = self._create_image_item(obj_name, data_dict[obj_name]['data'])
                dockwidget.graphicsView_matrix.addItem(image_item)
                
                c_scale = ColorScaleGen('bwr')

                image_item.setLookupTable(c_scale.lut)
                colorbar = self._create_colorbar(obj_name, c_scale)
                dockwidget.graphicsView_cb.addItem(colorbar)
                dockwidget.graphicsView_cb.hideAxis('bottom')

                data_name = data_dict[obj_name]['data_info']['nice_name']
                meas_units = data_dict[obj_name]['data_info']['si_units']

                dockwidget.graphicsView_cb.setLabel('left', data_name, units=meas_units)
                dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)

                x_axis_name = data_dict[obj_name]['x_axis_info']['nice_name']
                x_axis_units = data_dict[obj_name]['x_axis_info']['si_units']
                y_axis_name = data_dict[obj_name]['y_axis_info']['nice_name']
                y_axis_units = data_dict[obj_name]['y_axis_info']['si_units']
                dockwidget.graphicsView_matrix.setLabel('bottom', x_axis_name, units=x_axis_units)
                dockwidget.graphicsView_matrix.setLabel('left', y_axis_name, units=y_axis_units)

            ref_last_dockwidget = dockwidget

    def _create_internal_line_widgets(self, parent_dock):

        parent = parent_dock 

        # Create a Content Widget to which a layout can be attached.
        # add the content widget to the dockwidget
        content = QtWidgets.QWidget(parent)
        parent.dockWidgetContent = content
        parent.dockWidgetContent.setObjectName("dockWidgetContent")
        parent.setWidget(content)

        # create the only widget
        parent_dock.graphicsView = graphicsView = PlotWidget(content)
        graphicsView.setObjectName("graphicsView")

        # create Size Policy for the widget.
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, 
                                           QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(graphicsView.sizePolicy().hasHeightForWidth())
        graphicsView.setSizePolicy(sizePolicy)

        # create a grid layout
        grid = QtWidgets.QGridLayout(content)
        parent.gridLayout = grid
        parent.gridLayout.setObjectName("gridLayout")

        # arrange on grid
        grid.addWidget(graphicsView, 0, 0, 1, 1)


    def _create_internal_widgets(self, parent_dock, skip_colorcontrol=False):
        """  Create all the internal widgets for the dockwidget.

        @params parent_dock: the reference to the parent dock widget, which will
                             host the internal widgets
        """
        parent = parent_dock 

        # Create a Content Widget to which a layout can be attached.
        # add the content widget to the dockwidget
        content = QtWidgets.QWidget(parent)
        parent.dockWidgetContent = content
        parent.dockWidgetContent.setObjectName("dockWidgetContent")
        parent.setWidget(content)

        # create at first all required widgets

        parent_dock.graphicsView_matrix = graphicsView_matrix = ScanPlotWidget(content)
        graphicsView_matrix.setObjectName("graphicsView_matrix")

        parent.doubleSpinBox_cb_max = doubleSpinBox_cb_max = ScienDSpinBox(content)
        doubleSpinBox_cb_max.setObjectName("doubleSpinBox_cb_max")
        doubleSpinBox_cb_max.setMinimum(-100e9)
        doubleSpinBox_cb_max.setMaximum(100e9)

        parent_dock.doubleSpinBox_per_max = doubleSpinBox_per_max = ScienDSpinBox(content)
        doubleSpinBox_per_max.setObjectName("doubleSpinBox_per_max")
        doubleSpinBox_per_max.setMinimum(0)
        doubleSpinBox_per_max.setMaximum(100)
        doubleSpinBox_per_max.setValue(100.0)
        doubleSpinBox_per_max.setSuffix('%')

        parent_dock.graphicsView_cb = graphicsView_cb = ScanPlotWidget(content)
        graphicsView_cb.setObjectName("graphicsView_cb")

        parent_dock.doubleSpinBox_per_min = doubleSpinBox_per_min = ScienDSpinBox(content)
        doubleSpinBox_per_min.setObjectName("doubleSpinBox_per_min")
        doubleSpinBox_per_min.setMinimum(0)
        doubleSpinBox_per_min.setMaximum(100)
        doubleSpinBox_per_min.setValue(0.0)
        doubleSpinBox_per_min.setSuffix('%')
        doubleSpinBox_per_min.setMinimalStep(0.05)

        parent_dock.doubleSpinBox_cb_min = doubleSpinBox_cb_min = ScienDSpinBox(content)
        doubleSpinBox_cb_min.setObjectName("doubleSpinBox_cb_min")
        doubleSpinBox_cb_min.setMinimum(-100e9)
        doubleSpinBox_cb_min.setMaximum(100e9)

        parent.radioButton_cb_man = radioButton_cb_man = QtWidgets.QRadioButton(content)
        radioButton_cb_man.setObjectName("radioButton_cb_man")
        radioButton_cb_man.setText('Manual')
        parent_dock.radioButton_cb_per = radioButton_cb_per = QtWidgets.QRadioButton(content)
        radioButton_cb_per.setObjectName("radioButton_cb_per")
        radioButton_cb_per.setText('Percentiles')
        radioButton_cb_per.setChecked(True)

        # create required functions to react on change of the Radiobuttons:
        def cb_per_update(value):
            radioButton_cb_per.setChecked(True)
            self.sigColorBarChanged.emit(parent_dock.name)

        def cb_man_update(value):
            radioButton_cb_man.setChecked(True)
            self.sigColorBarChanged.emit(parent_dock.name)

        parent_dock.cb_per_update = cb_per_update
        doubleSpinBox_per_min.valueChanged.connect(cb_per_update)
        doubleSpinBox_per_max.valueChanged.connect(cb_per_update)
        parent_dock.cb_man_update = cb_man_update
        doubleSpinBox_cb_min.valueChanged.connect(cb_man_update)
        doubleSpinBox_cb_max.valueChanged.connect(cb_man_update)

        # create SizePolicy for only one spinbox, all the other spin boxes will
        # follow this size policy if not specified otherwise.
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, 
                                           QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(doubleSpinBox_cb_max.sizePolicy().hasHeightForWidth())
        doubleSpinBox_cb_max.setSizePolicy(sizePolicy)
        doubleSpinBox_cb_max.setMaximumSize(QtCore.QSize(100, 16777215))

        # create Size Policy for the colorbar. Let it extend in vertical direction.
        # Horizontal direction will be limited by the spinbox above.
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, 
                                           QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(graphicsView_cb.sizePolicy().hasHeightForWidth())
        graphicsView_cb.setSizePolicy(sizePolicy)
        graphicsView_cb.setMinimumSize(QtCore.QSize(80, 150))
        graphicsView_cb.setMaximumSize(QtCore.QSize(80, 16777215))

        # create a grid layout
        grid = QtWidgets.QGridLayout(content)
        parent.gridLayout = grid
        parent.gridLayout.setObjectName("gridLayout")

        # finally, arrange widgets on grid:
        # there are in total 7 rows, count runs from top to button, from left to
        # right.
        # it is (widget, fromRow, fromColum, rowSpan, columnSpan)
        grid.addWidget(graphicsView_matrix,   0, 0, 7, 1) # start [0,0], span 7 rows down, 1 column wide
        grid.addWidget(doubleSpinBox_cb_max,  0, 1, 1, 1) # start [0,1], span 1 rows down, 1 column wide
        grid.addWidget(doubleSpinBox_per_max, 1, 1, 1, 1) # start [1,1], span 1 rows down, 1 column wide
        grid.addWidget(graphicsView_cb,       2, 1, 1, 1) # start [2,1], span 1 rows down, 1 column wide
        grid.addWidget(doubleSpinBox_per_min, 3, 1, 1, 1) # start [3,1], span 1 rows down, 1 column wide
        grid.addWidget(doubleSpinBox_cb_min,  4, 1, 1, 1) # start [4,1], span 1 rows down, 1 column wide
        grid.addWidget(radioButton_cb_man,    5, 1, 1, 1) # start [5,1], span 1 rows down, 1 column wide
        grid.addWidget(radioButton_cb_per,    6, 1, 1, 1) # start [6,1], span 1 rows down, 1 column wide

    # ========================================================================== 
    #          END: Creation and Adaptation of Display Widget
    # ========================================================================== 
    # ========================================================================== 
    #                       View related methods 
    # ========================================================================== 

    def save_view(self):
        """Saves the current GUI state as a QbyteArray.
           The .data() function will transform it to a bytearray, 
           which can be saved as a StatusVar and read by the load_view method. 
        """
        self._save_display_view = self._mw.saveState().data() 
        

    def load_view(self):
        """Loads the saved state from the GUI and can read a QbyteArray
            or a simple byteArray aswell.
        """
        if self._save_display_view is None:
            pass
        else:
            self._mw.restoreState(self._save_display_view)


    def default_view(self):
        """Restore the arrangement of DockWidgets to the default and
           unchecks any Scan parameter that was previously selected.
        """
        self._mw.restoreState(self.saved_default_view)

        self._dock_state == 'double'

    def adjust_1D_transport_image(self):
        data_1D = self._transport_logic.get_1D_data()
        self.show_dockwidgets(data_1D.keys())

        for param_name in data_1D:
            dw = self.get_dockwidget(param_name)
            data_name = data_1D[param_name]['data_info']['nice_name']
            meas_units = data_1D[param_name]['data_info']['si_units']
            x_axis_name = data_1D[param_name]['x_axis_info']['nice_name']
            x_axis_units = data_1D[param_name]['x_axis_info']['si_units']
            dw.graphicsView.setLabel('bottom', x_axis_name, units=x_axis_units)
            dw.graphicsView.setLabel('left', data_name, units=meas_units)
            self._plot_container[param_name].setData(x=data_1D[param_name]['x_axis'], 
                                                   y=data_1D[param_name]['data'])

            self._plot_container[param_name].getViewBox().updateAutoRange()

    def adjust_2D_transport_image(self):
        data_2D = self._transport_logic.get_2D_data()
        self.show_dockwidgets(data_2D.keys())

        for param_name in data_2D:
            dw = self.get_dockwidget(param_name)
            data = data_2D[param_name]['data'].copy()
            
            data_name = data_2D[param_name]['data_info']['nice_name']
            meas_units = data_2D[param_name]['data_info']['si_units']
            x_axis_name = data_2D[param_name]['x_axis_info']['nice_name']
            x_axis_units = data_2D[param_name]['x_axis_info']['si_units']
            y_axis_name = data_2D[param_name]['y_axis_info']['nice_name']
            y_axis_units = data_2D[param_name]['y_axis_info']['si_units']
            dw.graphicsView_cb.setLabel('left', data_name, units=meas_units)
            dw.graphicsView_matrix.setLabel('bottom', x_axis_name, units=x_axis_units)
            dw.graphicsView_matrix.setLabel('left', y_axis_name, units=y_axis_units)
            
            cb_range = self._get_scan_cb_range(param_name,data=data)

            if data_2D[param_name]['display_range'] is not None:
                data_2D[param_name]['display_range'] = cb_range 

            self._image_container[param_name].setImage(image=data,
                                                    levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(param_name, data=data)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[param_name].getViewBox().updateAutoRange()

    def adjust_timetrace_transport_image(self):
        data_timetrace = self._transport_logic.get_timetrace_data()
        self.show_dockwidgets(data_timetrace.keys())

        for param_name in data_timetrace:
            dw = self.get_dockwidget(param_name)
            data_name = data_timetrace[param_name]['data_info']['nice_name']
            meas_units = data_timetrace[param_name]['data_info']['si_units']
            dw.graphicsView.setLabel('left', data_name, units=meas_units)
            self._plot_container[param_name].setData(x=data_timetrace[param_name]['x_axis'], 
                                                   y=data_timetrace[param_name]['data'])
            self._plot_container[param_name+'_temperature'].setData(x=data_timetrace[param_name]['x_axis'], 
                                                   y=data_timetrace[param_name]['temperature_data'])

            self._plot_container[param_name].getViewBox().updateAutoRange()

    def show_dockwidgets(self, meas_params):
        dockwidgets = self._dockwidget_container
        for name in dockwidgets.keys():
            self.update_dockwidget_visibility(name in meas_params, name)

    def update_dockwidget_visibility(self, make_visible, name):
        """ Hide or show a dockwidget. 

        @param bool make_visible: whether it should be hidden or show up.
        @param str name: name associated to the dockwidget. 
        """
        dockwidget = self.get_dockwidget(name)
        if dockwidget is not None:
            if make_visible:
                dockwidget.show()
            else:
                dockwidget.hide()

    def _update_1D_transport_data(self):
        """ Update all 1D displays of the transport measurement with data from the logic. """

        data_1D = self._transport_logic.get_1D_data()

        for param_name in data_1D:
            self._plot_container[param_name].setData(x=data_1D[param_name]['x_axis'], 
                                                   y=data_1D[param_name]['data'])

            self._plot_container[param_name].getViewBox().updateAutoRange()

    def _update_2D_transport_data(self):
        """ Update all 2D displays of the transport scan with data from the logic. """
        data_2D = self._transport_logic.get_2D_data()

        for param_name in data_2D:

            data = data_2D[param_name]['data'].copy()
            
            if not np.any(data):
                continue
            
            cb_range = self._get_scan_cb_range(param_name,data=data)

            if data_2D[param_name]['display_range'] is not None:
                data_2D[param_name]['display_range'] = cb_range 

            self._image_container[param_name].setImage(image=data,
                                                    levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(param_name, data=data)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[param_name].getViewBox().updateAutoRange()

    def _update_timetrace_transport_data(self):
        data_timetrace = self._transport_logic.get_timetrace_data()

        for param_name in data_timetrace:
            self._plot_container[param_name].setData(x=data_timetrace[param_name]['x_axis'], 
                                                   y=data_timetrace[param_name]['data'])
            self._plot_container[param_name+'_temperature'].setData(x=data_timetrace[param_name]['x_axis'], 
                                                   y=data_timetrace[param_name]['temperature_data'])

            # self._plot_container[param_name].getViewBox().updateAutoRange()
            # self._plot_container[param_name+'_temperature'].getViewBox().updateAutoRange()

    def _update_data_from_dockwidget(self, dockwidget_name):
        """ Update all displays of the dockwidget with data from logic.

        @param str dockwidget_name: name of the associated dockwidget.
        """

        data_obj = self.get_all_data_matrices()[dockwidget_name]
        data = data_obj['data'].copy()

        cb_range = self._get_scan_cb_range(dockwidget_name,data=data)

        # the name of the image object has to be the same as the dockwidget
        self._image_container[dockwidget_name].setImage(image=data, levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(dockwidget_name, data=data)
        # self._image_container[dockwidget_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
        self._image_container[dockwidget_name].getViewBox().updateAutoRange()

        # Be careful! I use here the feature that dicts are passed by reference,
        # i.e. changing this object, will change the initial data!
        data_obj['display_range'] = [ c for c in cb_range]
    
    def _get_scan_cb_range(self, dockwidget_name,data=None):
        """ Determines the cb_min and cb_max values for the xy scan image.
        @param str dockwidget_name: name associated to the dockwidget.

        """
        
        dockwidget = self.get_dockwidget(dockwidget_name)

        if data is None:
            data = self._image_container[dockwidget_name].image

        # If "Manual" is checked, or the image data is empty (all zeros), then take manual cb range.
        if dockwidget.radioButton_cb_man.isChecked() or np.count_nonzero(data) < 1:
            cb_min = dockwidget.doubleSpinBox_cb_min.value()
            cb_max = dockwidget.doubleSpinBox_cb_max.value()

        # Otherwise, calculate cb range from percentiles.
        else:
            # Exclude any zeros (which are typically due to unfinished scan)
            data_nonzero = data[np.nonzero(data)]

            # Read centile range
            low_centile = dockwidget.doubleSpinBox_per_min.value()
            high_centile = dockwidget.doubleSpinBox_per_max.value()

            cb_min = np.nanpercentile(data_nonzero, low_centile)
            cb_max = np.nanpercentile(data_nonzero, high_centile)

        cb_range = [cb_min, cb_max]
        if cb_range == [np.nan,np.nan]:
            cb_range = [0,1]

        return cb_range


    def _refresh_scan_colorbar(self, dockwidget_name, data=None):
        """ Update the colorbar of the Dockwidget.

        @param str dockwidget_name: the name of the dockwidget to update.
        """

        cb_range =  self._get_scan_cb_range(dockwidget_name,data=data)
        self._cb_container[dockwidget_name].refresh_colorbar(cb_range[0], cb_range[1])


    def get_dockwidget(self, objectname):
        """ Get the reference to the dockwidget associated to the objectname.

        @param str objectname: name under which the dockwidget can be found.
        """

        dw = self._dockwidget_container.get(objectname)
        if dw is None:
            self.log.warning(f'No dockwidget with name "{objectname}" was found! Be careful!')

        return dw

    def disable_scan_actions(self):
        # for safety, store status variables
        self.store_status_var()
        self.store_settings_status_var()

        self._mw.action_run.blockSignals(True)
        self._mw.action_run.setEnabled(False)

        self._mw.action_toggle_constant_output.setEnabled(False)
        self._mw.constant_sample_current_checkBox.setEnabled(False)
        self._mw.constant_sample_current_DoubleSpinBox.setEnabled(False)
        self._mw.constant_sample_voltage_checkBox.setEnabled(False)
        self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(False)
        self._mw.constant_backgate_voltage_checkBox.setEnabled(False)
        self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(False)
        self._mw.dimension_comboBox.setEnabled(False)
        self._mw.x_axis_sweep_parameter_comboBox.setEnabled(False)
        self._mw.x_axis_start_DoubleSpinBox.setEnabled(False)
        self._mw.x_axis_stop_DoubleSpinBox.setEnabled(False)
        self._mw.x_axis_points_DoubleSpinBox.setEnabled(False)
        self._mw.y_axis_sweep_parameter_comboBox.setEnabled(False)
        self._mw.y_axis_start_DoubleSpinBox.setEnabled(False)
        self._mw.y_axis_stop_DoubleSpinBox.setEnabled(False)
        self._mw.y_axis_points_DoubleSpinBox.setEnabled(False)

        self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setEnabled(False)
        self._sd.gate_voltage_upper_limit_DoubleSpinBox.setEnabled(False)
        self._sd.gate_voltage_lower_limit_DoubleSpinBox.setEnabled(False)
        self._sd.gate_voltage_autorange_checkBox.setEnabled(False)
        self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setEnabled(False)
        self._sd.sample_voltage_upper_limit_DoubleSpinBox.setEnabled(False)
        self._sd.sample_voltage_lower_limit_DoubleSpinBox.setEnabled(False)
        self._sd.sample_current_ramp_speed_DoubleSpinBox.setEnabled(False)
        self._sd.sample_current_upper_limit_DoubleSpinBox.setEnabled(False)
        self._sd.sample_current_lower_limit_DoubleSpinBox.setEnabled(False)
        self._sd.sample_transport_autorange_checkBox.setEnabled(False)

        self._mw.sensing_function_comboBox.setEnabled(False)
        self._sd.sensing_autorange_checkBox.setEnabled(False)
        self._sd.sensing_autozero_checkBox.setEnabled(False)
        self._sd.sensing_four_port_checkBox.setEnabled(False)
        self._sd.sensing_achange_checkBox.setEnabled(False)
        self._sd.sensing_delay_DoubleSpinBox.setEnabled(False)
        self._sd.int_time_transport_DoubleSpinBox.setEnabled(False)

    def enable_scan_actions(self):
        self._mw.action_stop.blockSignals(True)
        self._mw.action_stop.setEnabled(False)
        self._mw.action_run.blockSignals(False)
        self._mw.action_run.setEnabled(True)

        self._mw.action_toggle_constant_output.setEnabled(True)
        self._mw.constant_sample_current_checkBox.setEnabled(True)
        self._mw.constant_sample_current_DoubleSpinBox.setEnabled(self._mw.constant_sample_current_checkBox.isChecked())
        self._mw.constant_sample_voltage_checkBox.setEnabled(True)
        self._mw.constant_sample_voltage_DoubleSpinBox.setEnabled(self._mw.constant_sample_voltage_checkBox.isChecked())
        self._mw.constant_backgate_voltage_checkBox.setEnabled(True)
        self._mw.constant_backgate_voltage_DoubleSpinBox.setEnabled(self._mw.constant_backgate_voltage_checkBox.isChecked())
        self._mw.dimension_comboBox.setEnabled(True)
        if self._mw.dimension_comboBox.currentIndex() != 2:
            self._mw.x_axis_label.setEnabled(True)
            self._mw.x_axis_sweep_parameter_comboBox.setEnabled(True)
            self._mw.x_start_label.setEnabled(True)
            self._mw.x_axis_start_DoubleSpinBox.setEnabled(True)
            self._mw.x_stop_label.setEnabled(True)
            self._mw.x_axis_stop_DoubleSpinBox.setEnabled(True)
            self._mw.x_axis_points_label.setEnabled(True)
            self._mw.x_axis_points_DoubleSpinBox.setEnabled(True)

        if self._mw.dimension_comboBox.currentIndex() == 1:
            self._mw.y_axis_label.setEnabled(True)
            self._mw.y_axis_sweep_parameter_comboBox.setEnabled(True)
            self._mw.y_start_label.setEnabled(True)
            self._mw.y_axis_start_DoubleSpinBox.setEnabled(True)
            self._mw.y_stop_label.setEnabled(True)
            self._mw.y_axis_stop_DoubleSpinBox.setEnabled(True)
            self._mw.y_axis_points_label.setEnabled(True)
            self._mw.y_axis_points_DoubleSpinBox.setEnabled(True)

        self._sd.gate_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
        self._sd.gate_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
        self._sd.gate_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
        self._sd.gate_voltage_autorange_checkBox.setEnabled(True)
        self._sd.sample_voltage_ramp_speed_DoubleSpinBox.setEnabled(True)
        self._sd.sample_voltage_upper_limit_DoubleSpinBox.setEnabled(True)
        self._sd.sample_voltage_lower_limit_DoubleSpinBox.setEnabled(True)
        self._sd.sample_current_ramp_speed_DoubleSpinBox.setEnabled(True)
        self._sd.sample_current_upper_limit_DoubleSpinBox.setEnabled(True)
        self._sd.sample_current_lower_limit_DoubleSpinBox.setEnabled(True)
        self._sd.sample_transport_autorange_checkBox.setEnabled(True)

        self._mw.sensing_function_comboBox.setEnabled(True)
        self._sd.sensing_autorange_checkBox.setEnabled(True)
        self._sd.sensing_autozero_checkBox.setEnabled(True)
        self._sd.sensing_four_port_checkBox.setEnabled(True)
        self._sd.sensing_achange_checkBox.setEnabled(True)
        self._sd.sensing_delay_DoubleSpinBox.setEnabled(True)
        self._sd.int_time_transport_DoubleSpinBox.setEnabled(True)

    def enable_stop_action(self):
        self._mw.action_stop.blockSignals(False)
        self._mw.action_stop.setEnabled(True)

    def start_2D_transport_scan(self):
        use_DC_sample_current = self._mw.constant_sample_current_checkBox.isChecked()
        DC_sample_current = self._mw.constant_sample_current_DoubleSpinBox.value()
        use_DC_sample_voltage = self._mw.constant_sample_voltage_checkBox.isChecked()
        DC_sample_voltage = self._mw.constant_sample_voltage_DoubleSpinBox.value()
        use_DC_backgate_voltage = self._mw.constant_backgate_voltage_checkBox.isChecked()
        DC_backgate_voltage = self._mw.constant_backgate_voltage_DoubleSpinBox.value()

        x_axis_sweep_parameter = self._mw.x_axis_sweep_parameter_comboBox.currentText()
        x_axis_start = self._mw.x_axis_start_DoubleSpinBox.value()
        x_axis_stop = self._mw.x_axis_stop_DoubleSpinBox.value()
        x_axis_num = self._mw.x_axis_points_DoubleSpinBox.value()

        y_axis_sweep_parameter = self._mw.y_axis_sweep_parameter_comboBox.currentText()
        y_axis_start = self._mw.y_axis_start_DoubleSpinBox.value()
        y_axis_stop = self._mw.y_axis_stop_DoubleSpinBox.value()
        y_axis_num = self._mw.y_axis_points_DoubleSpinBox.value()

        backgate_voltage_ramp_speed = self._sd.gate_voltage_ramp_speed_DoubleSpinBox.value()
        backgate_voltage_autorange = self._sd.gate_voltage_autorange_checkBox.isChecked()
        sample_voltage_ramp_speed = self._sd.sample_voltage_ramp_speed_DoubleSpinBox.value()
        sample_current_ramp_speed = self._sd.sample_current_ramp_speed_DoubleSpinBox.value()
        sample_transport_autorange = self._sd.sample_transport_autorange_checkBox.isChecked()

        sens_fnc = self._mw.sensing_function_comboBox.currentText()
        sens_autorange = self._sd.sensing_autorange_checkBox.isChecked()
        sens_autozero = self._sd.sensing_autozero_checkBox.isChecked()
        sens_four_port = self._sd.sensing_four_port_checkBox.isChecked()
        sens_achange =  self._sd.sensing_achange_checkBox.isChecked()
        sens_delay = self._sd.sensing_delay_DoubleSpinBox.value()
        sens_int_time = self._sd.int_time_transport_DoubleSpinBox.value()

        self.scan_type = f'X_{x_axis_sweep_parameter}_Y_{y_axis_sweep_parameter}_vs_{sens_fnc}'

        self._transport_logic.start_scan_2D_DC_transport(
            x_axis_sweep_parameter = x_axis_sweep_parameter, x_axis_start = x_axis_start, x_axis_stop = x_axis_stop, x_axis_num = x_axis_num,
            y_axis_sweep_parameter = y_axis_sweep_parameter, y_axis_start = y_axis_start, y_axis_stop = y_axis_stop, y_axis_num = y_axis_num,
            use_DC_sample_current = use_DC_sample_current, DC_sample_current = DC_sample_current,
            use_DC_sample_voltage = use_DC_sample_voltage, DC_sample_voltage = DC_sample_voltage,
            use_DC_backgate_voltage = use_DC_backgate_voltage, DC_backgate_voltage = DC_backgate_voltage,
            backgate_voltage_ramp_speed = backgate_voltage_ramp_speed, backgate_voltage_autorange = backgate_voltage_autorange,
            sample_voltage_ramp_speed = sample_voltage_ramp_speed, sample_current_ramp_speed = sample_current_ramp_speed, sample_transport_autorange = sample_transport_autorange,
            sens_fnc =sens_fnc, sens_autorange = sens_autorange, sens_autozero = sens_autozero, sens_four_port = sens_four_port,
            sens_achange = sens_achange, sens_delay = sens_delay, sens_int_time = sens_int_time)
    
    def start_1D_transport_scan(self):
        use_DC_sample_current = self._mw.constant_sample_current_checkBox.isChecked()
        DC_sample_current = self._mw.constant_sample_current_DoubleSpinBox.value()
        use_DC_sample_voltage = self._mw.constant_sample_voltage_checkBox.isChecked()
        DC_sample_voltage = self._mw.constant_sample_voltage_DoubleSpinBox.value()
        use_DC_backgate_voltage = self._mw.constant_backgate_voltage_checkBox.isChecked()
        DC_backgate_voltage = self._mw.constant_backgate_voltage_DoubleSpinBox.value()

        x_axis_sweep_parameter = self._mw.x_axis_sweep_parameter_comboBox.currentText()
        x_axis_start = self._mw.x_axis_start_DoubleSpinBox.value()
        x_axis_stop = self._mw.x_axis_stop_DoubleSpinBox.value()
        x_axis_num = self._mw.x_axis_points_DoubleSpinBox.value()

        backgate_voltage_ramp_speed = self._sd.gate_voltage_ramp_speed_DoubleSpinBox.value()
        backgate_voltage_autorange = self._sd.gate_voltage_autorange_checkBox.isChecked()
        sample_voltage_ramp_speed = self._sd.sample_voltage_ramp_speed_DoubleSpinBox.value()
        sample_current_ramp_speed = self._sd.sample_current_ramp_speed_DoubleSpinBox.value()
        sample_transport_autorange = self._sd.sample_transport_autorange_checkBox.isChecked()

        sens_fnc = self._mw.sensing_function_comboBox.currentText()
        sens_autorange = self._sd.sensing_autorange_checkBox.isChecked()
        sens_autozero = self._sd.sensing_autozero_checkBox.isChecked()
        sens_four_port = self._sd.sensing_four_port_checkBox.isChecked()
        sens_achange =  self._sd.sensing_achange_checkBox.isChecked()
        sens_delay = self._sd.sensing_delay_DoubleSpinBox.value()
        sens_int_time = self._sd.int_time_transport_DoubleSpinBox.value()

        self.scan_type = f'{x_axis_sweep_parameter}_vs_{sens_fnc}'

        self._transport_logic.start_scan_1D_DC_transport(
            x_axis_sweep_parameter = x_axis_sweep_parameter, x_axis_start = x_axis_start, x_axis_stop = x_axis_stop, x_axis_num = x_axis_num,
            use_DC_sample_current = use_DC_sample_current, DC_sample_current = DC_sample_current,
            use_DC_sample_voltage = use_DC_sample_voltage, DC_sample_voltage = DC_sample_voltage,
            use_DC_backgate_voltage = use_DC_backgate_voltage, DC_backgate_voltage = DC_backgate_voltage,
            backgate_voltage_ramp_speed = backgate_voltage_ramp_speed, backgate_voltage_autorange = backgate_voltage_autorange,
            sample_voltage_ramp_speed = sample_voltage_ramp_speed, sample_current_ramp_speed = sample_current_ramp_speed, sample_transport_autorange = sample_transport_autorange,
            sens_fnc =sens_fnc, sens_autorange = sens_autorange, sens_autozero = sens_autozero, sens_four_port = sens_four_port,
            sens_achange = sens_achange, sens_delay = sens_delay, sens_int_time = sens_int_time)
        
    def start_transport_timetrace(self):
        use_DC_sample_current = self._mw.constant_sample_current_checkBox.isChecked()
        DC_sample_current = self._mw.constant_sample_current_DoubleSpinBox.value()
        use_DC_sample_voltage = self._mw.constant_sample_voltage_checkBox.isChecked()
        DC_sample_voltage = self._mw.constant_sample_voltage_DoubleSpinBox.value()
        use_DC_backgate_voltage = self._mw.constant_backgate_voltage_checkBox.isChecked()
        DC_backgate_voltage = self._mw.constant_backgate_voltage_DoubleSpinBox.value()

        backgate_voltage_ramp_speed = self._sd.gate_voltage_ramp_speed_DoubleSpinBox.value()
        backgate_voltage_autorange = self._sd.gate_voltage_autorange_checkBox.isChecked()
        sample_voltage_ramp_speed = self._sd.sample_voltage_ramp_speed_DoubleSpinBox.value()
        sample_current_ramp_speed = self._sd.sample_current_ramp_speed_DoubleSpinBox.value()
        sample_transport_autorange = self._sd.sample_transport_autorange_checkBox.isChecked()

        timestep = self._sd.timetrace_timestep_DoubleSpinBox.value()
        measure_temperature = self._sd.timetrace_measure_temperature_checkBox.isChecked()

        sens_fnc = self._mw.sensing_function_comboBox.currentText()
        sens_autorange = self._sd.sensing_autorange_checkBox.isChecked()
        sens_autozero = self._sd.sensing_autozero_checkBox.isChecked()
        sens_four_port = self._sd.sensing_four_port_checkBox.isChecked()
        sens_achange =  self._sd.sensing_achange_checkBox.isChecked()
        sens_delay = self._sd.sensing_delay_DoubleSpinBox.value()
        sens_int_time = self._sd.int_time_transport_DoubleSpinBox.value()

        self.scan_type = f'time_vs_{sens_fnc}'

        self._transport_logic.start_timetrace_DC_transport(timestep, measure_temperature,
            use_DC_sample_current = use_DC_sample_current, DC_sample_current = DC_sample_current,
            use_DC_sample_voltage = use_DC_sample_voltage, DC_sample_voltage = DC_sample_voltage,
            use_DC_backgate_voltage = use_DC_backgate_voltage, DC_backgate_voltage = DC_backgate_voltage,
            backgate_voltage_ramp_speed = backgate_voltage_ramp_speed, backgate_voltage_autorange = backgate_voltage_autorange,
            sample_voltage_ramp_speed = sample_voltage_ramp_speed, sample_current_ramp_speed = sample_current_ramp_speed, sample_transport_autorange = sample_transport_autorange,
            sens_fnc =sens_fnc, sens_autorange = sens_autorange, sens_autozero = sens_autozero, sens_four_port = sens_four_port,
            sens_achange = sens_achange, sens_delay = sens_delay, sens_int_time = sens_int_time)
        
    def save_transport_data_clicked(self):
        """Method enabling the saving of the transport data.
        """
        self._mw.action_Save.setEnabled(False)

        tag = self.scan_type + '_' + self._mw.save_tag_LineEdit.text()
        save_to_gwyddion = self._sd.save_to_gwyddion_CheckBox.isChecked()
        self._transport_logic.save_transport_data(tag, save_to_gwyddion)

    def autosave_transport_data(self):
        if self._sd.auto_save_qafm_CheckBox.isChecked():
            self._mw.action_Save.setEnabled(False)

            tag = 'autosave_'+ self.scan_type + '_' + self._mw.save_tag_LineEdit.text()
            save_to_gwyddion = self._sd.save_to_gwyddion_CheckBox.isChecked()
            self._transport_logic.save_transport_data(tag, save_to_gwyddion)

    def enable_save_actions(self):
        self._mw.action_Save.setEnabled(True)