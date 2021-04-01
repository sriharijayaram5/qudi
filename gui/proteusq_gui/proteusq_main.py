
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
Some good references

- https://stackoverflow.com/questions/35129102/simple-way-to-display-svg-image-in-a-pyqt-window
Menubar to Qwidget
- http://redino.net/blog/2014/05/qt-qwidget-add-menu-bar/
Custom PushButton style
- http://thesmithfam.org/blog/2009/09/17/qt-stylesheets-button-bar-tutorial/



What needs to be added manually:

- Menubar or Toolbar with Action Items
- Action item (find out how to add them in code)
- Logo in SVG (find out how to scale it properly)

for now, hide all elements, which are not implemented yet

Later
- Add in setting way to set

"""



class ProteusQMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_proteusq_main.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()

class ProteusQGUI(GUIBase):
    """ GUI to control the ProteusQ. """
    
    _modclass = 'ProteusQGUI'
    _modtype = 'gui'

    # main logic module
    scan_logic = Connector(interface='ScanLogic')

    # placeholders for the actual logic objects
    _scanlogic = None


    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialization of the GUI. """

        self.initMainUI()      # initialize the main GUI
        #self.default_view()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def initMainUI(self):
        """ Definition, configuration and initialisation of the confocal GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values.
        """
        self._mw = ProteusQMainWindow()


