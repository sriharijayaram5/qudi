
import numpy as np
import pyqtgraph as pg
import os
import markdown
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy import uic
from pyqtgraph import PlotWidget

from core.module import Connector, StatusVar, ConfigOption
from qtwidgets.scan_plotwidget import ScanPlotWidget
from qtwidgets.scientific_spinbox import ScienDSpinBox
from qtwidgets.scan_plotwidget import ScanImageItem
from gui.guiutils import ColorBar
from gui.colordefs import ColorScaleInferno
from gui.colordefs import QudiPalettePale as palette

from gui.guibase import GUIBase




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
        ui_file = os.path.join(this_dir, 'ui_qafm_settings.ui')

        # Load it
        super(SettingsDialog, self).__init__()
        uic.loadUi(ui_file, self)

        buttons = self.buttonBox.buttons()
        self._ok_button = buttons[0]
        self._cancel_button = buttons[1]
        self._apply_button = buttons[2]

    def accept(self):
        """ Reimplement the accept method to get rid of closing upon enter press."""
        if self._ok_button.hasFocus():
            super(SettingsDialog, self).accept()


class AboutDialog(QtWidgets.QDialog):
    """ LabQ information, version, change notes, and hardware status 
    """
    _tabIndexLookup = None
    _refDocuments = None
    _hardwareStatus = None

    def __init__(self):
        """ Create About LabQ dialog 
        """
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_qafm_about.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)

        # index the tabs in the dialog, for easier lookup
        self._tabIndexLookup = { self.tabWidget.tabText(i).lower(): i for i in range(self.tabWidget.count())}

        # determine path of reference documents to build labels
        doc_path = os.path.abspath(os.path.join(this_dir,".."))  # this is a poor guess
        self._refDocuments = { refkey: os.path.join(doc_path,refname) 
                               if os.path.exists(os.path.join(doc_path,refname)) else None 
                               for refkey,refname in [('release_notes', 'RELEASENOTES.md'),
                                                      ('about', 'ABOUT.md'),
                                                      ('version', 'VERSION.md'),
                                                      ('license', 'LICENSE.md') ] 
                             } 

        # hardware status is updated just-in-time         


class QuantitativeMeasurementWindow(QtWidgets.QWidget):
    """ Create the SettingsDialog window, based on the corresponding *.ui file."""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_quantitative_mode.ui')

        # Load it
        super(QuantitativeMeasurementWindow, self).__init__()
        uic.loadUi(ui_file, self)


