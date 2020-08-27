
import numpy as np
import pyqtgraph as pg
import os
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

- correct the eventloop with matplotlib!!!
- correct order of dockwidgets
- save of all the qafm data in one plot
- save optimizer data
- create save settings
- Add colorbar settings to savedata
- check the colorbar implementation for smaller values => 32bit problem...
- enable the save button when safe is finished!

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


class QuantitativeMeasurementWindow(QtWidgets.QWidget):
    """ Create the SettingsDialog window, based on the corresponding *.ui file."""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_quantitative_mode.ui')

        # Load it
        super(QuantitativeMeasurementWindow, self).__init__()
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

    __version__ = '0.1.4'

    ## declare connectors
    qafmlogic = Connector(interface='AFMConfocalLogic') # interface='AFMConfocalLogic'


    sigGotoObjpos = QtCore.Signal(dict)
    sigGotoAFMpos = QtCore.Signal(dict)
    sigColorBarChanged = QtCore.Signal(object)  # emit a dockwidget object.


    image_x_padding = ConfigOption('image_x_padding', 0.02)
    image_y_padding = ConfigOption('image_y_padding', 0.02)
    image_z_padding = ConfigOption('image_z_padding', 0.02)
    saved_default_view = ConfigOption('saved_default_view', b'\x00\x00\x00\xff\x00\x00\x00\x00\xfd\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x01\x04\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x03\xfb\x00\x00\x00(\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x01\x00\x00\x00D\x00\x00\x01\xd3\x00\x00\x01\xd3\x00\x07\xff\xff\xfb\x00\x00\x00\x0e\x00o\x00p\x00t\x00i\x00_\x00x\x00y\x01\x00\x00\x02\x17\x00\x00\x01\x10\x00\x00\x01\x10\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00p\x00t\x00i\x00_\x00z\x01\x00\x00\x03+\x00\x00\x00\xba\x00\x00\x00f\x00\xff\xff\xff\x00\x00\x00\x01\x00\x00\x06x\x00\x00\x03\xa1\xfc\x02\x00\x00\x00\x01\xfc\x00\x00\x00D\x00\x00\x03\xa1\x00\x00\x03E\x00\xff\xff\xff\xfc\x01\x00\x00\x00\x03\xfc\x00\x00\x01\x08\x00\x00\x02\xa3\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x02\x01\x00\x00\x00\x0e\xfb\x00\x00\x00\x12\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x14\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x12\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00M\x00a\x00g\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x10\x00P\x00h\x00a\x00s\x00e\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0e\x00F\x00r\x00e\x00q\x00_\x00f\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\n\x00N\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\n\x00L\x00f\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00E\x00x\x001\x00_\x00f\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00b\x00j\x00_\x00x\x00y\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00b\x00j\x00_\x00x\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00o\x00b\x00j\x00_\x00y\x00z\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfc\x00\x00\x03\xaf\x00\x00\x02\xa8\x00\x00\x00\xa4\x00\xff\xff\xff\xfa\x00\x00\x00\x02\x01\x00\x00\x00\x0b\xfb\x00\x00\x00\x12\x00c\x00o\x00u\x00n\x00t\x00s\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x14\x00b\x00_\x00f\x00i\x00e\x00l\x00d\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00D\x00a\x00c\x00)\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00H\x00e\x00i\x00g\x00h\x00t\x00(\x00S\x00e\x00n\x00)\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x12\x00I\x00p\x00r\x00o\x00b\x00e\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00M\x00a\x00g\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x10\x00P\x00h\x00a\x00s\x00e\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0e\x00F\x00r\x00e\x00q\x00_\x00b\x00w\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\n\x00N\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\n\x00L\x00f\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfb\x00\x00\x00\x0c\x00E\x00x\x001\x00_\x00b\x00w\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\xa4\x00\xff\xff\xff\xfc\x00\x00\x06[\x00\x00\x01%\x00\x00\x00\xfc\x00\xff\xff\xff\xfc\x02\x00\x00\x00\x02\xfb\x00\x00\x00\x1e\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00i\x00s\x00o\x00b\x01\x00\x00\x00D\x00\x00\x00\x92\x00\x00\x00y\x00\xff\xff\xff\xfb\x00\x00\x00\x1c\x00d\x00o\x00c\x00k\x00W\x00i\x00d\x00g\x00e\x00t\x00_\x00a\x00f\x00m\x01\x00\x00\x00\xda\x00\x00\x03\x0b\x00\x00\x02\xc8\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\x03\xa1\x00\x00\x00\x04\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x08\xfc\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x04\x00\x00\x00"\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00p\x00t\x00i\x00m\x00i\x00z\x00e\x00r\x01\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x002\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00o\x00b\x00j\x00e\x00c\x00t\x00i\x00v\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x00h\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00t\x00o\x00p\x01\x00\x00\x01G\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00,\x00T\x00o\x00o\x00l\x00B\x00a\x00r\x00_\x00s\x00a\x00m\x00p\x00l\x00e\x00_\x00s\x00c\x00a\x00n\x00n\x00e\x00r\x01\x00\x00\x01\x82\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00')

    _dock_state = 'double'  # possible: single and double

    _image_container = {}
    _cb_container = {}
    _checkbox_container = {}
    _plot_container = {}

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

    # here are the checked meas params stored, a list of strings
    _stat_var_meas_params = StatusVar('stat_var_meas_params', default=[])

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialization of the GUI. """

        self._qafm_logic = self.qafmlogic()

        self.initMainUI()      # initialize the main GUI
        self.default_view()


        self._qafm_logic.sigQAFMScanInitialized.connect(self.adjust_qafm_image)
        self._qafm_logic.sigQAFMLineScanFinished.connect(self._update_qafm_data)
        self._qafm_logic.sigQAFMScanFinished.connect(self.enable_scan_actions)
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

        self.retrieve_status_var()

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


        # initialize the settings stuff
        self.initSettingsUI()

        
        # Initialize iso b parameter

        self._mw.single_isob_freq_DSpinBox.valueChanged.connect(self._set_single_iso_b_freq)
        self._mw.single_isob_gain_DSpinBox.valueChanged.connect(self._set_single_iso_b_gain)

        self._mw.single_isob_freq_DSpinBox.setMinimalStep = 10e3
        self._mw.single_isob_gain_DSpinBox.setMinimalStep = 0.01

        self._qafm_logic.sigIsoBParamsUpdated.connect(self.update_single_iso_b_param)
        self.update_single_iso_b_param()


    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        self.store_status_var()
        self._mw.close()
        self._qm.close()
        self._sd.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()


    def initQuantiUI(self):
    	self._qm = QuantitativeMeasurementWindow()

    def openQuantiMeas(self):
    	self._qm.show()


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

    def initSettingsUI(self):
        """ Initialize and set up the Settings Dialog. """

        self._sd = SettingsDialog()

        self._mw.action_open_settings.triggered.connect(self.show_settings_window)

        self._sd.accepted.connect(self.update_qafm_settings)
        self._sd.rejected.connect(self.keep_former_qafm_settings)
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_qafm_settings)

        self._sd.single_iso_b_operation_CheckBox.stateChanged.connect(self._mw.dockWidget_isob.setVisible)
        self._sd.single_iso_b_operation_CheckBox.stateChanged.connect(self._mw.dockWidget_isob.setEnabled)

        # toggle twice to initiate a state change and come back to the initial one.
        self._sd.single_iso_b_operation_CheckBox.toggle()
        self._sd.single_iso_b_operation_CheckBox.toggle()

        # write the configuration to the settings window of the GUI.
        self.keep_former_qafm_settings()

        # react on setting changes by the logic
        self._qafm_logic.sigSettingsUpdated.connect(self.keep_former_qafm_settings)


    def _set_single_iso_b_freq(self, freq):
        print('val changed:', freq)
        self._qafm_logic.set_single_iso_b_params(freq=freq, gain=None)

    def _set_single_iso_b_gain(self, gain):
        print('val changed:', gain)
        self._qafm_logic.set_single_iso_b_params(freq=None, gain=gain)  


    def update_single_iso_b_param(self):
        """ Update single iso b parameter from the logic """
        
        self._mw.single_isob_freq_DSpinBox.blockSignals(True)
        self._mw.single_isob_gain_DSpinBox.blockSignals(True)

        freq, gain = self._qafm_logic.get_single_iso_b_params()

        if freq is not None:
            self._mw.single_isob_freq_DSpinBox.setValue(freq)

        if gain is not None:
            self._mw.single_isob_gain_DSpinBox.setValue(gain)

        self._mw.single_isob_freq_DSpinBox.blockSignals(False)
        self._mw.single_isob_gain_DSpinBox.blockSignals(False)


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
        # save settings
        sd['root_folder_name'] = self._sd.rootfolder_name_LineEdit.text()
        sd['create_summary_pic'] = self._sd.create_summary_pic_CheckBox.isChecked()
        # optimizer settings
        sd['optimizer_x_range'] = self._sd.optimizer_x_range_DoubleSpinBox.value()
        sd['optimizer_x_res'] = self._sd.optimizer_x_res_SpinBox.value()
        sd['optimizer_y_range'] = self._sd.optimizer_y_range_DoubleSpinBox.value()
        sd['optimizer_y_res'] = self._sd.optimizer_y_res_SpinBox.value()
        sd['optimizer_z_range'] = self._sd.optimizer_z_range_DoubleSpinBox.value()
        sd['optimizer_z_res'] = self._sd.optimizer_z_res_SpinBox.value()
        sd['optimizer_int_time'] = self._sd.optimizer_int_time_DoubleSpinBox.value()
        sd['optimizer_period'] = self._sd.optimizer_period_DoubleSpinBox.value()
        sd['single_iso_b_operation'] = self._sd.single_iso_b_operation_CheckBox.isChecked()
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
        # optimizer settings
        self._sd.optimizer_x_range_DoubleSpinBox.setValue(sd['optimizer_x_range'])
        self._sd.optimizer_x_res_SpinBox.setValue(sd['optimizer_x_res'])
        self._sd.optimizer_y_range_DoubleSpinBox.setValue(sd['optimizer_y_range'])
        self._sd.optimizer_y_res_SpinBox.setValue(sd['optimizer_y_res'])
        self._sd.optimizer_z_range_DoubleSpinBox.setValue(sd['optimizer_z_range'])
        self._sd.optimizer_z_res_SpinBox.setValue(sd['optimizer_z_res'])
        self._sd.optimizer_int_time_DoubleSpinBox.setValue(sd['optimizer_int_time'])
        self._sd.optimizer_period_DoubleSpinBox.setValue(sd['optimizer_period'])    

        self._sd.single_iso_b_operation_CheckBox.setChecked(sd['single_iso_b_operation'])


    def show_settings_window(self):
        """ Show and open the settings window. """
        self._sd.show()

    def retrieve_status_var(self):
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


    def store_status_var(self):

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

    def get_number_matrices(self):

        data_dict = {}
        data_dict.update(self._qafm_logic.get_qafm_data())
        data_dict.update(self._qafm_logic.get_obj_data())
        data_dict.update(self._qafm_logic.get_opti_data())

        return data_dict

    def _create_colorbar(self, colormap, name):

        self._cb_container[name] = ColorBar(colormap.cmap_normed, width=100, cb_min=0, cb_max=100)

        return self._cb_container

    def _create_image_item(self, name, data_matrix):

        self._image_container[name] = ScanImageItem(image=data_matrix, axisOrder='row-major')
        return self._image_container

    def _create_plot_item(self, name, x_axis, y_axis):

        self._plot_container[name] = pg.PlotDataItem(x=x_axis, y=y_axis,
                                                     pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine),
                                                     symbol='o',
                                                     symbolPen=palette.c1,
                                                     symbolBrush=palette.c1,
                                                     symbolSize=7
                                                    )

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
        

    def _create_dockwidgets(self):

        self._dock_state = ''

        ref_last_dockwidget = None
        is_first = True
        self._mw.dockWidgetContainer = []
        self._mw.dockWidgetContentContainer = []

        self.my_colors = ColorScaleInferno()


        data_dict = self.get_number_matrices()

        for obj_name in data_dict:

            if ('fw' in obj_name) or ('bw' in obj_name):

                dockwidget = QtWidgets.QDockWidget(self._mw)
                self._mw.dockWidgetContainer.append(dockwidget)

                dockwidgetContent = QtWidgets.QWidget(self._mw)
                self._mw.dockWidgetContentContainer.append(dockwidgetContent)

                self._create_internal_widgets(dockwidget, dockwidgetContent)
                dockwidget.setWidget(dockwidgetContent)

                dockwidget.setWindowTitle(obj_name)
                dockwidget.setObjectName(obj_name)

                # set size policy
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

                self._create_image_item(obj_name, data_dict[obj_name]['data'])
                dockwidget.graphicsView_xy.addItem(self._image_container[obj_name])
                self._image_container[obj_name].setLookupTable(self.my_colors.lut)

                self._create_colorbar(self.my_colors, obj_name)

                dockwidget.graphicsView_cb.addItem(self._cb_container[obj_name])
                dockwidget.graphicsView_cb.hideAxis('bottom')

                data_name = data_dict[obj_name]['nice_name']
                si_units = data_dict[obj_name]['si_units']

                dockwidget.graphicsView_cb.setLabel('left', data_name, units=si_units)
                dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)

                ref_last_dockwidget = dockwidget

        # for entry in data_bw:
        #
        #     obj_name = entry + '_bw'
        #
        #     dockwidget = QtWidgets.QDockWidget(self._mw)
        #     self._mw.dockWidgetContainer.append(dockwidget)
        #
        #     dockwidgetContent = QtWidgets.QWidget(self._mw)
        #     self._mw.dockWidgetContentContainer.append(dockwidgetContent)
        #
        #     self._create_internal_widgets(dockwidget, dockwidgetContent)
        #     dockwidget.setWidget(dockwidgetContent)
        #
        #     dockwidget.setWindowTitle(obj_name)
        #     dockwidget.setObjectName(obj_name)
        #
        #     # set size policy
        #     sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
        #                                        QtWidgets.QSizePolicy.Preferred)
        #     sizePolicy.setHorizontalStretch(0)
        #     sizePolicy.setVerticalStretch(0)
        #     sizePolicy.setHeightForWidth(dockwidget.sizePolicy().hasHeightForWidth())
        #     dockwidget.setSizePolicy(sizePolicy)
        #
        #     if is_first:
        #         self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), dockwidget)
        #         # QtCore.Qt.Orientation(1): horizontal orientation
        #         self._mw.splitDockWidget(dockwidget, self._mw.dockWidget_afm,
        #                                  QtCore.Qt.Orientation(1))
        #         is_first = False
        #     else:
        #         self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(4), dockwidget)
        #         self._mw.tabifyDockWidget(ref_last_dockwidget, dockwidget)
        #
        #     self._create_image_item(obj_name, data_bw[entry]['data'])
        #     dockwidget.graphicsView_xy.addItem(self._image_container[obj_name])
        #     self._image_container[obj_name].setLookupTable(self.my_colors.lut)
        #
        #     cb_name = obj_name
        #     self._create_colorbar(self.my_colors, cb_name)
        #
        #     dockwidget.graphicsView_cb.addItem(self._cb_container[cb_name])
        #     dockwidget.graphicsView_cb.hideAxis('bottom')
        #
        #     data_name = data_fw[entry]['nice_name']
        #     si_units = data_fw[entry]['si_units']
        #
        #     dockwidget.graphicsView_cb.setLabel('left', data_name, units=si_units)
        #     dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)
        #
        #
        #     ref_last_dockwidget = dockwidget


        for entry in data_dict:

            if 'obj' in entry:

                obj_name = entry
                axis0 = obj_name[-2].upper()
                axis1 = obj_name[-1].upper()

                dockwidget = QtWidgets.QDockWidget(self._mw)
                self._mw.dockWidgetContainer.append(dockwidget)


                dockwidgetContent = QtWidgets.QWidget(self._mw)
                self._mw.dockWidgetContentContainer.append(dockwidgetContent)

                self._create_internal_widgets(dockwidget, dockwidgetContent)
                dockwidget.setWidget(dockwidgetContent)

                dockwidget.graphicsView_xy.setLabel('bottom', f'{axis0} position', units='m')
                dockwidget.graphicsView_xy.setLabel('left', f'{axis1} position', units='m')

                dockwidget.setWindowTitle(obj_name)
                dockwidget.setObjectName(obj_name)

                # set size policy
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

                self._create_image_item(obj_name, data_dict[entry]['data'])
                dockwidget.graphicsView_xy.addItem(self._image_container[obj_name])
                self._image_container[obj_name].setLookupTable(self.my_colors.lut)

                cb_name = obj_name
                self._create_colorbar(self.my_colors, cb_name)

                dockwidget.graphicsView_cb.addItem(self._cb_container[cb_name])
                dockwidget.graphicsView_cb.hideAxis('bottom')

                data_name = data_dict[entry]['nice_name']
                si_units = data_dict[entry]['si_units']

                dockwidget.graphicsView_cb.setLabel('left', data_name, units=si_units)
                dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)

                #FIXME: This initialization has to happen somewhere
                # dockwidget.doubleSpinBox_cb_min.setSuffix(si_units)
                # dockwidget.doubleSpinBox_cb_min.setMinimalStep(data_obj[entry]['typ_val']/1000)

                # dockwidget.doubleSpinBox_cb_max.setSuffix(si_units)
                # dockwidget.doubleSpinBox_cb_max.setValue(data_obj[entry]['typ_val'])
                # dockwidget.doubleSpinBox_cb_max.setMinimalStep(data_obj[entry]['typ_val']/1000)

                ref_last_dockwidget = dockwidget


        if 'opti_xy' in data_dict:
            obj_name = 'opti_xy'

            dockwidget = QtWidgets.QDockWidget(self._mw)
            self._mw.dockWidgetContainer.append(dockwidget)

            dockwidgetContent = QtWidgets.QWidget(self._mw)
            self._mw.dockWidgetContentContainer.append(dockwidgetContent)

            self._create_internal_widgets(dockwidget, dockwidgetContent)
            dockwidget.setWidget(dockwidgetContent)

            dockwidget.setWindowTitle(obj_name)
            dockwidget.setObjectName(obj_name)

            # set size policy
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

            self._create_image_item(obj_name, data_dict[obj_name]['data'])
            dockwidget.graphicsView_xy.addItem(self._image_container[obj_name])
            self._image_container[obj_name].setLookupTable(self.my_colors.lut)

            cb_name = obj_name 
            self._create_colorbar(self.my_colors, cb_name)

            dockwidget.graphicsView_cb.addItem(self._cb_container[cb_name])
            dockwidget.graphicsView_cb.hideAxis('bottom')

            data_name = data_dict[obj_name]['nice_name']
            si_units = data_dict[obj_name]['si_units']

            dockwidget.graphicsView_cb.setLabel('left', data_name, units=si_units)
            dockwidget.graphicsView_cb.setMouseEnabled(x=False, y=False)

            ref_last_dockwidget = dockwidget


        if 'opti_z' in data_dict:
            obj_name = 'opti_z'

            dockwidget = QtWidgets.QDockWidget(self._mw)
            self._mw.dockWidgetContainer.append(dockwidget)

            dockwidgetContent = QtWidgets.QWidget(self._mw)
            self._mw.dockWidgetContentContainer.append(dockwidgetContent)

            self._create_internal_line_widgets(dockwidget, dockwidgetContent)
            dockwidget.setWidget(dockwidgetContent)

            dockwidget.setWindowTitle(obj_name)
            dockwidget.setObjectName(obj_name)

            # set size policy
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

            self._create_plot_item(obj_name, data_dict[obj_name]['coord0_arr'], 
                                   data_dict[obj_name]['data'])

            dockwidget.graphicsView.addItem(self._plot_container[obj_name])
            ref_last_dockwidget = dockwidget

        self.adjust_qafm_image()
        self.adjust_all_obj_images()
        self.adjust_optimizer_image('opti_xy')

    def _create_internal_line_widgets(self, parent_dock, parent_content):

        #TODO: think about a plain structure for saving the dock widgets
        parent_dock.gridLayout = QtWidgets.QGridLayout(parent_content)

        parent_dock.graphicsView = PlotWidget(parent_content)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, 
                                           QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(parent_dock.graphicsView.sizePolicy().hasHeightForWidth())
        parent_dock.graphicsView.setSizePolicy(sizePolicy)

        parent_dock.graphicsView.setLabel('bottom', 'Z position', units='m')
        parent_dock.graphicsView.setLabel('left', 'Fluorescence', units='c/s') 


        parent_dock.gridLayout.addWidget(parent_dock.graphicsView, 0, 0, 1, 1)

    def _create_internal_widgets(self, parent_dock, parent_content):

        #TODO: think about a plain structure for saving the dock widgets
        parent_dock.gridLayout = QtWidgets.QGridLayout(parent_content)

        parent_dock.radioButton_cb_man = QtWidgets.QRadioButton(parent_content)
        # parent_dock.radioButton_cb_man.setObjectName("radioButton_cb_man")
        parent_dock.radioButton_cb_man.setText('Manual')

        parent_dock.gridLayout.addWidget(parent_dock.radioButton_cb_man, 5, 2, 1, 1)
        parent_dock.doubleSpinBox_cb_max = ScienDSpinBox(parent_content)
        parent_dock.doubleSpinBox_cb_max.setMinimum(-100e9)
        parent_dock.doubleSpinBox_cb_max.setMaximum(100e9)
        # parent_dock.doubleSpinBox_cb_max.setValue(300000)
        # parent_dock.doubleSpinBox_cb_max.setSuffix('c/s')
        # parent_dock.doubleSpinBox_cb_max.setMinimalStep(1)

        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(parent_dock.doubleSpinBox_cb_max.sizePolicy().hasHeightForWidth())
        parent_dock.doubleSpinBox_cb_max.setSizePolicy(sizePolicy)
        parent_dock.doubleSpinBox_cb_max.setMaximumSize(QtCore.QSize(100, 16777215))
        # parent_dock.doubleSpinBox_cb_max.setObjectName("doubleSpinBox_cb_max")
        parent_dock.gridLayout.addWidget(parent_dock.doubleSpinBox_cb_max, 0, 2, 1, 1)
        parent_dock.graphicsView_cb = ScanPlotWidget(parent_content)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, 
                                           QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(parent_dock.graphicsView_cb.sizePolicy().hasHeightForWidth())
        parent_dock.graphicsView_cb.setSizePolicy(sizePolicy)
        parent_dock.graphicsView_cb.setMaximumSize(QtCore.QSize(80, 16777215))
        # parent_dock.graphicsView_cb.setObjectName("graphicsView_2")
        parent_dock.gridLayout.addWidget(parent_dock.graphicsView_cb, 2, 2, 1, 1)
        parent_dock.doubleSpinBox_cb_min = ScienDSpinBox(parent_content)
        parent_dock.doubleSpinBox_cb_min.setMinimum(-100e9)
        parent_dock.doubleSpinBox_cb_min.setMaximum(100e9)
        # parent_dock.doubleSpinBox_cb_min.setValue(0.0)
        # parent_dock.doubleSpinBox_cb_min.setSuffix('c/s')
        # parent_dock.doubleSpinBox_cb_min.setMinimalStep(1)
        # parent_dock.doubleSpinBox_cb_min.setObjectName("doubleSpinBox_cb_min")
        parent_dock.gridLayout.addWidget(parent_dock.doubleSpinBox_cb_min, 4, 2, 1, 1)

        parent_dock.doubleSpinBox_per_min = ScienDSpinBox(parent_content)
        parent_dock.doubleSpinBox_per_min.setMinimum(0)
        parent_dock.doubleSpinBox_per_min.setMaximum(100)
        parent_dock.doubleSpinBox_per_min.setValue(0.0)
        parent_dock.doubleSpinBox_per_min.setSuffix('%')
        parent_dock.doubleSpinBox_per_min.setMinimalStep(0.05)
        # parent_dock.doubleSpinBox_per_min.setObjectName("doubleSpinBox_per_min")
        parent_dock.gridLayout.addWidget(parent_dock.doubleSpinBox_per_min, 3, 2, 1, 1)

        parent_dock.doubleSpinBox_per_max = ScienDSpinBox(parent_content)
        parent_dock.doubleSpinBox_per_max.setMinimum(0)
        parent_dock.doubleSpinBox_per_max.setMaximum(100)
        parent_dock.doubleSpinBox_per_max.setValue(100.0)
        parent_dock.doubleSpinBox_per_max.setSuffix('%')
        # parent_dock.doubleSpinBox_per_max.setMinimalStep(0.05)
        # parent_dock.doubleSpinBox_per_max.setObjectName("doubleSpinBox_per_max")
        parent_dock.gridLayout.addWidget(parent_dock.doubleSpinBox_per_max, 1, 2, 1, 1)
        
        parent_dock.radioButton_cb_per = QtWidgets.QRadioButton(parent_content)
        # parent_dock.radioButton_cb_per.setObjectName("radioButton_cb_per")
        parent_dock.radioButton_cb_per.setText('Percentiles')
        parent_dock.radioButton_cb_per.setChecked(True)

        parent_dock.gridLayout.addWidget(parent_dock.radioButton_cb_per, 6, 2, 1, 1)
        parent_dock.graphicsView_xy = ScanPlotWidget(parent_content)

        #FIXME: this can be transferred to self._create_dockwidgets for a more general purpose
        parent_dock.graphicsView_xy.setLabel('bottom', 'X position', units='m')
        parent_dock.graphicsView_xy.setLabel('left', 'Y position', units='m') 

        # parent_dock.graphicsView_xy.setObjectName("graphicsView_xy")
        parent_dock.gridLayout.addWidget(parent_dock.graphicsView_xy, 0, 0, 7, 1)

        def cb_per_update(value):
            parent_dock.radioButton_cb_per.setChecked(True)
            self.sigColorBarChanged.emit(parent_dock)

        def cb_man_update(value):
            parent_dock.radioButton_cb_man.setChecked(True)
            self.sigColorBarChanged.emit(parent_dock)

        parent_dock.cb_per_update = cb_per_update
        parent_dock.doubleSpinBox_per_min.valueChanged.connect(parent_dock.cb_per_update)
        parent_dock.doubleSpinBox_per_max.valueChanged.connect(parent_dock.cb_per_update)
        
        parent_dock.cb_man_update = cb_man_update
        parent_dock.doubleSpinBox_cb_min.valueChanged.connect(parent_dock.cb_man_update)
        parent_dock.doubleSpinBox_cb_max.valueChanged.connect(parent_dock.cb_man_update)


    def _create_meas_params(self):

        meas_params_units = self._qafm_logic.get_afm_meas_params()
        meas_params = list(meas_params_units)

        for index, entry in enumerate(meas_params):

            checkbox = CustomCheckBox(self._mw.scan_param_groupBox)
            checkbox.setObjectName(entry)
            checkbox.setText(entry)
            checkbox.valueChanged_custom.connect(self.update_shown_dockwidget)
            checkbox.setChecked(True)
            checkbox.setChecked(False)

            self._mw.gridLayout_scan_params.addWidget(checkbox, index, 0, 1, 1)
            self._checkbox_container[entry] = checkbox

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
        if _save_display_view is None:
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

        if self._dock_state == 'double':
            return

        first_object = True
        ref_last_dockwidget = None
        for entry in self._mw.dockWidgetContainer:
            name = entry.objectName() 
            if 'bw' in name:
                if first_object:
                    self._mw.splitDockWidget(self._mw.dockWidget_afm, 
                                             entry,  
                                             QtCore.Qt.Orientation(1))
                    self._mw.splitDockWidget(entry, 
                                             self._mw.dockWidget_afm, 
                                             QtCore.Qt.Orientation(1))
                    first_object = False

                else:
                    self._mw.tabifyDockWidget(ref_last_dockwidget, entry)

            ref_last_dockwidget = entry

        #Creates the optimizer below the optical Widget
        for entry in reversed(self._mw.dockWidgetContainer):
            name = entry.objectName()

            if 'opti_xy' in name:
                self._mw.splitDockWidget(self._mw.dockWidget_objective,
                                         entry,
                                         QtCore.Qt.Orientation(2))

            if 'opti_z' in name:
                self._mw.splitDockWidget(self._mw.dockWidget_objective,
                                         entry,
                                         QtCore.Qt.Orientation(2))

        self._dock_state = 'double'

    def combine_view(self):

        if self._dock_state == 'single':
            return

        ref_last_dockwidget = None

        for entry in reversed(self._mw.dockWidgetContainer):
            if 'fw' in entry.objectName():
                ref_last_dockwidget = entry
                break

        for entry in self._mw.dockWidgetContainer:
            name = entry.objectName() 
            if 'bw' in name:
                self._mw.tabifyDockWidget(ref_last_dockwidget, entry)

            ref_last_dockwidget = entry

        self._dock_state = 'single'


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
        """ 

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

        qafm_data = self._qafm_logic.get_qafm_data()

        # order them in forward scan and backward scan:
        for param_name in qafm_data:
            if 'fw' in param_name:
                dockwidget = self._get_dockwidget(param_name)
                
                cb_range = self._get_scan_cb_range(dockwidget)

                if qafm_data[param_name]['display_range'] is not None:
                    qafm_data[param_name]['display_range'] = cb_range 

                self._image_container[param_name].setImage(image=qafm_data[param_name]['data'],
                                                           levels=(cb_range[0], cb_range[1]))
                self._refresh_scan_colorbar(dockwidget)
                # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
                self._image_container[param_name].getViewBox().updateAutoRange()

        for param_name in qafm_data:
            if 'bw' in param_name:
                dockwidget = self._get_dockwidget(param_name)

                cb_range = self._get_scan_cb_range(dockwidget)

                if qafm_data[param_name]['display_range'] is not None:
                    qafm_data[param_name]['display_range'] = cb_range

                self._image_container[param_name].setImage(image=qafm_data[param_name]['data'],
                                                           levels=(cb_range[0], cb_range[1]))
                self._refresh_scan_colorbar(dockwidget)
                # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
                self._image_container[param_name].getViewBox().updateAutoRange()


    def _update_data_from_dockwidget(self, dockwidget):

        obj_name = dockwidget.objectName()

        #FIXME: Very very ugly, just a temporary solution, needs to be fixed.
        if 'fw' in obj_name:
            data_obj = self._qafm_logic.get_qafm_data()[obj_name]
        elif 'bw' in obj_name:
            data_obj = self._qafm_logic.get_qafm_data()[obj_name]
        elif 'obj' in obj_name:
            data_obj = self._qafm_logic.get_obj_data()[obj_name]
        elif 'opti' in obj_name:
            data_obj = self._qafm_logic.get_opti_data()[obj_name]
        else:
            #just to nothing if nothing matches
            return

        cb_range = self._get_scan_cb_range(dockwidget)

        data = data_obj['data']

        self._image_container[obj_name].setImage(image=data, levels=(cb_range[0], cb_range[1]))
        self._refresh_scan_colorbar(dockwidget)
        # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
        self._image_container[obj_name].getViewBox().updateAutoRange()

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
            dockwidget = self._get_dockwidget(name)

            cb_range = self._get_scan_cb_range(dockwidget)

            if obj_data[name]['display_range'] is not None:
                obj_data[name]['display_range'] = cb_range

            self._image_container[name].setImage(image=obj_data[name]['data'], 
                                                 levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(dockwidget)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[name].getViewBox().updateAutoRange()

    def _update_opti_data(self, obj_name=None):

        opti_data = self._qafm_logic.get_opti_data()

        if obj_name == 'opti_xy':
            dockwidget =  self._get_dockwidget(obj_name)

            cb_range = self._get_scan_cb_range(dockwidget)

            if opti_data[obj_name]['display_range'] is not None:
                opti_data[obj_name]['display_range'] = cb_range

            self._image_container[obj_name].setImage(image=opti_data[obj_name]['data'], 
                                                 levels=(cb_range[0], cb_range[1]))
            self._refresh_scan_colorbar(dockwidget)
            # self._image_container[obj_name].getViewBox().setAspectLocked(lock=True, ratio=1.0)
            self._image_container[obj_name].getViewBox().updateAutoRange() 
        
        elif obj_name == 'opti_z':

            self._plot_container[obj_name].setData(x=opti_data[obj_name]['coord0_arr'], 
                                                   y=opti_data[obj_name]['data'])

            self._plot_container[obj_name].getViewBox().updateAutoRange() 


    def update_target_pos(self):
        x_max, y_max, c_max, z_max, c_max_z = self._qafm_logic._opt_val

        self._mw.obj_target_x_DSpinBox.setValue(x_max)
        self._mw.obj_target_y_DSpinBox.setValue(y_max)
        self._mw.obj_target_z_DSpinBox.setValue(z_max)


    def _get_scan_cb_range(self, dockwidget):
        """ Determines the cb_min and cb_max values for the xy scan image."""
        
        xy_image = self._image_container[dockwidget.objectName()]

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



    def _refresh_scan_colorbar(self, dockwidget):

        cb_range =  self._get_scan_cb_range(dockwidget)
        self._cb_container[dockwidget.objectName()].refresh_colorbar(cb_range[0], cb_range[1])

    def _get_dockwidget(self, objectname):

        for entry in self._mw.dockWidgetContainer:
            if entry.objectName() == objectname:
                return entry

        return None


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
        """ Manages what happens if the xy scan is started. """
        #self.disable_scan_actions()

        self.disable_scan_actions()

        self._mw.actionOptimize_Pos.setEnabled(True)

        x_start = self._mw.afm_x_min_DSpinBox.value()
        x_stop = self._mw.afm_x_max_DSpinBox.value()
        y_start = self._mw.afm_y_min_DSpinBox.value()
        y_stop = self._mw.afm_y_max_DSpinBox.value()
        res_x = self._mw.afm_x_num_SpinBox.value()
        res_y = self._mw.afm_y_num_SpinBox.value()

        meas_params = ['counts']
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


    def update_shown_dockwidget(self, make_visible, name):

        for entry in self._mw.dockWidgetContainer:
            if name in entry.objectName():
                if make_visible:
                    entry.show()
                else:
                    entry.hide()

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



