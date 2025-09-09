
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
from gui.fitsettings import FitSettingsDialog

from gui.guibase import GUIBase

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut
from PyQt5 import QtGui 

"""
Implementation Steps/TODOs:
- add default saveview as a file, which should be saved in the gui.
- check the colorbar implementation for smaller values => 32bit problem, quite hard...
"""

class CustomCheckBox(QtWidgets.QCheckBox):

    # with the current state and the name of the box
    valueChanged_custom = QtCore.Signal(bool, str)

    def __init__(self, parent=None):

        super(CustomCheckBox, self).__init__(parent)
        self.stateChanged.connect(self.emit_value_name)

    @QtCore.Slot(int)
    def emit_value_name(self, state):
        self.valueChanged_custom.emit(bool(state), self.objectName())

class QAFMPulseDataViewerMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_data_viewer_main_window.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()

class QAFMPulseDataViewerGUI(GUIBase):
    """ GUI to control the qAFM Scan. """

    ## declare connectors
    qafmlogic = Connector(interface='AFMConfocalLogic') # interface='AFMConfocalLogic'

    sigColorBarChanged = QtCore.Signal(str)  # emit a dockwidget object.

    saved_default_view = ConfigOption('saved_default_view', b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01\x04\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x03\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x01\x00\x00\x00D\x00\x00\x01\xd3\x00\x00\x01\xd3\x00\x07\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00p\x00t\x00i\x00_\x00x\x00y\x01\x00\x00\x02\x17\x00\x00\x01\x10\x00\x00\x01\x10\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00p\x00t\x00i\x00_\x00z\x01\x00\x00\x03+\x00\x00\x00\xba\x00\x00\x00f\x00\xff\xff\xff\x00\x00\x00\x01\x00\x00\x06x\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x02\xfb\x00\x00\x00\x1e\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00i\x00s\x00o\x00b\x00\x00\x00\x00D\x00\x00\x00\xa7\x00\x00\x00y\x00\xff\xff\xff\xfc\x00\x00\x00D\x00\x00\x03\xa1\x00\x00\x02\xc8\x00\xff\xff\xff\xfc\x01\x00\x00\x00\x03\xfc\x00\x00\x01\x08\x00\x00\x02\xb5\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0e\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00y\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00y\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfc\x00\x00\x03\xc1\x00\x00\x02\xbf\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0b\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00a\x00f\x00m\x01\x00\x00\x06\x84\x00\x00\x00\xfc\x00\x00\x00\xfc\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\x03\xa1\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x04\x00\x00\x00"\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00p\x00t\x00i\x00m\x00i\x00z\x00e\x00r\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x002\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x00h\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00t\x00o\x00p\x01\x00\x00\x01G\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00,\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00a\x00m\x00p\x00l\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x01\x82\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00')
    _config_color_map = ConfigOption('color_map')  # user specification in config file

    _image_container = {}
    _plot_container = {}
    _cb_container = {}
    _dockwidget_container = {}

    _data_view_tabs = ['d1', 'd2', 'd3', 'd4', 'Calculation', 'Fit', 'Pulsed_Measurement']
    _dataset_container = ['d1', 'd2', 'd3', 'd4']
    _dataset_combobox_container = []
    _dataset_index_container = []

    # status variables (will be saved at shutdown)
    _color_map = StatusVar('color_map', default='inferno')  # possible saved color map config
    _save_display_view = StatusVar('save_display_view', default=None) # It is a bytearray

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)


    def on_activate(self):
        """ Definition and initialization of the GUI. """
        self._qafm_logic = self.qafmlogic()

        # if self._config_color_map is not None:
        #     self._color_map = self._config_color_map

        # self._current_cs = ColorScaleGen(self._color_map)
        # self._qafm_logic.set_color_map(self._color_map)

        self.new_scan = True
        self.last_fit_method = 'None'
        self.last_fit_dataset = 'None'
        self.fitting_busy = False
        self.data_summary = self.init_data_summary()
        self.initMainUI()

        self.fc = self._qafm_logic._fitlogic.make_fit_container('pulsed', '1d')
        self.fc.set_units(self._qafm_logic._pulsed_master_AWG.pulsedmeasurementlogic()._data_units)
        # Recall saved status variables
        if 'fits' in self._statusVariables and isinstance(self._statusVariables.get('fits'), dict):
            self.fc.load_from_dict(self._statusVariables['fits'])

        self._fsd = FitSettingsDialog(self.fc)
        self._fsd.applySettings()
        self._mw.used_fit_comboBox.setFitFunctions(self._fsd.currentFits)
        self._fsd.sigFitsUpdated.connect(self._mw.used_fit_comboBox.setFitFunctions)
        self._mw.used_fit_comboBox.currentIndexChanged.connect(self.update_used_fit_parameter_comboBox)
        self._mw.actionFit_Settings.triggered.connect(self._fsd.show)
        
        self.sigColorBarChanged.connect(self._update_data_from_dockwidget)
        self._mw.actionDefault_Display.triggered.connect(self.default_view)
        self._mw.actionSave_Display.triggered.connect(self.save_view)
        self._mw.actionLoad_Display.triggered.connect(self.load_view)

        self._qafm_logic.sigQAFMLineScanFinished.connect(self.update_data_viewer_data_after_scanpoint)

        self._qafm_logic.sigQAFMScanInitialized.connect(self.new_scan_started)

        self.load_view()
        

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        if len(self.fc.fit_list) > 0:
            self._statusVariables['fits'] = self.fc.save_to_dict()
        self._mw.actionFit_Settings.triggered.disconnect()
        self.saveWindowGeometry(self._mw)
        self._mw.close()


    def show(self):
        """Make window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def init_data_summary(self):
        pulsed_data = self._qafm_logic.get_pulsed_data()
        dict = {}
        for data_tab in self._data_view_tabs:
            dict.update({data_tab: np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])})
        return dict
    
    def init_fit_dict(self, fit_method):
        fit_dict = {}
        pulsed_data = self._qafm_logic.get_pulsed_data()
        fit_params = self._fsd.getParameters(fit_method)
        for params in fit_params:
            fit_dict[params] = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
        fit_dict['analyzed'] = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
        return fit_dict
    
    def new_scan_started(self):
        if self._mw.update_after_scan_point_checkBox.isChecked():
            self.adjust_data_viewer_image()
        self.new_scan = True

    def initMainUI(self):
        """ Definition, configuration and initialisation of the confocal GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values.
        """
        self._mw = QAFMPulseDataViewerMainWindow()
        self.restoreWindowPos(self._mw)

        self.setup_dataset_combobox_and_index()
        self.adjust_dataset_index_DoubleSpinBox()
        self.adjust_coordinate_SpinBox()
        self._mw.update_after_scan_point_checkBox.stateChanged.connect(self.update_after_scan_point_checkbox_changed)
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)
        self._create_dockwidgets()
        self._set_aspect_ratio_images()
        self._mw.view_data_pushButton.clicked.connect(self.adjust_data_viewer_image)
        self._mw.view_pulsed_measurement_pushButton.clicked.connect(self.adjust_pulsed_measurement_image)
        self._mw.update_from_crosshair_pushButton.clicked.connect(self.update_from_crosshair)
        self._mw.update_from_crosshair_pushButton.setEnabled(False)
        self._mw.x_coord_index_SpinBox.editingFinished.connect(self.update_crosshair_pos_from_spinbox)
        self._mw.y_coord_index_SpinBox.editingFinished.connect(self.update_crosshair_pos_from_spinbox)
        self._mw.show_crosshair_checkBox.stateChanged.connect(self.toggle_crosshair)
        self._qafm_logic.sigQAFMScanInitialized.connect(self.adjust_dataset_index_DoubleSpinBox)
        self._qafm_logic.sigQAFMScanInitialized.connect(self.adjust_coordinate_SpinBox)

    def setup_dataset_combobox_and_index(self):
        self._dataset_combobox_container = [self._mw.dataset1_comboBox, self._mw.dataset2_comboBox, self._mw.dataset3_comboBox, self._mw.dataset4_comboBox]
        self._dataset_index_container = [self._mw.dataset1_index_SpinBox, self._mw.dataset2_index_SpinBox, self._mw.dataset3_index_SpinBox, self._mw.dataset4_index_SpinBox]

    def adjust_dataset_index_DoubleSpinBox(self):
        max_index = self._qafm_logic._pulsed_scan_array['pulsed_fw']['data'].shape[2]-1
        self._mw.dataset1_index_SpinBox.setMinimum(-1)
        self._mw.dataset1_index_SpinBox.setMaximum(max_index)
        self._mw.dataset2_index_SpinBox.setMinimum(-1)
        self._mw.dataset2_index_SpinBox.setMaximum(max_index)
        self._mw.dataset3_index_SpinBox.setMinimum(-1)
        self._mw.dataset3_index_SpinBox.setMaximum(max_index)
        self._mw.dataset4_index_SpinBox.setMinimum(-1)
        self._mw.dataset4_index_SpinBox.setMaximum(max_index)

    def adjust_coordinate_SpinBox(self):
        x_coord_max = self._qafm_logic._pulsed_scan_array['pulsed_fw']['coord0_arr'].shape[0]-1
        y_coord_max = self._qafm_logic._pulsed_scan_array['pulsed_fw']['coord1_arr'].shape[0]-1
        self._mw.x_coord_index_SpinBox.setMinimum(-1)
        self._mw.x_coord_index_SpinBox.setMaximum(x_coord_max)
        self._mw.y_coord_index_SpinBox.setMinimum(-1)
        self._mw.y_coord_index_SpinBox.setMaximum(y_coord_max)

    def update_used_fit_parameter_comboBox(self):
        current_fit = self._mw.used_fit_comboBox.currentText()
        self._mw.used_fit_parameter_comboBox.clear()
        self._mw.used_fit_parameter_comboBox.addItem('None')
        if current_fit != 'No Fit':
            for parameter in self._fsd.getParameters(current_fit):
                self._mw.used_fit_parameter_comboBox.addItem(parameter)
        self._mw.used_fit_parameter_comboBox.setCurrentIndex(0)

    def update_after_scan_point_checkbox_changed(self):
        if self._mw.update_after_scan_point_checkBox.isChecked():
            self._mw.view_data_pushButton.setEnabled(False)
            self.adjust_data_viewer_image()
        else:
            self._mw.view_data_pushButton.setEnabled(True)

    
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

    def setColorMap(self, cmap_name):
        """ Sets the current color map, and then color scale based on 
            Matplotlib colormap name

        @param str cmap_name: sets the colormap name and colorscale
        """
        self._color_map = cmap_name
        self._qafm_logic.set_color_map(self._color_map)
        color_scheme = ColorScaleGen(cmap_name)
        self.setColorScale(color_scheme)

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
        ref_last_dockwidget = None
        is_first = True

        pulsed_data = self._qafm_logic.get_pulsed_data()

        for obj_name in self._data_view_tabs:

            # connect all dock widgets to the central widget
            dockwidget = QtWidgets.QDockWidget(self._mw.centralwidget)

            self._dockwidget_container[obj_name] = dockwidget
            setattr(self._mw,  f'dockWidget_{obj_name}', dockwidget)
            dockwidget.name = obj_name # store the original name. 
            skip_colorcontrol = False

            # take a different creation style for line widgets
            if 'Pulsed_Measurement' in obj_name:
                self._create_internal_line_widgets(dockwidget)
            else: 
                self._create_internal_widgets(dockwidget, skip_colorcontrol)
            
            

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
                self._mw.splitDockWidget(dockwidget, self._mw.data_analysis_settings_dockWidget,
                                         QtCore.Qt.Orientation(1))
                is_first = False
            else:
                self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(4), dockwidget)
                self._mw.tabifyDockWidget(ref_last_dockwidget, dockwidget)

            if 'Pulsed_Measurement' in obj_name:
                plot_item = self._create_plot_item(obj_name, 
                               pulsed_data['pulsed_fw']['coord2_arr'], 
                               pulsed_data['pulsed_fw']['data'][0,0,:])

                dockwidget.graphicsView.addItem(plot_item)
                data_name = 'Signal'
                meas_units = 'arb. u.'
                x_axis_name = 'Tau'
                x_axis_units = 's'
                dockwidget.graphicsView.setLabel('bottom', x_axis_name, units=x_axis_units)
                dockwidget.graphicsView.setLabel('left', data_name, units=meas_units)
            
            else:
                image_item = self._create_image_item(obj_name, pulsed_data['pulsed_fw']['data'][:,:,0])
                dockwidget.graphicsView_matrix.addItem(image_item)
                c_scale = ColorScaleGen('bwr')


                image_item.setLookupTable(c_scale.lut)
                colorbar = self._create_colorbar(obj_name, c_scale)
                dockwidget.graphicsView_cb.addItem(colorbar)
                dockwidget.graphicsView_cb.hideAxis('bottom')

                data_name = obj_name
                #si_units = data_dict[obj_name]['si_units']
                meas_units = 'a.u.'

                dockwidget.graphicsView_cb.setLabel('left', data_name, units=meas_units)
                dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)
                dockwidget.graphicsView_matrix.setLabel('bottom', 'X position', units='m')
                dockwidget.graphicsView_matrix.setLabel('left', 'Y position', units='m')
                dockwidget.graphicsView_matrix.sigCrosshairDraggedPosChanged.connect(functools.partial(self.update_all_crosshair, obj_name))

            ref_last_dockwidget = dockwidget

            

        self.adjust_data_viewer_image()

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
        parent.checkBox_tilt_corr = checkBox_tilt_corr = CustomCheckBox(content)
        checkBox_tilt_corr.setObjectName("checkBox_tilt_corr")
        checkBox_tilt_corr.setText("Tilt correction")
        checkBox_tilt_corr.setVisible(False)   # this will only be enabled for Heights

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
        if skip_colorcontrol:
            grid.addWidget(graphicsView_matrix,   0, 0, 1, 1) # start [0,0], span 7 rows down, 1 column wide
            doubleSpinBox_cb_max.hide()
            doubleSpinBox_per_max.hide()
            grid.addWidget(graphicsView_cb,       0, 1, 1, 1) # start [2,1], span 1 rows down, 1 column wide
            doubleSpinBox_per_min.hide()
            doubleSpinBox_cb_min.hide()
            radioButton_cb_man.hide()
            radioButton_cb_per.hide()
            checkBox_tilt_corr.hide()
        else:

            grid.addWidget(graphicsView_matrix,   0, 0, 7, 1) # start [0,0], span 7 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_cb_max,  0, 1, 1, 1) # start [0,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_per_max, 1, 1, 1, 1) # start [1,1], span 1 rows down, 1 column wide
            grid.addWidget(graphicsView_cb,       2, 1, 1, 1) # start [2,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_per_min, 3, 1, 1, 1) # start [3,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_cb_min,  4, 1, 1, 1) # start [4,1], span 1 rows down, 1 column wide
            grid.addWidget(radioButton_cb_man,    5, 1, 1, 1) # start [5,1], span 1 rows down, 1 column wide
            grid.addWidget(radioButton_cb_per,    6, 1, 1, 1) # start [6,1], span 1 rows down, 1 column wide
            grid.addWidget(checkBox_tilt_corr,    7, 0, 1, 1) # start [7,0], span 1 rows down, 1 column wide

    # ========================================================================== 
    #          END: Creation and Adaptation of Display Widget
    # ========================================================================== 
    # ========================================================================== 
    #                       View related methods 
    # ========================================================================== 

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

    def toggle_crosshair(self):
        pulsed_data = self._qafm_logic.get_pulsed_data()
        x_index = self._mw.x_coord_index_SpinBox.value()
        y_index = self._mw.y_coord_index_SpinBox.value()
        state = self._mw.show_crosshair_checkBox.isChecked()
        for key in self._dockwidget_container.keys():
            if key is not 'Pulsed_Measurement':
                self._dockwidget_container[key].graphicsView_matrix.set_crosshair_pos((pulsed_data['pulsed_fw']['coord0_arr'][x_index], pulsed_data['pulsed_fw']['coord0_arr'][y_index]))
                self._dockwidget_container[key].graphicsView_matrix.set_crosshair_size((0,0))
                self._dockwidget_container[key].graphicsView_matrix.toggle_crosshair(state)
        self._mw.update_from_crosshair_pushButton.setEnabled(state)

    def update_from_crosshair(self):
        coords = self._dockwidget_container['d1'].graphicsView_matrix.crosshair_position
        pulsed_data = self._qafm_logic.get_pulsed_data()

        x_index = np.argmin(np.abs(pulsed_data['pulsed_fw']['coord0_arr']-coords[0]))
        y_index = np.argmin(np.abs(pulsed_data['pulsed_fw']['coord1_arr']-coords[1]))

        self._mw.x_coord_index_SpinBox.setValue(x_index)
        self._mw.y_coord_index_SpinBox.setValue(y_index)

        self.update_crosshair_pos(pulsed_data['pulsed_fw']['coord0_arr'][x_index], pulsed_data['pulsed_fw']['coord1_arr'][y_index])

    def update_crosshair_pos_from_spinbox(self):
        x_index = self._mw.x_coord_index_SpinBox.value()
        y_index = self._mw.y_coord_index_SpinBox.value()
        pulsed_data = self._qafm_logic.get_pulsed_data()
        self.update_crosshair_pos(pulsed_data['pulsed_fw']['coord0_arr'][x_index], pulsed_data['pulsed_fw']['coord1_arr'][y_index])

    def update_crosshair_pos(self, x, y):
        for key in self._dockwidget_container.keys():
            if key is not 'Pulsed_Measurement':
                self._dockwidget_container[key].graphicsView_matrix.set_crosshair_pos((x,y))

    def update_all_crosshair(self, obj_name):
        coords = self._dockwidget_container[obj_name].graphicsView_matrix.crosshair_position
        for key in self._dockwidget_container.keys():
            if key is not 'Pulsed_Measurement':
                self._dockwidget_container[key].graphicsView_matrix.set_crosshair_pos((coords[0],coords[1]))
    
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

    def adjust_pulsed_measurement_image(self):
        self._mw.view_pulsed_measurement_pushButton.setEnabled(False)
        pulsed_data = self._qafm_logic.get_pulsed_data()
        esr_data = self._qafm_logic.get_esr_data()
        qafm_data = self._qafm_logic.get_qafm_data()
        param_name = 'Pulsed_Measurement'
        dw = self.get_dockwidget(param_name)
        x_pos = self._mw.x_coord_index_SpinBox.value()
        y_pos = self._mw.y_coord_index_SpinBox.value()
        displayed_pulsed_measurement_data = self._mw.pulsed_data_comboBox.currentText()
        
        pulsed_measurement = False
        cw_odmr_measurement = False
        if qafm_data['Height(Dac)_fw']['params']['Parameters for'] == 'QAFM Tracking measurement':
            delta_0 = qafm_data['Height(Dac)_fw']['params']['delta_0']
            x_axis = np.array((-delta_0, delta_0))
            x_axis_name = 'Frequency'
            x_axis_units = 'Hz'
            pulsed_measurement = True

        elif qafm_data['Height(Dac)_fw']['params']['Parameters for'] == 'QAFM PODMR measurement':
            if qafm_data['Height(Dac)_fw']['params']['MW Tracking mode']:
                x_axis = pulsed_data['pulsed_fw']['var_list'][y_pos][x_pos]
            else:
                x_axis = pulsed_data['pulsed_fw']['coord2_arr']
            x_axis_name = 'Frequency'
            x_axis_units = 'Hz'
            pulsed_measurement = True

        elif qafm_data['Height(Dac)_fw']['params']['Parameters for'] == 'QAFM CW ODMR measurement':
            if qafm_data['Height(Dac)_fw']['params']['MW Tracking mode']:
                x_axis = esr_data['esr_fw']['var_list'][y_pos][x_pos]
            else:
                x_axis = esr_data['esr_fw']['coord2_arr']
            x_axis_name = 'Frequency'
            x_axis_units = 'Hz'
            cw_odmr_measurement = True

        elif qafm_data['Height(Dac)_fw']['params']['Parameters for'] == 'QAFM arb. sequence measurement':
            if qafm_data['Height(Dac)_fw']['params']['Arb. pulse measurement frequency sweep']:
                x_axis_name = 'Frequency'
                x_axis_units = 'Hz'
            else:
                x_axis_name = 'Tau'
                x_axis_units = 's'
            x_axis = pulsed_data['pulsed_fw']['coord2_arr']
            pulsed_measurement = True

        else:
            self.log.warning('Current scan does not include displayable data.')
            self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
            return
        
        if displayed_pulsed_measurement_data == 'Data':
            if cw_odmr_measurement:
                data = esr_data['esr_fw']['data'][y_pos][x_pos]
            elif pulsed_measurement:
                data = pulsed_data['pulsed_fw']['data'][y_pos][x_pos]
            else:
                self.log.warning('Current scan does not include displayable data.')
                self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
                return
                
        elif displayed_pulsed_measurement_data == 'Data Alternating':
            if pulsed_measurement:
                data = pulsed_data['pulsed_fw']['data_alternating'][y_pos][x_pos]
            else:
                self.log.warning('Current scan does not include displayable alternating data.')
                self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
                return
            
        elif displayed_pulsed_measurement_data == 'Data Delta':
            if pulsed_measurement:
                data = pulsed_data['pulsed_fw']['data_delta'][y_pos][x_pos]
            else:
                self.log.warning('Current scan does not include displayable delta data.')
                self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
                return
            
        elif displayed_pulsed_measurement_data == 'Tracking':
            if qafm_data['Height(Dac)_fw']['params']['Parameters for'] == 'QAFM arb. sequence measurement':
                if qafm_data['Height(Dac)_fw']['params']['Tracking']:
                    if qafm_data['Height(Dac)_fw']['params']['Tracking method'] == 'Two point':
                        delta_0 = qafm_data['Height(Dac)_fw']['params']['delta_0']
                        x_axis = np.array((-delta_0, delta_0))
                    else:
                        x_axis = pulsed_data['pulsed_fw']['var_list_tracking'][y_pos][x_pos]

                    data = pulsed_data['pulsed_fw']['data_tracking'][y_pos][x_pos]
                    x_axis_name = 'Frequency'
                    x_axis_units = 'Hz'
                else:
                    self.log.warning('Current scan does not track resonance frequency.')
                    self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
                    return
            else:
                self.log.warning('Current scan does not track resonance frequency.')
                self._mw.view_pulsed_measurement_pushButton.setEnabled(True)
                return

        dw.graphicsView.setLabel('bottom', x_axis_name, units=x_axis_units)
        self._plot_container[param_name].setData(x=x_axis, 
                                                y=data)

        self._plot_container[param_name].getViewBox().updateAutoRange()
        self._mw.view_pulsed_measurement_pushButton.setEnabled(True)

    def update_data_viewer_data_after_scanpoint(self):
        if self._mw.update_after_scan_point_checkBox.isChecked():
            self._update_data_viewer_data()
    
    def adjust_data_viewer_image(self):
        """ Fit the axis and range parameters to the currently started scan. """
        self._mw.view_data_pushButton.setEnabled(False)
        self._update_data_viewer_data()

        pulsed_data = self._qafm_logic.get_pulsed_data()

        for entry in self._image_container:
            image = self._image_container[entry]
            xy_viewbox = image.getViewBox()

            xMin = pulsed_data['pulsed_fw']['coord0_arr'][0]
            xMax = pulsed_data['pulsed_fw']['coord0_arr'][-1]
            yMin = pulsed_data['pulsed_fw']['coord1_arr'][0]
            yMax = pulsed_data['pulsed_fw']['coord1_arr'][-1]

            res_x = len(pulsed_data['pulsed_fw']['coord0_arr'])
            res_y = len(pulsed_data['pulsed_fw']['coord1_arr'])

            px_size = ((xMax - xMin) / (res_x - 1), (yMax - yMin) / (res_y - 1))
            image.set_image_extent(((xMin - px_size[0] / 2, xMax + px_size[0] / 2),
                                    (yMin - px_size[1] / 2, yMax + px_size[1] / 2)))
            xy_viewbox.updateAutoRange()
            xy_viewbox.updateViewRange()
        self._mw.view_data_pushButton.setEnabled(True)

    def _update_data_viewer_data(self):
        pulsed_data = self._qafm_logic.get_pulsed_data()

        datasets = {}

        for idx, name in enumerate(self._dataset_container):
            index = self._dataset_index_container[idx].value()
            if self._dataset_combobox_container[idx].currentText() == 'None':
                data = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
            elif self._dataset_combobox_container[idx].currentText() == 'Data':
                data = pulsed_data['pulsed_fw']['data'][:,:,index]
            elif self._dataset_combobox_container[idx].currentText() == 'Data Alternating':
                data = pulsed_data['pulsed_fw']['data_alternating'][:,:,index]
            elif self._dataset_combobox_container[idx].currentText() == 'Data Delta':
                data = pulsed_data['pulsed_fw']['data_delta'][:,:,index]
            datasets[name] = data.copy()
            self.data_summary[name] = data.copy()
            cb_range = self._get_scan_cb_range(name,data=data)
            self._image_container[name].setImage(image=data,
                                                           levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(name, data=data)
            self._image_container[name].getViewBox().updateAutoRange()

        name = 'Calculation'
        if self._mw.calculation_checkBox.isChecked():
            try:
                string = self._mw.calculation_lineEdit.text()
                for idx, dataset_name in enumerate(self._dataset_container):
                    if not dataset_name in string:
                        string = string + f'+{dataset_name}'
                        datasets[dataset_name] = 0
                function = self.string_to_function(string)
                data = function(datasets['d1'], datasets['d2'], datasets['d3'], datasets['d4']).astype('float64')
            except:
                data = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
                self.log.error('Expression for calculation is not valid.')
        else:
            data = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
        self.data_summary[name] = data
        cb_range = self._get_scan_cb_range(name,data=data)
        self._image_container[name].setImage(image=data,
                                                        levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(name, data=data)
        self._image_container[name].getViewBox().updateAutoRange()
        

        name = 'Fit'
        if self._mw.fit_checkBox.isChecked() and self._mw.fit_data_comboBox.currentText() != 'None' and self._mw.used_fit_comboBox.currentText() != 'No Fit' and self._mw.used_fit_parameter_comboBox.currentText() != 'None' and not self.fitting_busy and not self._mw.update_after_scan_point_checkBox.isChecked():
            if self._qafm_logic.check_thread_active():
                self.continue_code = False
                self.perform_fit = False
                self.show_popup()
                while not self.continue_code:
                    pass
            else:
                self.perform_fit = True
            
            if self.perform_fit and len(pulsed_data['pulsed_fw']['data'][0,0])>=2:
                self.log.info('Fit is performing.')
                self.fitting_busy = True
                self._mw.fitting_status_label.setText('Fitting')
                current_fit_method = self._mw.used_fit_comboBox.getCurrentFit()[0]
                current_fit_dataset = self._mw.fit_data_comboBox.currentText()
                if self._mw.fit_data_comboBox.currentText() == 'Data':
                    pulsed_data_for_fit = pulsed_data['pulsed_fw']['data']
                elif self._mw.fit_data_comboBox.currentText() == 'Data Alternating':
                    pulsed_data_for_fit = pulsed_data['pulsed_fw']['data_alternating']
                elif self._mw.fit_data_comboBox.currentText() == 'Data Delta':
                    pulsed_data_for_fit = pulsed_data['pulsed_fw']['data_delta']

                if current_fit_method != self.last_fit_method or current_fit_dataset != self.last_fit_dataset or self.new_scan:
                    self.new_scan = False
                    self.last_fit_method = current_fit_method
                    self.last_fit_dataset = current_fit_dataset
                    self.fit_dict = self.init_fit_dict(current_fit_method)
                    
                self.fc.set_current_fit(current_fit_method)
                var_list = pulsed_data['pulsed_fw']['coord2_arr']
                fit_params = self._fsd.getParameters(current_fit_method)
                for idy in range(len(pulsed_data['pulsed_fw']['coord1_arr'])):
                    for idx in range(len(pulsed_data['pulsed_fw']['coord0_arr'])):
                        data_for_fit = pulsed_data_for_fit[idy,idx]
                        if np.sum(data_for_fit) == 0 or self.fit_dict['analyzed'][idy,idx] == 1:
                            continue

                        x_fit, y_fit, result = self.fc.do_fit(var_list, data_for_fit)
                        for param in fit_params:
                            self.fit_dict[param][idy,idx] = result.params[param].value
                        self.fit_dict['analyzed'][idy,idx] = 1
                        self.result_str_dict = result.result_str_dict

                displayed_fit_param = self._mw.used_fit_parameter_comboBox.currentText()
                data = self.fit_dict[displayed_fit_param]
                self.data_summary[name] = data.copy()
                self.fitting_busy = False
                self._mw.fitting_status_label.setText('Idle')
                data_name = displayed_fit_param.capitalize()
                meas_units = self.result_str_dict[data_name]['unit']
            else:
                self.log.info('Fit was not performed.')
                data = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0]) #Fit function has to be added later on
                self.data_summary[name] = data.copy()
                data_name = 'Fit'
                meas_units = 'a.u.'
        else:
            data = np.zeros_like(pulsed_data['pulsed_fw']['data'][:,:,0])
            self.data_summary[name] = data.copy()
            data_name = 'Fit'
            meas_units = 'a.u.'
        
        self._dockwidget_container[name].graphicsView_cb.setLabel('left', data_name, units=meas_units)
        cb_range = self._get_scan_cb_range(name,data=data)
        self._image_container[name].setImage(image=data,
                                                        levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(name, data=data)
        self._image_container[name].getViewBox().updateAutoRange()

    def string_to_function(self, expression):
        def function(d1,d2,d3,d4):
            try:
                result = eval(expression,{'__builtins__': None}, {'d1': d1, 'd2': d2, 'd3': d3, 'd4': d4})
            except ZeroDivisionError:
                result = 0
            return result
        return np.frompyfunc(function, 4, 1)
    
    def show_popup(self):
        msg = QMessageBox()
        msg.setWindowTitle('Fitting while scanning')
        msg.setText('A scan is running right now. Do you want to performe data fitting?')
        msg.setInformativeText('Fitting slows down the system and can cause a crash of Qudi while done during a scan.')
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        msg.buttonClicked.connect(self.popup_button)

        msg.exec_()

    def popup_button(self, button):
        if 'Yes' in button.text():
            self.perform_fit = True
        else:
            self.perform_fit = False
        self.continue_code = True


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
    
    def _update_data_from_dockwidget(self, dockwidget_name):
        """ Update all displays of the dockwidget with data from logic.

        @param str dockwidget_name: name of the associated dockwidget.
        """

        data = self.data_summary[dockwidget_name]

        cb_range = self._get_scan_cb_range(dockwidget_name,data=data)

        # the name of the image object has to be the same as the dockwidget
        self._image_container[dockwidget_name].setImage(image=data, levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(dockwidget_name, data=data)
        # self._image_container[dockwidget_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
        self._image_container[dockwidget_name].getViewBox().updateAutoRange()

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