class PeriodicOptimizerRequest(QtWidgets.QDialog):
    """ Create a periodic request Dialog Window. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_optimizer_request.ui')

        # Load it
        super(PeriodicOptimizerRequest, self).__init__()
        uic.loadUi(ui_file, self)   


class CustomCheckBox(QtWidgets.QCheckBox):

    # with the current state and the name of the box
    valueChanged_custom = QtCore.Signal(bool, str)

    def __init__(self, parent=None):

        super(CustomCheckBox, self).__init__(parent)
        self.stateChanged.connect(self.emit_value_name)

    @QtCore.Slot(int)
    def emit_value_name(self, state):
        self.valueChanged_custom.emit(bool(state), self.objectName())


class ProteusQMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_qafm_gui.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()

class ProteusQGUI(GUIBase):
    """ GUI to control the ProteusQ. """
    
    _modclass = 'ProteusQGUI'
    _modtype = 'gui'

    _LabQversion = '1.4'
    __version__ = '0.2.4'

    ## declare connectors
    qafmlogic = Connector(interface='AFMConfocalLogic') # interface='AFMConfocalLogic'


    sigGotoObjpos = QtCore.Signal(dict)
    sigGotoAFMpos = QtCore.Signal(dict)
    sigColorBarChanged = QtCore.Signal(str)  # emit a dockwidget object.


    image_x_padding = ConfigOption('image_x_padding', 0.02)
    image_y_padding = ConfigOption('image_y_padding', 0.02)
    image_z_padding = ConfigOption('image_z_padding', 0.02)
    saved_default_view = ConfigOption('saved_default_view', b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01\x04\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x03\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x01\x00\x00\x00D\x00\x00\x01\xd3\x00\x00\x01\xd3\x00\x07\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00p\x00t\x00i\x00_\x00x\x00y\x01\x00\x00\x02\x17\x00\x00\x01\x10\x00\x00\x01\x10\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00p\x00t\x00i\x00_\x00z\x01\x00\x00\x03+\x00\x00\x00\xba\x00\x00\x00f\x00\xff\xff\xff\x00\x00\x00\x01\x00\x00\x06x\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x02\xfb\x00\x00\x00\x1e\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00i\x00s\x00o\x00b\x00\x00\x00\x00D\x00\x00\x00\xa7\x00\x00\x00y\x00\xff\xff\xff\xfc\x00\x00\x00D\x00\x00\x03\xa1\x00\x00\x02\xc8\x00\xff\xff\xff\xfc\x01\x00\x00\x00\x03\xfc\x00\x00\x01\x08\x00\x00\x02\xb5\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0e\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00y\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00x\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00_\x00y\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfc\x00\x00\x03\xc1\x00\x00\x02\xbf\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x00\x01\x00\x00\x00\x0b\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00*\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x002\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00M\x00a\x00g\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00&\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00P\x00h\x00a\x00s\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00$\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00F\x00r\x00e\x00q\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00N\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00 \x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00L\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00"\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00E\x00x\x001\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00a\x00f\x00m\x01\x00\x00\x06\x84\x00\x00\x00\xfc\x00\x00\x00\xfc\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\x03\xa1\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x04\x00\x00\x00"\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00p\x00t\x00i\x00m\x00i\x00z\x00e\x00r\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x002\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x00h\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00t\x00o\x00p\x01\x00\x00\x01G\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00,\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00a\x00m\x00p\x00l\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x01\x82\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00')

    _dock_state = 'double'  # possible: single and double

    _image_container = {}
    _cb_container = {}
    _checkbox_container = {}
    _plot_container = {}
    _dockwidget_container = {}

    # status variables (will be saved at shutdown)
    _save_display_view = StatusVar('save_display_view', default=None) # It is a bytearray
    _obj_range_x_min = StatusVar('obj_range_x_min', default=0)  # in m
    _obj_range_x_max = StatusVar('obj_range_x_max', default=30e-6)  # in m
    _obj_range_x_num = StatusVar('obj_range_x_num', default=40)
    _obj_range_y_min = StatusVar('obj_range_y_min', default=0)  # in m
    _obj_range_y_max = StatusVar('obj_range_y_max', default=30e-6)  # in m
    _obj_range_y_num = StatusVar('obj_range_y_num', default=40)
    _obj_range_z_min = StatusVar('obj_range_z_min', default=0)  # in m
    _obj_range_z_max = StatusVar('obj_range_z_max', default=10e-6)  # in m
    _obj_range_z_num = StatusVar('obj_range_z_num', default=40)

    _save_obj_xy = StatusVar('save_obj_xy', default=False)
    _save_obj_xz = StatusVar('save_obj_xz', default=False)
    _save_obj_yz = StatusVar('save_obj_yz', default=False)
    _obj_save_text = StatusVar('obj_save_text', default='')

    _qafm_save_text = StatusVar('qafm_save_text', default='')
    _probename_text = StatusVar('probename_text', default='')
    _samplename_text = StatusVar('samplename_text', default='')
    _daily_folder = StatusVar('daily_folder', default=True)

    _afm_range_x_min = StatusVar('afm_range_x_min', default=0)
    _afm_range_x_max = StatusVar('afm_range_x_max', default=100e-6)
    _afm_range_x_num = StatusVar('afm_range_x_num', default=100)

    _afm_range_y_min = StatusVar('afm_range_y_min', default=0)
    _afm_range_y_max = StatusVar('afm_range_y_max', default=100e-6)
    _afm_range_y_num = StatusVar('afm_range_y_num', default=100)

    # save here the period Optimizer value.
    _periodic_opti_time = StatusVar('periodic_opti_time', default=100)

    # here are the checked meas params stored, a list of strings
    _stat_var_meas_params = StatusVar('stat_var_meas_params', default=[])

    _current_cs = ColorScaleInferno()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialization of the GUI. """

        self._qafm_logic = self.qafmlogic()

        self.initMainUI()      # initialize the main GUI
        #self.default_view()

        self._qafm_logic.sigQAFMScanInitialized.connect(self.adjust_qafm_image)
        self._qafm_logic.sigQAFMLineScanFinished.connect(self._update_qafm_data)
        self._qafm_logic.sigQAFMScanFinished.connect(self.enable_scan_actions)
        self._qafm_logic.sigQAFMScanFinished.connect(self.autosave_qafm_measurement)
        self._qafm_logic.sigNewAFMPos.connect(self.update_afm_pos)

        self._qafm_logic.sigObjScanInitialized.connect(self.adjust_obj_image)
        self._qafm_logic.sigObjLineScanFinished.connect(self._update_obj_data)
        self._qafm_logic.sigObjScanFinished.connect(self.enable_scan_actions)
        self._qafm_logic.sigNewObjPos.connect(self.update_obj_pos)

        self._mw.actionStart_QAFM_Scan.triggered.connect(self.start_qafm_scan_clicked)
        self._mw.actionStop_Scan.triggered.connect(self.stop_any_scanning)
        self._mw.actionStart_Obj_XY_scan.triggered.connect(self.start_obj_scan_xy_scan_clicked )
        self._mw.actionStart_Obj_XZ_scan.triggered.connect(self.start_obj_scan_xz_scan_clicked )
        self._mw.actionStart_Obj_YZ_scan.triggered.connect(self.start_obj_scan_yz_scan_clicked )


        self._qafm_logic.sigOptimizeScanInitialized.connect(self.adjust_optimizer_image)
        self._qafm_logic.sigOptimizeLineScanFinished.connect(self._update_opti_data)
        self._qafm_logic.sigOptimizeScanFinished.connect(self.enable_optimizer_action)
        self._qafm_logic.sigOptimizeScanFinished.connect(self.update_target_pos)

        self._mw.actionOptimize_Pos.triggered.connect(self.start_optimize_clicked)

        self._qafm_logic.sigObjTargetReached.connect(self.enable_scan_actions)
        self._qafm_logic.sigAFMTargetReached.connect(self.enable_scan_actions)

        self._mw.actionSplit_Display.triggered.connect(self.split_view)
        self._mw.actionCombine_Display.triggered.connect(self.combine_view)
        self._mw.actionDefault_Display.triggered.connect(self.default_view)
        self._mw.actionSave_Display.triggered.connect(self.save_view)
        self._mw.actionLoad_Display.triggered.connect(self.load_view)

        self._mw.actionGo_To_AFM_pos.triggered.connect(self.goto_afm_pos_clicked)
        self._mw.actionGo_To_Obj_pos.triggered.connect(self.goto_obj_pos_clicked)
        

        self.sigGotoObjpos.connect(self._qafm_logic.set_obj_pos)
        self.sigGotoAFMpos.connect(self._qafm_logic.set_afm_pos)
        self.sigColorBarChanged.connect(self._update_data_from_dockwidget)

        self._qafm_logic.sigQAFMDataSaved.connect(self.enable_qafm_save_button)
        self._mw.actionSaveDataQAFM.triggered.connect(self.save_qafm_data_clicked)

        self._qafm_logic.sigObjDataSaved.connect(self.enable_obj_save_button)
        self._mw.actionSaveObjData.triggered.connect(self.save_obj_data_clicked)

        self._qafm_logic.sigOptiDataSaved.connect(self.enable_opti_save_button)
        self._mw.actionSaveOptiData.triggered.connect(self.save_opti_data_clicked)

        # update the display:
        self.update_obj_pos(self._qafm_logic.get_obj_pos())
        self.update_afm_pos(self._qafm_logic.get_afm_pos())

        if 'obj_xy' in self._image_container:
            self._image_container['obj_xy'].sigMouseClicked.connect(self.update_targetpos_xy)


        self._mw.action_curr_pos_to_target.triggered.connect(self.set_current_pos_to_target)
        self._mw.action_center_pos_to_target.triggered.connect(self.set_center_pos_to_target)

        self.initQuantiUI()
        self._mw.action_Quantitative_Measure.triggered.connect(self.openQuantiMeas)

        # connect Quantitative signals 
        self._qm.Start_QM_PushButton.clicked.connect(self.start_quantitative_measure_clicked)
        self._qm.Continue_QM_PushButton.clicked.connect(self.continue_quantitative_measure_clicked)
        self._qm.Stop_QM_PushButton.clicked.connect(self.stop_quantitative_measure_clicked)

        self._qm.Start_QM_PushButton.clicked.connect(self.disable_scan_actions_quanti)
        self._qm.Continue_QM_PushButton.clicked.connect(self.disable_scan_actions_quanti)
        self._qafm_logic.sigQuantiScanFinished.connect(self.enable_scan_actions_quanti)
        self._qafm_logic.sigQuantiScanFinished.connect(self.autosave_quantitative_measurement)


        # initialize the settings stuff
        self.initSettingsUI()

        # Initialize iso b parameter
        self._mw.use_single_isob_RadioButton.toggled.connect(self._set_iso_b_single_mode)
        self._mw.use_dual_isob_RadioButton.toggled.connect(self._enable_dual_iso_b_plots)
        self._mw.freq1_isob_freq_DSpinBox.valueChanged.connect(self._set_freq1_iso_b_freq)
        self._mw.freq2_isob_freq_DSpinBox.valueChanged.connect(self._set_freq2_iso_b_freq)
        self._mw.isob_gain_DSpinBox.valueChanged.connect(self._set_iso_b_gain)

        self._mw.freq1_isob_freq_DSpinBox.setMinimalStep = 10e3
        self._mw.freq2_isob_freq_DSpinBox.setMinimalStep = 10e3
        self._mw.isob_gain_DSpinBox.setMinimalStep = 0.01

        self._qafm_logic.sigIsoBParamsUpdated.connect(self.update_iso_b_param)
        self.update_iso_b_param()

        # Set everything up for the optimizer request 
        self.initOptimizerRequestUI()

        self.initAboutUI()     # provide version number and hardware status
        self.retrieve_status_var()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        self.store_status_var()
        self._mw.close()
        self._qm.close()
        self._sd.close()
        self._or.close()


    def show(self):
        """Make window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()


    def initQuantiUI(self):
        self._qm = QuantitativeMeasurementWindow()


    def openQuantiMeas(self):
        self._qm.show()
        self._qm.raise_()


    def initMainUI(self):
        """ Definition, configuration and initialisation of the confocal GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values.
        """
        self._mw = ProteusQMainWindow()

        ###################################################################
        #               Configuring the dock widgets                      #
        ###################################################################
        # All our gui elements are dockable, and so there should be no "central" widget.
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)
        self._create_dockwidgets()
        self._create_meas_params()
        self._set_aspect_ratio_images()
        self.split_view()

        self.adjust_qafm_image()
        self.adjust_all_obj_images()
        self.adjust_optimizer_image('opti_xy')
        self._update_opti_data('opti_z')

        self._initialize_inputs()
        self._arrange_iso_dockwidget()


    def initSettingsUI(self):
        """ Initialize and set up the Settings Dialog. """

        self._sd = SettingsDialog()

        self._mw.action_open_settings.triggered.connect(self.show_settings_window)

        self._sd.accepted.connect(self.update_qafm_settings)
        self._sd.rejected.connect(self.keep_former_qafm_settings)
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_qafm_settings)

        self._sd.iso_b_operation_CheckBox.stateChanged.connect(self._mw.dockWidget_isob.setVisible)
        self._sd.iso_b_operation_CheckBox.stateChanged.connect(self._mw.dockWidget_isob.setEnabled)
        self._sd.iso_b_operation_CheckBox.stateChanged.connect(self._sd.n_iso_b_pulse_margin_Label.setEnabled)
        self._sd.iso_b_operation_CheckBox.stateChanged.connect(self._sd.n_iso_b_pulse_margin_DoubleSpinBox.setEnabled)

        # trigger update of dual iso-b plot visibility 
        self._sd.iso_b_operation_CheckBox.stateChanged.connect(self._enable_dual_iso_b_plots) 

        # toggle twice to initiate a state change and come back to the initial one.
        self._sd.iso_b_operation_CheckBox.toggle()
        self._sd.iso_b_operation_CheckBox.toggle()

        # write the configuration to the settings window of the GUI.
        self.keep_former_qafm_settings()

        # react on setting changes by the logic
        self._qafm_logic.sigSettingsUpdated.connect(self.keep_former_qafm_settings)

    
    def initAboutUI(self):
        """ Initialize the LabQ About dialog box """
        self._ab = AboutDialog()

        self._ab.software_version_Label.setText(f"LabQ version {self._LabQversion}")

        self._mw.actionAbout.triggered.connect(self.show_about_tab)
        self._mw.actionVersion.triggered.connect(self.show_version_tab)
        self._mw.actionHardwareStatus.triggered.connect(self.show_hardware_status_tab)


    def update_about_messages(self):
        """ update messages to be displayed in AboutDialog
            - this updates the 'AboutDialog' messages based upon
              the Markdown files found in the main ProteusQ directory
        """

        # If no Markdown file is found, the default .ui definition is used
        # Main 'About' text. 
        doc_path = self._ab._refDocuments.get('about')
        if doc_path is not None:
            with open(doc_path,'r') as f:
                message = markdown.markdown(f.read()) # renders to HTML
            self._ab.about_Label.setText(message)

        # 'Version' text
        doc_path = self._ab._refDocuments.get('version')
        if doc_path is not None:
            with open(doc_path,'r') as f:
                message = markdown.markdown(f.read()) # renders to HTML
            self._ab.version_Label.setText(message)

        # 'Release Notes' text
        doc_path = self._ab._refDocuments.get('release_notes')
        if doc_path is not None:
            with open(doc_path,'r') as f:
                message = markdown.markdown(f.read()) # renders to HTML
            self._ab.release_notes_Label.setText(message)
    

    def update_hardware_status_message(self):
        """ Retrieves information from qafm_logic, regarding the hardware conditions
            In the case this is called with dummy instances, the null report is returned
        """
        try: 
            # MicrowaveQ hardware
            query = ['unlocked_features','fpga_version',]
            status_dict = self._qafm_logic.get_hardware_status(query)
            status = "#Hardware Status:\n\n"
            status += "## MicrowaveQ  \n"
            for refname, refres in status_dict.items():
                status += f"### {refname}  \n"
                if isinstance(refres,dict):
                    status += "\n".join([f" - {k} : {v}" for k,v in refres.items()])
                else:
                    status += str(refres)
                status += "\n\n"      
            status += "---  \n"

            # SPM hardware
            query = ['spm_library_version','spm_server_version','spm_client_version']
            status_dict = self._qafm_logic.get_hardware_status(query)
            status += "## SPM  \n"
            for refname, refres in status_dict.items():
                status += f"### {refname}  \n"
                if isinstance(refres,dict):
                    status += "\n".join([f" - {k} : {v}" for k,v in refres.items()])
                else:
                    status += str(refres)
                status += "\n\n"      
            status += "---  \n"
            status_html = markdown.markdown(status) 

        except:
            status_html = markdown.markdown("##Hardware Status:\n- Dummy hardware in use")
            
        self._ab.hardware_status_Label.setText(status_html)


    def show_about_tab(self):
        """ display 'About LabQ', emphasis on about tab"""

        i = self._ab._tabIndexLookup.get("about", None)
        if i is not None:
            self._ab.tabWidget.setCurrentIndex(i)

        self.show_about_window()


    def show_version_tab(self):
        """ display 'About LabQ', emphasis on version tab"""

        i = self._ab._tabIndexLookup.get("version", None)
        if i is not None:
            self._ab.tabWidget.setCurrentIndex(i)

        self.show_about_window()

    def show_hardware_status_tab(self):
        """ display 'About LabQ', emphasis on hardware status tab"""

        i = self._ab._tabIndexLookup.get("hardware status", None)
        if i is not None:
            self._ab.tabWidget.setCurrentIndex(i)

        self.show_about_window()
    
    
    def show_about_window(self):
        """ display 'About LabQ' dialog box """
        # Load the 'About text'
        self.update_about_messages()
        self.update_hardware_status_message()

        self._ab.show()
        self._ab.raise_()

    # ==========================================================================
    #               Start Methods for the Optimizer Request

    def initOptimizerRequestUI(self):
        """ Initiate the Optimizer request Dialog."""
        self._or = PeriodicOptimizerRequest()

        self._mw.action_open_optimizer_request.triggered.connect(self.show_optimizer_request_window)

        self._or.time_optimizer_request_SpinBox.valueChanged.connect(self.update_max_optimizer_request)

        self._request_timer = QtCore.QTimer()
        self._request_timer.timeout.connect(self.update_progress_bar)
        self._request_timer.setSingleShot(False)

        self._request_timer_interval = 1 # in s, will essentially fire every second


        self._or.start_optimizer_request_PushButton.pressed.connect(self.start_optimize_request_pressed)
        self._or.stop_optimizer_request_PushButton.pressed.connect(self.stop_optimize_request_pressed)

        self._or.time_optimizer_request_SpinBox.setValue(self._periodic_opti_time)

    def show_optimizer_request_window(self):
        """ Show and open the settings window. """
        self._or.show()
        self._or.raise_()

    def update_max_optimizer_request(self, val):
        """ Update the  Progress bar. 
        
        @params float val: Maximal value of progress Bar in seconds. Make sure
                           not to pass zero or a negative number. 
        """

        self._or.progress_Bar.setMaximum(val)
        self._or.progress_Bar.setValue(val)
        self._periodic_opti_time = val

    def start_timer(self):
        """ Start the timer, if timer is running, it will be restarted. """
        self._request_timer.start(self._request_timer_interval * 1000) # in ms

    def stop_timer(self):
        """ Stop the timer. """
        self._request_timer.stop()

    def update_progress_bar(self):
        """ This function will be called periodically. """
        
        curr_val = self._or.progress_Bar.value()

        # make it just a bit larger than 0, assume _request_timer_interval will 
        # never be smaller than this value.
        if curr_val - self._request_timer_interval < 0.1:

            self.perform_period_action()
            self._or.progress_Bar.setValue(self._or.progress_Bar.maximum())
        else:
            self._or.progress_Bar.setValue(curr_val - self._request_timer_interval)

    def start_optimize_request_pressed(self):
        """ Event when start button is pressed. """
        self._or.progress_Bar.setValue(self._or.progress_Bar.maximum())

        self.perform_period_action()
        self._or.time_optimizer_request_SpinBox.setEnabled(False)
        self.start_timer()

    def stop_optimize_request_pressed(self):
        """ Event when stop button is pressed. """
        self.stop_timer()
        self._or.time_optimizer_request_SpinBox.setEnabled(True)


    def perform_period_action(self):
        """ Just a wrapper method which is called to perform periodic action."""
        self.start_optimize_clicked()
        #self.log.info('Boom!')

    #               End Methods for the Optimizer Request
    # ==========================================================================

    def _set_iso_b_single_mode(self, single_mode):
        #print('val changed:', single_mode)
        self._qafm_logic.set_iso_b_params(single_mode=single_mode)

    def _set_freq1_iso_b_freq(self, freq1):
        #print('val changed:', freq1)
        self._qafm_logic.set_iso_b_params(freq1=freq1)

    def _set_freq2_iso_b_freq(self, freq2):
        #print('val changed:', freq2)
        self._qafm_logic.set_iso_b_params(freq2=freq2)

    def _set_iso_b_gain(self, gain):
        #print('val changed:', gain)
        self._qafm_logic.set_iso_b_params(gain=gain)  

    def _enable_dual_iso_b_plots(self,enable):
        enable = enable and not self._qafm_logic.get_iso_b_mode() # iso_b_mode=single
        
        for obj_name in ['counts2', 'counts_diff']:
            for direc in ['bw', 'fw']:
                    ob = getattr(self._mw,f'dockWidget_{obj_name}_{direc}')
                    ob.setVisible(enable)


    def update_iso_b_param(self):
        """ Update single iso b parameter from the logic """

        self._mw.use_single_isob_RadioButton.blockSignals(True) 
        self._mw.use_dual_isob_RadioButton.blockSignals(True) 
        self._mw.freq1_isob_freq_DSpinBox.blockSignals(True)
        self._mw.freq2_isob_freq_DSpinBox.blockSignals(True)
        self._mw.isob_gain_DSpinBox.blockSignals(True)

        iso_b_operation, single_mode, freq1, freq2, gain = \
            self._qafm_logic.get_iso_b_params()

        if single_mode is not None:
            if single_mode == True:
                self._mw.use_single_isob_RadioButton.setChecked(True)
                self._mw.freq2_isob_freq_DSpinBox.setEnabled(False)
            else:
                self._mw.use_dual_isob_RadioButton.setChecked(True)
                self._mw.freq2_isob_freq_DSpinBox.setEnabled(True)

        if freq1 is not None:
            self._mw.freq1_isob_freq_DSpinBox.setValue(freq1)

        if freq2 is not None:
            self._mw.freq2_isob_freq_DSpinBox.setValue(freq2)

        if gain is not None:
            self._mw.isob_gain_DSpinBox.setValue(gain)
        
        self._enable_dual_iso_b_plots(iso_b_operation)

        self._mw.use_single_isob_RadioButton.blockSignals(False) 
        self._mw.use_dual_isob_RadioButton.blockSignals(False) 
        self._mw.freq1_isob_freq_DSpinBox.blockSignals(False)
        self._mw.freq2_isob_freq_DSpinBox.blockSignals(False)
        self._mw.isob_gain_DSpinBox.blockSignals(False)


    def update_qafm_settings(self):
        
        # create a settings dict
        sd = {}

        # general settings
        sd['idle_move_target_sample'] = self._sd.idle_move_target_sample_DoubleSpinBox.value()
        sd['idle_move_target_obj'] = self._sd.idle_move_target_obj_DoubleSpinBox.value()
        # scanning settings
        sd['idle_move_scan_sample'] = self._sd.idle_move_scan_sample_DoubleSpinBox.value()
        sd['idle_move_scan_obj'] = self._sd.idle_move_scan_obj_DoubleSpinBox.value()
        sd['int_time_sample_scan'] = self._sd.int_time_sample_scan_DoubleSpinBox.value()
        sd['int_time_obj_scan'] = self._sd.int_time_obj_scan_DoubleSpinBox.value()
        sd['n_iso_b_pulse_margin'] = self._sd.n_iso_b_pulse_margin_DoubleSpinBox.value()
        # save settings
        sd['root_folder_name'] = self._sd.rootfolder_name_LineEdit.text()
        sd['create_summary_pic'] = self._sd.create_summary_pic_CheckBox.isChecked()
        sd['auto_save_quanti'] = self._sd.auto_save_quanti_CheckBox.isChecked()
        sd['auto_save_qafm'] = self._sd.auto_save_qafm_CheckBox.isChecked()
        sd['save_to_gwyddion'] = self._sd.save_to_gwyddion_CheckBox.isChecked()

        # optimizer settings
        sd['optimizer_x_range'] = self._sd.optimizer_x_range_DoubleSpinBox.value()
        sd['optimizer_x_res'] = self._sd.optimizer_x_res_SpinBox.value()
        sd['optimizer_y_range'] = self._sd.optimizer_y_range_DoubleSpinBox.value()
        sd['optimizer_y_res'] = self._sd.optimizer_y_res_SpinBox.value()
        sd['optimizer_z_range'] = self._sd.optimizer_z_range_DoubleSpinBox.value()
        sd['optimizer_z_res'] = self._sd.optimizer_z_res_SpinBox.value()
        sd['optimizer_int_time'] = self._sd.optimizer_int_time_DoubleSpinBox.value()
        sd['optimizer_period'] = self._sd.optimizer_period_DoubleSpinBox.value()
        sd['iso_b_operation'] = self._sd.iso_b_operation_CheckBox.isChecked()
        self._qafm_logic.set_qafm_settings(sd)


    def keep_former_qafm_settings(self):
        """ Keep the old settings and restores them in the gui from logic. """
        
        sd = self._qafm_logic.get_qafm_settings()

        # general settings
        self._sd.idle_move_target_sample_DoubleSpinBox.setValue(sd['idle_move_target_sample'])
        self._sd.idle_move_target_obj_DoubleSpinBox.setValue(sd['idle_move_target_obj'])
        # scanning settings
        self._sd.idle_move_scan_sample_DoubleSpinBox.setValue(sd['idle_move_scan_sample'])
        self._sd.idle_move_scan_obj_DoubleSpinBox.setValue(sd['idle_move_scan_obj'])
        self._sd.int_time_sample_scan_DoubleSpinBox.setValue(sd['int_time_sample_scan'])
        self._sd.int_time_obj_scan_DoubleSpinBox.setValue(sd['int_time_obj_scan'])
        # save settings
        self._sd.rootfolder_name_LineEdit.setText(sd['root_folder_name'])
        self._sd.create_summary_pic_CheckBox.setChecked(sd['create_summary_pic'])
        self._sd.auto_save_quanti_CheckBox.setChecked(sd['auto_save_quanti'])
        self._sd.auto_save_qafm_CheckBox.setChecked(sd['auto_save_qafm'])
        self._sd.save_to_gwyddion_CheckBox.setChecked(sd['save_to_gwyddion'])
        # optimizer settings
        self._sd.optimizer_x_range_DoubleSpinBox.setValue(sd['optimizer_x_range'])
        self._sd.optimizer_x_res_SpinBox.setValue(sd['optimizer_x_res'])
        self._sd.optimizer_y_range_DoubleSpinBox.setValue(sd['optimizer_y_range'])
        self._sd.optimizer_y_res_SpinBox.setValue(sd['optimizer_y_res'])
        self._sd.optimizer_z_range_DoubleSpinBox.setValue(sd['optimizer_z_range'])
        self._sd.optimizer_z_res_SpinBox.setValue(sd['optimizer_z_res'])
        self._sd.optimizer_int_time_DoubleSpinBox.setValue(sd['optimizer_int_time'])
        self._sd.optimizer_period_DoubleSpinBox.setValue(sd['optimizer_period'])    

        self._sd.iso_b_operation_CheckBox.setChecked(sd['iso_b_operation'])
        self._sd.n_iso_b_pulse_margin_DoubleSpinBox.setValue(sd['n_iso_b_pulse_margin'])


    def show_settings_window(self):
        """ Show and open the settings window. """
        self._sd.show()
        self._sd.raise_()


    def retrieve_status_var(self):
        """ Obtain variables from file. """

        self._mw.obj_x_min_DSpinBox.setValue(self._obj_range_x_min)
        self._mw.obj_x_max_DSpinBox.setValue(self._obj_range_x_max)
        self._mw.obj_x_num_SpinBox.setValue(self._obj_range_x_num)

        self._mw.obj_y_min_DSpinBox.setValue(self._obj_range_y_min)
        self._mw.obj_y_max_DSpinBox.setValue(self._obj_range_y_max)
        self._mw.obj_y_num_SpinBox.setValue(self._obj_range_y_num)

        self._mw.obj_z_min_DSpinBox.setValue(self._obj_range_z_min)
        self._mw.obj_z_max_DSpinBox.setValue(self._obj_range_z_max)
        self._mw.obj_z_num_SpinBox.setValue(self._obj_range_z_num)

        self._mw.save_obj_xy_CheckBox.setChecked(self._save_obj_xy)
        self._mw.save_obj_xz_CheckBox.setChecked(self._save_obj_xz)
        self._mw.save_obj_yz_CheckBox.setChecked(self._save_obj_yz)
        self._mw.obj_save_LineEdit.setText(self._obj_save_text)

        self._mw.qafm_save_LineEdit.setText(self._qafm_save_text)
        self._mw.probename_LineEdit.setText(self._probename_text)
        self._mw.samplename_LineEdit.setText(self._samplename_text)
        self._mw.daily_folder_CheckBox.setChecked(self._daily_folder)

        self._mw.afm_x_min_DSpinBox.setValue(self._afm_range_x_min)
        self._mw.afm_x_max_DSpinBox.setValue(self._afm_range_x_max)
        self._mw.afm_x_num_SpinBox.setValue(self._afm_range_x_num)

        self._mw.afm_y_min_DSpinBox.setValue(self._afm_range_y_min)
        self._mw.afm_y_max_DSpinBox.setValue(self._afm_range_y_max)
        self._mw.afm_y_num_SpinBox.setValue(self._afm_range_y_num)

        for entry in self._stat_var_meas_params:
            if entry in self._checkbox_container:
                self._checkbox_container[entry].setChecked(True)

        self._or.time_optimizer_request_SpinBox.setValue(self._periodic_opti_time)


    def store_status_var(self):
        """ Store all those variables to file. """

        self._obj_range_x_min = self._mw.obj_x_min_DSpinBox.value()
        self._obj_range_x_max = self._mw.obj_x_max_DSpinBox.value()
        self._obj_range_x_num = self._mw.obj_x_num_SpinBox.value()
        self._obj_range_y_min = self._mw.obj_y_min_DSpinBox.value()
        self._obj_range_y_max = self._mw.obj_y_max_DSpinBox.value()
        self._obj_range_y_num = self._mw.obj_y_num_SpinBox.value()
        self._obj_range_z_min = self._mw.obj_z_min_DSpinBox.value()
        self._obj_range_z_max = self._mw.obj_z_max_DSpinBox.value()
        self._obj_range_z_num = self._mw.obj_z_num_SpinBox.value()

        self._save_obj_xy = self._mw.save_obj_xy_CheckBox.isChecked()
        self._save_obj_xz = self._mw.save_obj_xz_CheckBox.isChecked()
        self._save_obj_yz = self._mw.save_obj_yz_CheckBox.isChecked()
        self._obj_save_text = self._mw.obj_save_LineEdit.text()

        self._qafm_save_text = self._mw.qafm_save_LineEdit.text()
        self._probename_text = self._mw.probename_LineEdit.text()
        self._samplename_text = self._mw.samplename_LineEdit.text()
        self._daily_folder = self._mw.daily_folder_CheckBox.isChecked()

        self._afm_range_x_min = self._mw.afm_x_min_DSpinBox.value()
        self._afm_range_x_max = self._mw.afm_x_max_DSpinBox.value()
        self._afm_range_x_num = self._mw.afm_x_num_SpinBox.value()

        self._afm_range_y_min = self._mw.afm_y_min_DSpinBox.value()
        self._afm_range_y_max = self._mw.afm_y_max_DSpinBox.value()
        self._afm_range_y_num = self._mw.afm_y_num_SpinBox.value()

        # store the selection of the measurement params
        self._stat_var_meas_params = []
        for entry in self._checkbox_container:
            if self._checkbox_container[entry].isChecked():
                self._stat_var_meas_params.append(entry)

        self._periodic_opti_time = self._or.time_optimizer_request_SpinBox.value()


    def get_all_data_matrices(self):
        """ more of a helper method to get all the data matrices. """

        data_dict = {}
        data_dict.update(self._qafm_logic.get_qafm_data())
        data_dict.update(self._qafm_logic.get_obj_data())
        data_dict.update(self._qafm_logic.get_opti_data())

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

        self._plot_container[name] = pg.PlotDataItem(x=x_axis, y=y_axis,
                                                     pen=pg.mkPen(palette.c1, 
                                                                  style=QtCore.Qt.DotLine),
                                                     symbol='o',
                                                     symbolPen=palette.c1,
                                                     symbolBrush=palette.c1,
                                                     symbolSize=7
                                                    )
        return self._plot_container[name]


    def _set_aspect_ratio_images(self):
        for entry in self._image_container:
            self._image_container[entry].getViewBox().setAspectLocked(lock=True, ratio=1.0)

    def _initialize_inputs(self):

        # set constraints
        self._mw.obj_x_min_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_x_min_DSpinBox.setSuffix('m')
        self._mw.obj_x_min_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_x_max_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_x_max_DSpinBox.setSuffix('m')
        self._mw.obj_x_max_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_x_num_SpinBox.setRange(2, 10000)

        self._mw.obj_y_min_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_y_min_DSpinBox.setSuffix('m')
        self._mw.obj_y_min_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_y_max_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_y_max_DSpinBox.setSuffix('m')
        self._mw.obj_y_max_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_y_num_SpinBox.setRange(2, 10000)

        self._mw.obj_z_min_DSpinBox.setRange(0.0, 10e-6)
        self._mw.obj_z_min_DSpinBox.setSuffix('m')
        self._mw.obj_z_min_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_z_max_DSpinBox.setRange(0.0, 10e-6)
        self._mw.obj_z_max_DSpinBox.setSuffix('m')
        self._mw.obj_z_max_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_z_num_SpinBox.setRange(2, 10000)

        self._mw.obj_target_x_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_target_x_DSpinBox.setSuffix('m')
        self._mw.obj_target_x_DSpinBox.setMinimalStep(0.1e-6)
        self._mw.obj_target_x_DSpinBox.setValue(15e-6)

        self._mw.obj_target_y_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_target_y_DSpinBox.setSuffix('m')
        self._mw.obj_target_y_DSpinBox.setMinimalStep(0.1e-6)
        self._mw.obj_target_y_DSpinBox.setValue(15e-6)

        self._mw.obj_target_z_DSpinBox.setRange(0.0, 10e-6)
        self._mw.obj_target_z_DSpinBox.setSuffix('m')
        self._mw.obj_target_z_DSpinBox.setMinimalStep(0.1e-6)
        self._mw.obj_target_z_DSpinBox.setValue(5e-6)

        self._mw.afm_x_min_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_x_min_DSpinBox.setSuffix('m')
        self._mw.afm_x_min_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.afm_x_max_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_x_max_DSpinBox.setSuffix('m')
        self._mw.afm_x_max_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.afm_x_num_SpinBox.setRange(2, 10000)

        self._mw.afm_y_min_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_y_min_DSpinBox.setSuffix('m')
        self._mw.afm_y_min_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.afm_y_max_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_y_max_DSpinBox.setSuffix('m')
        self._mw.afm_y_max_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.afm_y_num_SpinBox.setRange(2, 10000)


        self._mw.afm_target_x_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_target_x_DSpinBox.setSuffix('m')
        self._mw.afm_target_x_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.afm_target_y_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_target_y_DSpinBox.setSuffix('m')
        self._mw.afm_target_y_DSpinBox.setMinimalStep(0.1e-6)

        self._mw.obj_cur_x_DSpinBox.setSuffix('m')
        self._mw.obj_cur_x_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_cur_y_DSpinBox.setSuffix('m')
        self._mw.obj_cur_y_DSpinBox.setRange(0.0, 30e-6)
        self._mw.obj_cur_z_DSpinBox.setSuffix('m')
        self._mw.obj_cur_z_DSpinBox.setRange(0.0, 10e-6)

        self._mw.afm_curr_x_DSpinBox.setSuffix('m')
        self._mw.afm_curr_x_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_curr_x_DSpinBox.setDecimals(3, dynamic_precision=False)
        self._mw.afm_curr_y_DSpinBox.setSuffix('m')
        self._mw.afm_curr_y_DSpinBox.setRange(0.0, 100e-6)
        self._mw.afm_curr_y_DSpinBox.setDecimals(3, dynamic_precision=False)

        # set initial values:
        self._mw.obj_x_min_DSpinBox.setValue(0.0e-6)
        self._mw.obj_x_max_DSpinBox.setValue(30e-6)
        self._mw.obj_y_min_DSpinBox.setValue(0.0e-6)
        self._mw.obj_y_max_DSpinBox.setValue(30e-6)
        self._mw.obj_z_min_DSpinBox.setValue(0.0e-6)
        self._mw.obj_z_max_DSpinBox.setValue(10e-6)
        
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
              
        DockWidgetContent is a usual QWidget, hosting the internal content of the 
        DockWidget.

        Another good reference:
          https://www.geeksforgeeks.org/pyqt5-qdockwidget-setting-multiple-widgets-inside-it/

        """

        self._dock_state = ''

        ref_last_dockwidget = None
        is_first = True

        data_dict = self.get_all_data_matrices()
        c_scale = self.getColorScale()

        for obj_name in data_dict:

            # connect all dock widgets to the central widget
            dockwidget = QtWidgets.QDockWidget(self._mw.centralwidget)

            self._dockwidget_container[obj_name] = dockwidget
            setattr(self._mw,  f'dockWidget_{obj_name}', dockwidget)
            dockwidget.name = obj_name # store the original name. 

            # hide controls for the optimizer, it is not needed anyway
            if 'opti_xy' in obj_name:
                skip_colorcontrol = True
            else:
                skip_colorcontrol = False

            # take a different creation style for line widgets
            if 'opti_z' in obj_name:
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
                self._mw.splitDockWidget(dockwidget, self._mw.dockWidget_afm,
                                         QtCore.Qt.Orientation(1))
                is_first = False
            else:
                self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(4), dockwidget)
                self._mw.tabifyDockWidget(ref_last_dockwidget, dockwidget)

            # for optimizer, the creation is a line item, not an 2d image
            if 'opti_z' in obj_name:

                plot_item = self._create_plot_item(obj_name, 
                               data_dict[obj_name]['coord0_arr'], 
                               data_dict[obj_name]['data'])
                dockwidget.graphicsView.addItem(plot_item)

            else:

                image_item = self._create_image_item(obj_name, data_dict[obj_name]['data'])
                dockwidget.graphicsView_matrix.addItem(image_item)
                image_item.setLookupTable(c_scale.lut)

                colorbar = self._create_colorbar(obj_name, c_scale)
                dockwidget.graphicsView_cb.addItem(colorbar)
                dockwidget.graphicsView_cb.hideAxis('bottom')

                data_name = data_dict[obj_name]['nice_name']
                si_units = data_dict[obj_name]['si_units']

                dockwidget.graphicsView_cb.setLabel('left', data_name, units=si_units)
                dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)

            ref_last_dockwidget = dockwidget

            # cover now the special adaptations:

            if ('fw' in obj_name) or ('bw' in obj_name) or ('opti_xy' in obj_name):

                dockwidget.graphicsView_matrix.setLabel('bottom', 'X position', units='m')
                dockwidget.graphicsView_matrix.setLabel('left', 'Y position', units='m')

            if 'obj' in obj_name:
                axis0 = obj_name[-2].upper()
                axis1 = obj_name[-1].upper()

                dockwidget.graphicsView_matrix.setLabel('bottom', f'{axis0} position', units='m')
                dockwidget.graphicsView_matrix.setLabel('left', f'{axis1} position', units='m')

            if 'opti_z' in obj_name:
                dockwidget.graphicsView.setLabel('bottom', 'Z position', units='m')
                dockwidget.graphicsView.setLabel('left', 'Fluorescence', units='c/s') 

        self.adjust_qafm_image()
        self.adjust_all_obj_images()
        self.adjust_optimizer_image('opti_xy')


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
        if skip_colorcontrol:
            grid.addWidget(graphicsView_matrix,   0, 0, 1, 1) # start [0,0], span 7 rows down, 1 column wide
            doubleSpinBox_cb_max.hide()
            doubleSpinBox_per_max.hide()
            grid.addWidget(graphicsView_cb,       0, 1, 1, 1) # start [2,1], span 1 rows down, 1 column wide
            doubleSpinBox_per_min.hide()
            doubleSpinBox_cb_min.hide()
            radioButton_cb_man.hide()
            radioButton_cb_per.hide()
        else:

            grid.addWidget(graphicsView_matrix,   0, 0, 7, 1) # start [0,0], span 7 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_cb_max,  0, 1, 1, 1) # start [0,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_per_max, 1, 1, 1, 1) # start [1,1], span 1 rows down, 1 column wide
            grid.addWidget(graphicsView_cb,       2, 1, 1, 1) # start [2,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_per_min, 3, 1, 1, 1) # start [3,1], span 1 rows down, 1 column wide
            grid.addWidget(doubleSpinBox_cb_min,  4, 1, 1, 1) # start [4,1], span 1 rows down, 1 column wide
            grid.addWidget(radioButton_cb_man,    5, 1, 1, 1) # start [5,1], span 1 rows down, 1 column wide
            grid.addWidget(radioButton_cb_per,    6, 1, 1, 1) # start [6,1], span 1 rows down, 1 column wide


    def _create_meas_params(self):
        """ Generate CheckBoxes to control which AFM parameters are to be measured."""

        meas_params_units = self._qafm_logic.get_afm_meas_params()
        meas_params = list(meas_params_units)

        for index, entry in enumerate(meas_params):

            checkbox = CustomCheckBox(self._mw.scan_param_groupBox)
            checkbox.setObjectName(entry)
            checkbox.setText(entry)
            checkbox.valueChanged_custom.connect(self._update_afm_dockwidget_by_name)
            checkbox.setChecked(True)
            checkbox.setChecked(False)

            self._mw.gridLayout_scan_params.addWidget(checkbox, index, 0, 1, 1)
            self._checkbox_container[entry] = checkbox


    def _update_afm_dockwidget_by_name(self, make_visible, name):
        """ Helper method to call the correct dockwidget

        @param bool make_visible: visible or not
        @param str name: generic name of the dock widget
        """
        self.update_dockwidget_visibility(make_visible, f'{name}_fw')
        self.update_dockwidget_visibility(make_visible, f'{name}_bw')


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

        for entry in self._checkbox_container:
            self._checkbox_container[entry].setChecked(False)

        self._dock_state == 'double'


    def split_view(self):
        """ Split the dockwidgets in forward and backward scans.
        Attach the remaining dockwidgets to the forward group.
        """

        if self._dock_state == 'double':
            return

        first_object = True
        ref_last_dockwidget = None

        for key, item in self._dockwidget_container.items():
            if 'bw' in key:
                if first_object:
                    self._mw.splitDockWidget(self._mw.dockWidget_afm, 
                                             item,  
                                             QtCore.Qt.Orientation(1))
                    self._mw.splitDockWidget(item, 
                                             self._mw.dockWidget_afm, 
                                             QtCore.Qt.Orientation(1))
                    first_object = False
                else:
                    self._mw.tabifyDockWidget(ref_last_dockwidget, item)
            ref_last_dockwidget = item

        # Creates the optimizer below the optical Widget
        #FIXME: reversed can only be applied on dict from python 3.8, whenever
        #       updated to 3.8, remove this list handling intermediate layer
        for key, item in reversed(list(self._dockwidget_container.items())):

            if 'opti_xy' in key:
                self._mw.splitDockWidget(self._mw.dockWidget_objective,
                                         item,
                                         QtCore.Qt.Orientation(2))
            if 'opti_z' in key:
                self._mw.splitDockWidget(self._mw.dockWidget_objective,
                                         item,
                                         QtCore.Qt.Orientation(2))

        self._dock_state = 'double'


    def combine_view(self):
        """ Combine all the dockwidget in the center under one. """

        if self._dock_state == 'single':
            return

        ref_last_dockwidget = None
        
        #FIXME: reversed can only be applied on dict from python 3.8, whenever
        #       updated to 3.8, remove this list handling intermediate layer
        for key, item in reversed(list(self._dockwidget_container.items())):
            if 'fw' in key:
                ref_last_dockwidget = item
                break

        for key, item in self._dockwidget_container.items():
            if 'bw' in key:
                self._mw.tabifyDockWidget(ref_last_dockwidget, item)

            ref_last_dockwidget = item

        self._dock_state = 'single'

    def _arrange_iso_dockwidget(self):
        """ Helper method to arrange the iso-b dockwidget properly above the afm dockwidget."""

        # you have to do it this way, otherwise, you mess up the order of the 
        # dock widgets.
        self._mw.splitDockWidget(self._mw.dockWidget_afm, 
                                 self._mw.dockWidget_isob, 
                                 QtCore.Qt.Orientation(2)) # vertical orientation
        self._mw.splitDockWidget(self._mw.dockWidget_isob, 
                                 self._mw.dockWidget_afm, 
                                 QtCore.Qt.Orientation(2)) # vertical orientation



    def adjust_qafm_image(self):
        """ Fit the axis and range parameters to the currently started scan. """

        # It is extremely crucial that before adjusting the window view and
        # limits and its extend, to make an update of the current image. 
        # Otherwise the adjustment will just be made for the previous image and
        # you will get completely wrong display.
        self._update_qafm_data()

        qafm_data = self._qafm_logic.get_qafm_data()

        for entry in self._image_container:

            if ('fw' in entry) or ('bw' in entry):

                image = self._image_container[entry]
                xy_viewbox = image.getViewBox()

                xMin = qafm_data[entry]['coord0_arr'][0]
                xMax = qafm_data[entry]['coord0_arr'][-1]
                yMin = qafm_data[entry]['coord1_arr'][0]
                yMax = qafm_data[entry]['coord1_arr'][-1]

                res_x = len(qafm_data[entry]['coord0_arr'])
                res_y = len(qafm_data[entry]['coord1_arr'])

                px_size = ((xMax - xMin) / (res_x - 1), (yMax - yMin) / (res_y - 1))
                image.set_image_extent(((xMin - px_size[0] / 2, xMax + px_size[0] / 2),
                                        (yMin - px_size[1] / 2, yMax + px_size[1] / 2)))
                xy_viewbox.updateAutoRange()
                xy_viewbox.updateViewRange()


    def adjust_all_obj_images(self):
        obj_names = list(self._qafm_logic.get_obj_data())
        for entry in obj_names:
            self.adjust_obj_image(entry)


    @QtCore.Slot(str)
    def adjust_obj_image(self, obj_name):
        """ Update the objective scan image with data from the logic.

        @param str obj_name: either 'obj_xy', 'obj_xz' or 'obj_yz'
        """

        # It is extremely crucial that before adjusting the window view and
        # limits and its extend, to make an update of the current image. 
        # Otherwise the adjustment will just be made for the previous image and
        # you will get completely wrong display.
        self._update_obj_data(obj_name)

        obj_data = self._qafm_logic.get_obj_data()[obj_name]

        image = self._image_container[obj_name]

        viewbox = image.getViewBox()

        Min0 = obj_data['coord0_arr'][0]
        Max0 = obj_data['coord0_arr'][-1]
        Min1 = obj_data['coord1_arr'][0]
        Max1 = obj_data['coord1_arr'][-1]

        res_0 = len(obj_data['coord0_arr'])
        res_1 = len(obj_data['coord1_arr'])

        px_size = ((Max0 - Min0) / (res_0 - 1), (Max1 - Min1) / (res_1 - 1))
        image.set_image_extent(((Min0 - px_size[0] / 2, Max0 + px_size[0] / 2),
                                (Min1 - px_size[1] / 2, Max1 + px_size[1] / 2)))
        viewbox.updateAutoRange()
        viewbox.updateViewRange()


    @QtCore.Slot(str)
    def adjust_optimizer_image(self, obj_name):
        """ Update the view of the xy optimizer with data from the logic. """

        if obj_name == 'opti_xy':

            # It is extremely crucial that before adjusting the window view and
            # limits and its extend, to make an update of the current image. 
            # Otherwise the adjustment will just be made for the previous image and
            # you will get completely wrong display.
            self._update_opti_data(obj_name)

            obj_data = self._qafm_logic.get_opti_data()[obj_name]
            image = self._image_container[obj_name]

            viewbox = image.getViewBox()

            Min0 = obj_data['coord0_arr'][0]
            Max0 = obj_data['coord0_arr'][-1]
            Min1 = obj_data['coord1_arr'][0]
            Max1 = obj_data['coord1_arr'][-1]

            res_0 = len(obj_data['coord0_arr'])
            res_1 = len(obj_data['coord1_arr'])

            px_size = ((Max0 - Min0) / (res_0 - 1), (Max1 - Min1) / (res_1 - 1))
            image.set_image_extent(((Min0 - px_size[0] / 2, Max0 + px_size[0] / 2),
                                    (Min1 - px_size[1] / 2, Max1 + px_size[1] / 2)))
            viewbox.updateAutoRange()
            viewbox.updateViewRange()


    def _update_qafm_data(self):
        """ Update all displays of the qaft scan with data from the logic. """

        qafm_data = self._qafm_logic.get_qafm_data()

        # order them in forward scan and backward scan:
        for param_name in qafm_data:
            if 'fw' in param_name:
                cb_range = self._get_scan_cb_range(param_name)

                if qafm_data[param_name]['display_range'] is not None:
                    qafm_data[param_name]['display_range'] = cb_range 

                self._image_container[param_name].setImage(image=qafm_data[param_name]['data'],
                                                           levels=(cb_range[0], cb_range[1]))
                self._refresh_scan_colorbar(param_name)
                # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
                self._image_container[param_name].getViewBox().updateAutoRange()

        for param_name in qafm_data:
            if 'bw' in param_name:

                cb_range = self._get_scan_cb_range(param_name)

                if qafm_data[param_name]['display_range'] is not None:
                    qafm_data[param_name]['display_range'] = cb_range

                self._image_container[param_name].setImage(image=qafm_data[param_name]['data'],
                                                           levels=(cb_range[0], cb_range[1]))
                self._refresh_scan_colorbar(param_name)
                # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
                self._image_container[param_name].getViewBox().updateAutoRange()


    def _update_data_from_dockwidget(self, dockwidget_name):
        """ Update all displays of the dockwidget with data from logic.

        @param str dockwidget_name: name of the associated dockwidget.
        """

        data_obj = self.get_all_data_matrices()[dockwidget_name]
        cb_range = self._get_scan_cb_range(dockwidget_name)
        data = data_obj['data']

        # the name of the image object has to be the same as the dockwidget
        self._image_container[dockwidget_name].setImage(image=data, levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(dockwidget_name)
        # self._image_container[dockwidget_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
        self._image_container[dockwidget_name].getViewBox().updateAutoRange()

        # Be careful! I use here the feature that dicts are passed by reference,
        # i.e. changing this object, will change the initial data!
        data_obj['display_range'] = cb_range


    @QtCore.Slot(str)
    def _update_obj_data(self, obj_name=None):

        obj_data = self._qafm_logic.get_obj_data()

        # bascically: update all objective pictures
        if obj_name is None:
            update_name_list = list(obj_data)
        else:
            update_name_list = [obj_name]

        for name in update_name_list:

            cb_range = self._get_scan_cb_range(name)

            if obj_data[name]['display_range'] is not None:
                obj_data[name]['display_range'] = cb_range

            self._image_container[name].setImage(image=obj_data[name]['data'], 
                                                 levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(name)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[name].getViewBox().updateAutoRange()


    def _update_opti_data(self, obj_name=None):

        opti_data = self._qafm_logic.get_opti_data()

        if obj_name == 'opti_xy':

            cb_range = self._get_scan_cb_range(obj_name)

            if opti_data[obj_name]['display_range'] is not None:
                opti_data[obj_name]['display_range'] = cb_range

            self._image_container[obj_name].setImage(image=opti_data[obj_name]['data'], 
                                                 levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(obj_name)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[obj_name].getViewBox().updateAutoRange() 
        
        elif obj_name == 'opti_z':

            self._plot_container[obj_name].setData(x=opti_data[obj_name]['coord0_arr'], 
                                                   y=opti_data[obj_name]['data'])

            self._plot_container[obj_name].getViewBox().updateAutoRange() 


    def update_target_pos(self):
        """ Get new value from logic and update the display."""
        x_max, y_max, c_max, z_max, c_max_z = self._qafm_logic._opt_val

        self._mw.obj_target_x_DSpinBox.setValue(x_max)
        self._mw.obj_target_y_DSpinBox.setValue(y_max)
        self._mw.obj_target_z_DSpinBox.setValue(z_max)


    def _get_scan_cb_range(self, dockwidget_name):
        """ Determines the cb_min and cb_max values for the xy scan image.
        @param str dockwidget_name: name associated to the dockwidget.

        """
        
        dockwidget = self.get_dockwidget(dockwidget_name)
        xy_image = self._image_container[dockwidget_name]

        # If "Manual" is checked, or the image data is empty (all zeros), then take manual cb range.
        if dockwidget.radioButton_cb_man.isChecked() or np.count_nonzero(xy_image.image) < 1:
            cb_min = dockwidget.doubleSpinBox_cb_min.value()
            cb_max = dockwidget.doubleSpinBox_cb_max.value()

        # Otherwise, calculate cb range from percentiles.
        else:
            # Exclude any zeros (which are typically due to unfinished scan)
            xy_image_nonzero = xy_image.image[np.nonzero(xy_image.image)]

            # Read centile range
            low_centile = dockwidget.doubleSpinBox_per_min.value()
            high_centile = dockwidget.doubleSpinBox_per_max.value()

            cb_min = np.percentile(xy_image_nonzero, low_centile)
            cb_max = np.percentile(xy_image_nonzero, high_centile)

        cb_range = [cb_min, cb_max]

        return cb_range


    def _refresh_scan_colorbar(self, dockwidget_name):
        """ Update the colorbar of the Dockwidget.

        @param str dockwidget_name: the name of the dockwidget to update.
        """

        cb_range =  self._get_scan_cb_range(dockwidget_name)
        self._cb_container[dockwidget_name].refresh_colorbar(cb_range[0], cb_range[1])

    def get_dockwidget(self, objectname):
        """ Get the reference to the dockwidget associated to the objectname.

        @param str objectname: name under which the dockwidget can be found.
        """

        dw = self._dockwidget_container.get(objectname)
        if dw is None:
            self.log.warning(f'No dockwidget with name "{objectname}" was found! Be careful!')

        return dw

    def set_current_pos_to_target(self):
        """ Set the current position to target position. """

        x_target = self._mw.obj_cur_x_DSpinBox.value()
        self._mw.obj_target_x_DSpinBox.setValue(x_target)
        y_target = self._mw.obj_cur_y_DSpinBox.value()
        self._mw.obj_target_y_DSpinBox.setValue(y_target)
        z_target = self._mw.obj_cur_z_DSpinBox.value()
        self._mw.obj_target_z_DSpinBox.setValue(z_target)

    def set_center_pos_to_target(self):
        """ Set the target position to the middle of all scan ranges. """

        #FIXME: Make this nicer by obtaining the maximal traveling range and 
        #       take half of it.
        self._mw.obj_target_x_DSpinBox.setValue(15e-6)
        self._mw.obj_target_y_DSpinBox.setValue(15e-6)
        self._mw.obj_target_z_DSpinBox.setValue(5e-6)

    def start_qafm_scan_clicked(self):
        """ Manages what happens if the xy qafm scan is started. """

        self.disable_scan_actions()

        self._mw.actionOptimize_Pos.setEnabled(True)

        x_start = self._mw.afm_x_min_DSpinBox.value()
        x_stop = self._mw.afm_x_max_DSpinBox.value()
        y_start = self._mw.afm_y_min_DSpinBox.value()
        y_stop = self._mw.afm_y_max_DSpinBox.value()
        res_x = self._mw.afm_x_num_SpinBox.value()
        res_y = self._mw.afm_y_num_SpinBox.value()

        meas_params = ['counts']

        # add dual ISO-B mode parameter if necessary
        if self._qafm_logic._sg_iso_b_operation \
           and not self._qafm_logic._sg_iso_b_single_mode:
           meas_params.extend(['counts2', 'counts_diff'])

        for entry in self._checkbox_container:
            if self._checkbox_container[entry].isChecked():
                meas_params.append(entry)

        # self._qafm_logic.start_scan_area_qafm_bw_fw_by_point
        self._qafm_logic.start_scan_area_qafm_bw_fw_by_line(coord0_start=x_start,
                                                            coord0_stop=x_stop,
                                                            coord0_num=res_x,
                                                            coord1_start=y_start,
                                                            coord1_stop=y_stop,
                                                            coord1_num=res_y,
                                                            plane='XY',
                                                            meas_params=meas_params)

    def start_obj_scan_xy_scan_clicked(self):
        """ Manages what happens if the objective xy scan is started. """

        self.disable_scan_actions()

        x_start = self._mw.obj_x_min_DSpinBox.value()
        x_stop = self._mw.obj_x_max_DSpinBox.value()
        y_start = self._mw.obj_y_min_DSpinBox.value()
        y_stop = self._mw.obj_y_max_DSpinBox.value()
        res_x = self._mw.obj_x_num_SpinBox.value()
        res_y = self._mw.obj_y_num_SpinBox.value()

        self._qafm_logic.start_scan_area_obj_by_line(coord0_start=x_start,
                                                      coord0_stop=x_stop,
                                                      coord0_num=res_x,
                                                      coord1_start=y_start, 
                                                      coord1_stop=y_stop,
                                                      coord1_num=res_y,
                                                      plane='X2Y2', 
                                                      continue_meas=False)

    def start_obj_scan_xz_scan_clicked(self):
        """ Manages what happens if the objective xz scan is started. """

        self.disable_scan_actions()

        x_start = self._mw.obj_x_min_DSpinBox.value()
        x_stop = self._mw.obj_x_max_DSpinBox.value()
        z_start = self._mw.obj_z_min_DSpinBox.value()
        z_stop = self._mw.obj_z_max_DSpinBox.value()
        res_x = self._mw.obj_x_num_SpinBox.value()
        res_z = self._mw.obj_z_num_SpinBox.value()

        self._qafm_logic.start_scan_area_obj_by_line(coord0_start=x_start,
                                                      coord0_stop=x_stop,
                                                      coord0_num=res_x,
                                                      coord1_start=z_start, 
                                                      coord1_stop=z_stop,
                                                      coord1_num=res_z,
                                                      plane='X2Z2', 
                                                      continue_meas=False)


    def start_obj_scan_yz_scan_clicked(self):
        """ Manages what happens if the objective yz scan is started. """

        self.disable_scan_actions()

        y_start = self._mw.obj_y_min_DSpinBox.value()
        y_stop = self._mw.obj_y_max_DSpinBox.value()
        z_start = self._mw.obj_z_min_DSpinBox.value()
        z_stop = self._mw.obj_z_max_DSpinBox.value()
        res_y = self._mw.obj_y_num_SpinBox.value()
        res_z = self._mw.obj_z_num_SpinBox.value()

        self._qafm_logic.start_scan_area_obj_by_line(coord0_start=y_start,
                                                      coord0_stop=y_stop,
                                                      coord0_num=res_y,
                                                      coord1_start=z_start, 
                                                      coord1_stop=z_stop,
                                                      coord1_num=res_z,
                                                      plane='Y2Z2', 
                                                      continue_meas=False)


    def start_optimize_clicked(self):
        """ Start optimizer scan."""

        self.disable_scan_actions()

        x_target = self._mw.obj_target_x_DSpinBox.value()
        y_target = self._mw.obj_target_y_DSpinBox.value()
        z_target = self._mw.obj_target_z_DSpinBox.value()

        # settings of optimizer can be set in its setting window

        self._qafm_logic.set_optimizer_target(x_target=x_target, 
                                              y_target=y_target, 
                                              z_target=z_target)

        ret_val = self._qafm_logic.set_optimize_request(True)
        # if the request is valid, then True will be returned, if not False

        self._mw.actionOptimize_Pos.setEnabled(not ret_val)  

    def stop_any_scanning(self):
        """ Stop all scanning actions."""

        ret_val = self._qafm_logic.stop_measure()

        # some error happened, hence enable the scan buttons again.
        if ret_val == -1:
            self.enable_scan_actions()

    def disable_scan_actions(self):
        # for safety, store status variables
        self.store_status_var()

        self._mw.actionStart_QAFM_Scan.setEnabled(False)
        self._mw.actionStart_Obj_XY_scan.setEnabled(False)
        self._mw.actionStart_Obj_XZ_scan.setEnabled(False)
        self._mw.actionStart_Obj_YZ_scan.setEnabled(False)
        self._mw.actionGo_To_AFM_pos.setEnabled(False)
        self._mw.actionGo_To_Obj_pos.setEnabled(False)
        self._mw.actionOptimize_Pos.setEnabled(False)
        self._mw.actionSaveDataQAFM.setEnabled(False)
        self._mw.actionSaveObjData.setEnabled(False)
        self._mw.actionSaveOptiData.setEnabled(False)

    def enable_scan_actions(self):
        self._mw.actionStart_QAFM_Scan.setEnabled(True)
        self._mw.actionStart_Obj_XY_scan.setEnabled(True)
        self._mw.actionStart_Obj_XZ_scan.setEnabled(True)
        self._mw.actionStart_Obj_YZ_scan.setEnabled(True)
        self._mw.actionGo_To_AFM_pos.setEnabled(True)
        self._mw.actionGo_To_Obj_pos.setEnabled(True)
        self._mw.actionOptimize_Pos.setEnabled(True)
        self._mw.actionSaveDataQAFM.setEnabled(True)
        self._mw.actionSaveObjData.setEnabled(True)
        self._mw.actionSaveOptiData.setEnabled(True)

    def enable_optimizer_action(self):
        self._mw.actionOptimize_Pos.setEnabled(True)

        # check the state of the logic and enable the buttons.
        if self._qafm_logic.module_state() == 'idle':
            self.enable_scan_actions()


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

    @QtCore.Slot(dict)
    def update_obj_pos(self, pos_dict):

        for entry in pos_dict:
            spinbox = getattr(self._mw, f'obj_cur_{entry[0].lower()}_DSpinBox')
            spinbox.setValue(pos_dict[entry])

    @QtCore.Slot(dict)
    def update_afm_pos(self, pos_dict):

        for entry in pos_dict:
            if entry[0].lower() == 'z':
                continue
            spinbox = getattr(self._mw, f'afm_curr_{entry[0].lower()}_DSpinBox')
            spinbox.setValue(pos_dict[entry])

    def goto_afm_pos_clicked(self):

        self.disable_scan_actions()

        x = self._mw.afm_target_x_DSpinBox.value()
        y = self._mw.afm_target_y_DSpinBox.value()
        # connect via signal for non-blocking behaviour
        self.sigGotoAFMpos.emit({'x': x, 'y': y})
        #self._qafm_logic.start_set_afm_pos(x,y)

    def goto_obj_pos_clicked(self):

        self.disable_scan_actions()
        
        x = self._mw.obj_target_x_DSpinBox.value()
        y = self._mw.obj_target_y_DSpinBox.value()
        z = self._mw.obj_target_z_DSpinBox.value()

        # connect via signal for non-blocking behaviour
        self.sigGotoObjpos.emit({'x': x, 'y': y, 'z': z})
        #self._qafm_logic.start_set_obj_pos()

    def update_targetpos_xy(self, event, xy_pos):

        self._mw.obj_target_x_DSpinBox.setValue(xy_pos.x())
        self._mw.obj_target_y_DSpinBox.setValue(xy_pos.y())


    def save_obj_data_clicked(self):
        """Method enabling the saving of the objective data.
        """
        self._mw.actionSaveObjData.setEnabled(False)

        obj_name_list = []
        if self._mw.save_obj_xy_CheckBox.isChecked():
            obj_name_list.append('obj_xy')
        if self._mw.save_obj_xz_CheckBox.isChecked():
            obj_name_list.append('obj_xz')
        if self._mw.save_obj_yz_CheckBox.isChecked():
            obj_name_list.append('obj_yz')

        tag = self._mw.obj_save_LineEdit.text()
        probe_name = self._mw.probename_LineEdit.text()
        sample_name = self._mw.samplename_LineEdit.text()
        daily_folder = self._mw.daily_folder_CheckBox.isChecked()

        self._qafm_logic.save_obj_data(obj_name_list, tag, probe_name, sample_name,
                                        use_qudi_savescheme=False,
                                        daily_folder=daily_folder)

    def enable_obj_save_button(self):
        """Method making sure the save button is enabled after objective data is saved. 
        """
        self._mw.actionSaveObjData.setEnabled(True)


    def save_qafm_data_clicked(self):
        """Method enabling the saving of the qafm data.
        """
        self._mw.actionSaveDataQAFM.setEnabled(False)

        tag = self._mw.qafm_save_LineEdit.text()
        probe_name = self._mw.probename_LineEdit.text()
        sample_name = self._mw.samplename_LineEdit.text()
        daily_folder = self._mw.daily_folder_CheckBox.isChecked()

        self._qafm_logic.save_qafm_data(tag, probe_name, sample_name,
                                        use_qudi_savescheme=False,
                                        daily_folder=daily_folder)


    def autosave_qafm_measurement(self):
        """ Auto save method to react to signals for qafm measurements. """
        if self._sd.auto_save_qafm_CheckBox.isChecked():
            self.autosave_qafm_data()

    def autosave_quantitative_measurement(self):
        """ Auto save method to react to signals for quantitative measurements. """
        if self._sd.auto_save_quanti_CheckBox.isChecked():
            self.autosave_qafm_data()

    def autosave_qafm_data(self):
        """ Save automatically after scan has finished the data. """

        self._mw.actionSaveDataQAFM.setEnabled(False)

        tag = self._mw.qafm_save_LineEdit.text() + '_autosave'
        probe_name = self._mw.probename_LineEdit.text()
        sample_name = self._mw.samplename_LineEdit.text()
        daily_folder = self._mw.daily_folder_CheckBox.isChecked()

        self._qafm_logic.save_qafm_data(tag, probe_name, sample_name,
                                        use_qudi_savescheme=False,
                                        daily_folder=daily_folder)        


    def enable_qafm_save_button(self):
        """Method making sure the save button is enabled after qafm data is saved. 
        """
        self._mw.actionSaveDataQAFM.setEnabled(True)

    def save_opti_data_clicked(self):
        """Method enabling the saving of the optimizer data.
        """
        self._mw.actionSaveOptiData.setEnabled(False)

        tag = self._mw.obj_save_LineEdit.text()
        probe_name = self._mw.probename_LineEdit.text()
        sample_name = self._mw.samplename_LineEdit.text()
        daily_folder = self._mw.daily_folder_CheckBox.isChecked()

        self._qafm_logic.save_optimizer_data(tag, probe_name, sample_name, 
                                            use_qudi_savescheme=False, 
                                            daily_folder=daily_folder)

    def enable_opti_save_button(self):
        """Method making sure the save button is enabled after opti data is saved. 
        """
        self._mw.actionSaveOptiData.setEnabled(True)


    # Quantitative Measurement settings

    def enable_scan_actions_quanti(self):
        self.enable_scan_actions()
        self._qm.Start_QM_PushButton.setEnabled(True)
        self._qm.Continue_QM_PushButton.setEnabled(True)

    def disable_scan_actions_quanti(self):
        self.disable_scan_actions()
        self._qm.Start_QM_PushButton.setEnabled(False)
        self._qm.Continue_QM_PushButton.setEnabled(False)

    def start_quantitative_measure_clicked(self, continue_meas=False):
        self.disable_scan_actions_quanti()

        x_start = self._mw.afm_x_min_DSpinBox.value()
        x_stop = self._mw.afm_x_max_DSpinBox.value()
        y_start = self._mw.afm_y_min_DSpinBox.value()
        y_stop = self._mw.afm_y_max_DSpinBox.value()
        res_x = self._mw.afm_x_num_SpinBox.value()
        res_y = self._mw.afm_y_num_SpinBox.value()

        meas_params = ['counts', 'b_field']
        for entry in self._checkbox_container:
            if self._checkbox_container[entry].isChecked():
                meas_params.append(entry)

        # check only one button, this is sufficient
        fw_scan = self._qm.scan_dir_fw_RadioButton.isChecked() 

        afm_int_time = self._qm.afm_int_time_DoubleSpinBox.value()
        idle_move_time = self._qm.idle_move_time_QDoubleSpinBox.value()
        esr_freq_start = self._qm.esr_freq_start_DoubleSpinBox.value()
        esr_freq_stop = self._qm.esr_freq_stop_DoubleSpinBox.value()
        esr_freq_num = self._qm.esr_freq_num_SpinBox.value()
        esr_count_freq = self._qm.esr_count_freq_DoubleSpinBox.value()
        esr_mw_power = self._qm.esr_mw_power_DoubleSpinBox.value()
        esr_runs = self._qm.esr_runs_SpinBox.value()
        single_res = self._qm.esr_single_res_RadioButton.isChecked() 
        optimize_period = self._qm.optimizer_period_DoubleSpinBox.value()

        if fw_scan:
            self._qafm_logic.start_scan_area_quanti_qafm_fw_by_point(
                coord0_start=x_start, coord0_stop=x_stop, coord0_num=res_x, 
                coord1_start=y_start, coord1_stop=y_stop, coord1_num=res_y, 
                int_time_afm=afm_int_time, idle_move_time=idle_move_time, 
                freq_start=esr_freq_start, freq_stop=esr_freq_stop, 
                freq_points=esr_freq_num, esr_count_freq=esr_count_freq,
                mw_power=esr_mw_power, num_esr_runs=esr_runs, 
                optimize_period=optimize_period, meas_params=meas_params,
                single_res=single_res, continue_meas=continue_meas)

        else:

            self._qafm_logic.start_scan_area_quanti_qafm_fw_bw_by_point(
                coord0_start=x_start, coord0_stop=x_stop, coord0_num=res_x, 
                coord1_start=y_start, coord1_stop=y_stop, coord1_num=res_y, 
                int_time_afm=afm_int_time, idle_move_time=idle_move_time, 
                freq_start=esr_freq_start, freq_stop=esr_freq_stop, 
                freq_points=esr_freq_num, esr_count_freq=esr_count_freq,
                mw_power=esr_mw_power, num_esr_runs=esr_runs, 
                optimize_period=optimize_period, meas_params=meas_params,
                single_res=single_res, continue_meas=continue_meas)


    def continue_quantitative_measure_clicked(self):
        self.start_quantitative_measure_clicked(continue_meas=True)

    def stop_quantitative_measure_clicked(self):
        self.stop_any_scanning()



