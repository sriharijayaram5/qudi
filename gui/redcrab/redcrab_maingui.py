# -*- coding: utf-8 -*-

"""
This file contains the QuDi main GUI for pulsed measurements.

QuDi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

QuDi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with QuDi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
import os
import pyqtgraph as pg
import datetime
import sys
from core.module import Connector, StatusVar
from core.util import units
from gui.colordefs import QudiPalettePale as palette
from gui.fitsettings import FitSettingsDialog
from gui.guibase import GUIBase
from qtpy import QtCore, QtWidgets, uic
from qtwidgets.scientific_spinbox import ScienDSpinBox, ScienSpinBox
from enum import Enum


class RedCRABMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_redcrab_maingui.ui')

        # Load it
        super(RedCRABMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()


class InitiationTab(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_initiate_tab.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class MainSettingsTab(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_main_settings_tab.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class PulsesTab(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_pulse_options_tab.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class PulseOptionModule(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_pulse_option_module.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class ParametersTab(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_parameters_tab.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class ParameterOptionModule(QtWidgets.QWidget):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_parameter_module.ui')
        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)


class RedCRABGui(GUIBase):
    """ This is the main GUI Class for RedCRAB optimization. """

    _modclass = 'RedCRABGui'
    _modtype = 'gui'

    # declare connectors
    redcrabmasterlogic = Connector(interface='RedCRABMasterLogic')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._mw = RedCRABMainWindow()
        self._ms = MainSettingsTab()
        self._pulses = PulsesTab()
        self._parameters = ParametersTab()
        self._initiation = InitiationTab()

        self._mw.tabWidget.addTab(self._initiation, 'Optimization')
        self._mw.tabWidget.addTab(self._ms, 'Main Settings')
        self._mw.tabWidget.addTab(self._pulses, 'Pulses')
        self._mw.tabWidget.addTab(self._parameters, 'Parameters')
        # self._mw.tabWidget.addTab(self._initiation, 'Optimization')

        self._pulse_option_modules = []
        self._parameter_option_modules = []

        # Connect menu bar options
        self._mw.actionSave_2.triggered.connect(self._save_all_variables)
        self._mw.actionCreate_Config_File.triggered.connect(self._create_config)

        # Connect main options tab signals
        self._connect_main_options_signals()

        self._pulses.add_pulse_pushButton.clicked.connect(self.add_pulse)
        self._pulses.del_pulse_pushButton.clicked.connect(self.delete_pulse)

        self._parameters.add_parameter_pushButton.clicked.connect(self.add_parameter)
        self._parameters.del_parameter_pushButton.clicked.connect(self.delete_parameter)

        self._ms.create_config_pushButton.clicked.connect(self._create_config)

        self._initiation.pset_path_pushButton.clicked.connect(self.select_file)
        self._initiation.create_pushButton.clicked.connect(self._create_files)
        self._initiation.run_pushButton.clicked.connect(self._run_optimization)

        # Load variables
        self._load_main_settings_variables()
        self._load_pulses()
        self._load_parameters()
        self._load_initiation()

        self.old_path = os.getcwd()

        self.show()
        return

    def on_deactivate(self):
        """ Deactivate the module
        """
        os.chdir(self.old_path)
        self._save_main_settings_variables()
        self._save_pulses()
        self._save_parameters()
        self._save_initiation()
        self._mw.close()
        return

    def show(self):
        """Make main window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()
        return

    def _connect_main_options_signals(self):
        self._ms.variable_T_checkBox.stateChanged.connect(self.toggle_variable_time_options)
        self._ms.asc_impr_expect_checkBox.stateChanged.connect(self.toggle_asc_impr_expected_options)
        self._ms.asc_close_checkBox.stateChanged.connect(self.toggle_asc_close_options)
        self._ms.specify_re_eval_steps_checkBox.stateChanged.connect(self.toggle_specify_re_eval_steps_options)

    def _connect_pulses_signals(self):
        for pulse_ui in self._pulse_option_modules:
            pulse_ui.reasonable_ampl_var_checkBox.stateChanged.connect(self.toggle_reasonable_ampl_var)
            pulse_ui.num_gaussians_checkBox.stateChanged.connect(self.toggle_num_gaussians)
            pulse_ui.frequency_range_checkBox.stateChanged.connect(self.toggle_frequency_range)
            pulse_ui.frequency_range_f_2_checkBox.stateChanged.connect(self.toggle_frequency_range_2)
            pulse_ui.freq_select_distr_checkBox.stateChanged.connect(self.toggle_freq_select_distr)
            pulse_ui.freq_select_distr_2_checkBox.stateChanged.connect(self.toggle_freq_select_distr_2)
            pulse_ui.analytic_scaling_fnct_avail_checkBox.stateChanged.connect(self.toggle_analytic_scaling_fnct_avail)
            pulse_ui.init_guess_avail_checkBox.stateChanged.connect(self.toggle_init_guess_avail)

            pulse_ui.w_distr_comboBox.currentIndexChanged.connect(self.toggle_custom_freq_distr)
            pulse_ui.w_distr_comboBox_2.currentIndexChanged.connect(self.toggle_custom_freq_distr_2)

    def _connect_parameters_signals(self):
        for parameter_ui in self._parameter_option_modules:
            parameter_ui.init_para_avail_checkBox.stateChanged.connect(self.toggle_para_value)
            parameter_ui.reasonable_para_var_checkBox.stateChanged.connect(self.toggle_para_variation)

    def select_file(self):
        self._initiation.path_lineEdit.setText(QtWidgets.QFileDialog.getExistingDirectory())

    def toggle_variable_time_options(self):
        if self._ms.variable_T_checkBox.isChecked():
            self._ms.TT_min_doubleSpinBox.setEnabled(True)
            self._ms.TT_max_doubleSpinBox.setEnabled(True)
        else:
            self._ms.TT_min_doubleSpinBox.setEnabled(False)
            self._ms.TT_max_doubleSpinBox.setEnabled(False)

    def toggle_asc_impr_expected_options(self):
        if self._ms.asc_impr_expect_checkBox.isChecked():
            self._ms.asc_impr_expect_N_spinBox.setEnabled(True)
        else:
            self._ms.asc_impr_expect_N_spinBox.setEnabled(False)

    def toggle_asc_close_options(self):
        if self._ms.asc_close_checkBox.isChecked():
            self._ms.asc_close_N_spinBox.setEnabled(True)
            self._ms.asc_close_p_spinBox.setEnabled(True)
        else:
            self._ms.asc_close_N_spinBox.setEnabled(False)
            self._ms.asc_close_p_spinBox.setEnabled(False)

    def toggle_specify_re_eval_steps_options(self):
        if self._ms.specify_re_eval_steps_checkBox.isChecked():
            self._ms.specify_re_eval_steps_lineEdit.setEnabled(True)
        else:
            self._ms.specify_re_eval_steps_lineEdit.setEnabled(False)

    def toggle_reasonable_ampl_var(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.reasonable_ampl_var_checkBox.isChecked():
                pulse_ui.ampl_var_doubleSpinBox.setEnabled(True)
            else:
                pulse_ui.ampl_var_doubleSpinBox.setEnabled(False)

    def toggle_num_gaussians(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.num_gaussians_checkBox.isChecked():
                pulse_ui.single_Gaussian_radioButton.setEnabled(True)
                pulse_ui.two_gaussians_radioButton.setEnabled(True)
            else:
                pulse_ui.single_Gaussian_radioButton.setEnabled(False)
                pulse_ui.two_gaussians_radioButton.setEnabled(False)

    def toggle_frequency_range(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.frequency_range_checkBox.isChecked():
                pulse_ui.freq_range_lower_doubleSpinBox.setEnabled(True)
                pulse_ui.freq_range_upper_doubleSpinBox.setEnabled(True)
            else:
                pulse_ui.freq_range_lower_doubleSpinBox.setEnabled(False)
                pulse_ui.freq_range_upper_doubleSpinBox.setEnabled(False)

    def toggle_frequency_range_2(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.frequency_range_f_2_checkBox.isChecked():
                pulse_ui.freq_range_upper_doubleSpinBox_2.setEnabled(True)
                pulse_ui.freq_range_lower_doubleSpinBox_2.setEnabled(True)
            else:
                pulse_ui.freq_range_upper_doubleSpinBox_2.setEnabled(False)
                pulse_ui.freq_range_lower_doubleSpinBox_2.setEnabled(False)

    def toggle_freq_select_distr(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.freq_select_distr_checkBox.isChecked():
                pulse_ui.w_distr_comboBox.setEnabled(True)
                self.toggle_custom_freq_distr()
                # pulse_ui.mean_value_doubleSpinBox.setEnabled(True)
                # pulse_ui.sigma_doubleSpinBox.setEnabled(True)
            else:
                pulse_ui.w_distr_comboBox.setEnabled(False)
                pulse_ui.mean_value_doubleSpinBox.setEnabled(False)
                pulse_ui.sigma_doubleSpinBox.setEnabled(False)
                pulse_ui.freq_distr_function_lineEdit.setEnabled(False)

    def toggle_freq_select_distr_2(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.freq_select_distr_2_checkBox.isChecked():
                pulse_ui.w_distr_comboBox_2.setEnabled(True)
                self.toggle_custom_freq_distr_2()
                # pulse_ui.mean_value_doubleSpinBox_2.setEnabled(True)
                # pulse_ui.sigma_doubleSpinBox_2.setEnabled(True)
            else:
                pulse_ui.w_distr_comboBox_2.setEnabled(False)
                pulse_ui.mean_value_doubleSpinBox_2.setEnabled(False)
                pulse_ui.sigma_doubleSpinBox_2.setEnabled(False)
                pulse_ui.freq_distr_function_lineEdit_2.setEnabled(False)

    def toggle_analytic_scaling_fnct_avail(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.analytic_scaling_fnct_avail_checkBox.isChecked():
                pulse_ui.contr_ampl_time_analytic_scaling_lineEdit.setEnabled(True)
            else:
                pulse_ui.contr_ampl_time_analytic_scaling_lineEdit.setEnabled(False)

    def toggle_init_guess_avail(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.init_guess_avail_checkBox.isChecked():
                pulse_ui.guess_scale_type_comboBox.setEnabled(True)
                pulse_ui.contr_ampl_time_analytic_guess_lineEdit.setEnabled(True)
            else:
                pulse_ui.guess_scale_type_comboBox.setEnabled(False)
                pulse_ui.contr_ampl_time_analytic_guess_lineEdit.setEnabled(False)

    def toggle_custom_freq_distr(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.freq_select_distr_checkBox.isChecked() and pulse_ui.w_distr_comboBox.currentIndex() is 2:
                pulse_ui.freq_distr_function_lineEdit.setEnabled(True)
            else:
                pulse_ui.freq_distr_function_lineEdit.setEnabled(False)

            if pulse_ui.freq_select_distr_checkBox.isChecked() and pulse_ui.w_distr_comboBox.currentIndex() is 1:
                pulse_ui.mean_value_doubleSpinBox.setEnabled(True)
                pulse_ui.sigma_doubleSpinBox.setEnabled(True)
            else:
                pulse_ui.mean_value_doubleSpinBox.setEnabled(False)
                pulse_ui.sigma_doubleSpinBox.setEnabled(False)

    def toggle_custom_freq_distr_2(self):
        for pulse_ui in self._pulse_option_modules:
            if pulse_ui.freq_select_distr_2_checkBox.isChecked() and pulse_ui.w_distr_comboBox_2.currentIndex() is 2:
                pulse_ui.freq_distr_function_lineEdit_2.setEnabled(True)
            else:
                pulse_ui.freq_distr_function_lineEdit_2.setEnabled(False)

            if pulse_ui.freq_select_distr_2_checkBox.isChecked() and pulse_ui.w_distr_comboBox_2.currentIndex() is 1:
                pulse_ui.mean_value_doubleSpinBox_2.setEnabled(True)
                pulse_ui.sigma_doubleSpinBox_2.setEnabled(True)
            else:
                pulse_ui.mean_value_doubleSpinBox_2.setEnabled(False)
                pulse_ui.sigma_doubleSpinBox_2.setEnabled(False)

    def toggle_para_value(self):
        for para_ui in self._parameter_option_modules:
            if para_ui.init_para_avail_checkBox.isChecked():
                para_ui.para_value_doubleSpinBox.setEnabled(True)
            else:
                para_ui.para_value_doubleSpinBox.setEnabled(False)

    def toggle_para_variation(self):
        for para_ui in self._parameter_option_modules:
            if para_ui.reasonable_para_var_checkBox.isChecked():
                para_ui.para_var_doubleSpinBox.setEnabled(True)
            else:
                para_ui.para_var_doubleSpinBox.setEnabled(False)

    def add_pulse(self):
        self.redcrabmasterlogic().new_pulse()
        self._reload_pulses()

    def delete_pulse(self):
        if len(self.redcrabmasterlogic().pulses) is not 0:
            index = self._pulses.tabWidget.currentIndex()
            del self.redcrabmasterlogic().pulses[index]
            del self._pulse_option_modules[index]
            self._reload_pulses()

    def add_parameter(self):
        self.redcrabmasterlogic().new_parameter()
        self._reload_parameters()

    def delete_parameter(self):
        if len(self.redcrabmasterlogic().parameters) is not 0:
            index = self._parameters.tabWidget.currentIndex()
            del self.redcrabmasterlogic().parameters[index]
            del self._parameter_option_modules[index]
            self._reload_parameters()

    def _load_main_settings_variables(self):

        # SpinBoxes
        self._ms.ID_spinBox.setValue(self.redcrabmasterlogic().id_number)
        self._ms.total_time_doubleSpinBox.setValue(self.redcrabmasterlogic().total_time)
        self._ms.number_of_steps_spinBox.setValue(self.redcrabmasterlogic().number_of_time_steps)
        self._ms.form_factor_2_maximization_doubleSpinBox.setValue(self.redcrabmasterlogic().form_factor_2_maximization)
        self._ms.max_num_si_spinBox.setValue(self.redcrabmasterlogic().max_num_SI)
        self._ms.max_funct_eval_si_1_spinBox.setValue(self.redcrabmasterlogic().max_funct_ev_SI_1)
        self._ms.max_funct_eval_si_2_spinBox.setValue(self.redcrabmasterlogic().max_funct_ev_SI_2)
        self._ms.asc_impr_expect_N_spinBox.setValue(self.redcrabmasterlogic().asc_improvement_expected)
        self._ms.asc_close_N_spinBox.setValue(self.redcrabmasterlogic().asc_close_after_rel_dist[0])
        self._ms.asc_close_p_spinBox.setValue(self.redcrabmasterlogic().asc_close_after_rel_dist[1])

        # CheckBoxes
        self._ms.std_avail_checkBox.setChecked(self.redcrabmasterlogic().std_available)
        self._ms.guess_pulse_avail_checkBox.setChecked(self.redcrabmasterlogic().guess_pulses_available)
        self._ms.is_pure_para_opti_checkBox.setChecked(self.redcrabmasterlogic().is_pure_para_opti)
        self._ms.individual_output_checkBox.setChecked(self.redcrabmasterlogic().individual_output)
        self._ms.variable_T_checkBox.setChecked(self.redcrabmasterlogic().flag_variable_T)
        self._ms.asc_impr_expect_checkBox.setChecked(self.redcrabmasterlogic().flag_asc_improvement_expected)
        self._ms.asc_close_checkBox.setChecked(self.redcrabmasterlogic().flag_asc_close)
        self._ms.specify_re_eval_steps_checkBox.setChecked(self.redcrabmasterlogic().flag_specify_re_eval_steps)

        # LineEdit
        self._ms.specify_re_eval_steps_lineEdit.setText(str(self.redcrabmasterlogic().re_eval_steps).strip('[]'))

    def _save_main_settings_variables(self):

        # SpinBoxes
        self.redcrabmasterlogic().id_number = self._ms.ID_spinBox.value()
        self.redcrabmasterlogic().total_time = self._ms.total_time_doubleSpinBox.value()
        self.redcrabmasterlogic().number_of_time_steps = self._ms.number_of_steps_spinBox.value()
        if abs(self.redcrabmasterlogic().form_factor_2_maximization - 0.0) < 1e-3:
            self.redcrabmasterlogic().form_factor_2_maximization = 1.0
            self._ms.form_factor_2_maximization_doubleSpinBox.setValue(
                self.redcrabmasterlogic().form_factor_2_maximization)
            self.log.error('Scaling factor for cost function cannot be 0\nValue set to 1!')
        else:
            self.redcrabmasterlogic().form_factor_2_maximization \
                = self._ms.form_factor_2_maximization_doubleSpinBox.value()
        self.redcrabmasterlogic().max_num_SI = self._ms.max_num_si_spinBox.value()
        self.redcrabmasterlogic().max_funct_ev_SI_1 = self._ms.max_funct_eval_si_1_spinBox.value()
        self.redcrabmasterlogic().max_funct_ev_SI_2 = self._ms.max_funct_eval_si_2_spinBox.value()
        self.redcrabmasterlogic().asc_improvement_expected = self._ms.asc_impr_expect_N_spinBox.value()
        self.redcrabmasterlogic().asc_close_after_rel_dist[0] = self._ms.asc_close_N_spinBox.value()
        self.redcrabmasterlogic().asc_close_after_rel_dist[1] = self._ms.asc_close_p_spinBox.value()

        # CheckBoxes
        self.redcrabmasterlogic().std_available = self._ms.std_avail_checkBox.isChecked()
        self.redcrabmasterlogic().guess_pulses_available = self._ms.guess_pulse_avail_checkBox.isChecked()
        self.redcrabmasterlogic().is_pure_para_opti = self._ms.is_pure_para_opti_checkBox.isChecked()
        self.redcrabmasterlogic().individual_output = self._ms.individual_output_checkBox.isChecked()
        self.redcrabmasterlogic().flag_variable_T = self._ms.variable_T_checkBox.isChecked()
        self.redcrabmasterlogic().flag_asc_improvement_expected = self._ms.asc_impr_expect_checkBox.isChecked()
        self.redcrabmasterlogic().flag_asc_close = self._ms.asc_close_checkBox.isChecked()
        self.redcrabmasterlogic().flag_specify_re_eval_steps = self._ms.specify_re_eval_steps_checkBox.isChecked()

        # LineEdit
        l = self._ms.specify_re_eval_steps_lineEdit.text().split(', ')
        l2 = [float(i) for i in l]
        self.redcrabmasterlogic().re_eval_steps = l2

    def _load_pulses(self):
        self._pulses.tabWidget.clear()
        self._pulse_option_modules = []
        basis_choice_dict = {'fourier': 0, 'tschebyschow': 1, 'gaussian': 2}
        w_distr_dict = {'1': 0, '2': 1, 'acustom': 2}
        guess_scale_type_dict = {'abs': 0, 'rel': 1, 'multiply': 2}
        for pulse_logic in self.redcrabmasterlogic().pulses:
            pulse_ui = PulseOptionModule()
            self._pulse_option_modules.append(pulse_ui)
            self._pulses.tabWidget.addTab(pulse_ui, pulse_logic.pulsename)
            self._connect_pulses_signals()

            # CheckBoxes
            pulse_ui.reasonable_ampl_var_checkBox.setChecked(pulse_logic.flag_reasonable_ampl_var)
            pulse_ui.num_gaussians_checkBox.setChecked(pulse_logic.flag_num_gaussians)
            pulse_ui.select_basis_f_2_checkBox.setChecked(pulse_logic.flag_select_basis_f_2)
            pulse_ui.frequency_range_checkBox.setChecked(pulse_logic.flag_frequency_range)
            pulse_ui.frequency_range_f_2_checkBox.setChecked(pulse_logic.flag_frequency_range_2)
            pulse_ui.freq_select_distr_checkBox.setChecked(pulse_logic.flag_freq_select_distr)
            pulse_ui.freq_select_distr_2_checkBox.setChecked(pulse_logic.flag_freq_select_distr_2)
            pulse_ui.analytic_scaling_fnct_avail_checkBox.setChecked(pulse_logic.flag_analytic_scaling_fnct_avail)
            pulse_ui.init_guess_avail_checkBox.setChecked(pulse_logic.flag_init_guess_avail)

            # SpinBoxes
            pulse_ui.amp_limit_low_doubleSpinBox.setValue(pulse_logic.amp_limit_low)
            pulse_ui.amp_limit_high_doubleSpinBox.setValue(pulse_logic.amp_limit_high)
            pulse_ui.ampl_var_doubleSpinBox.setValue(pulse_logic.ampl_var)
            pulse_ui.freq_range_lower_doubleSpinBox.setValue(pulse_logic.freq_range_lower)
            pulse_ui.freq_range_upper_doubleSpinBox.setValue(pulse_logic.freq_range_upper)
            pulse_ui.freq_range_lower_doubleSpinBox_2.setValue(pulse_logic.freq_range_lower_2)
            pulse_ui.freq_range_upper_doubleSpinBox_2.setValue(pulse_logic.freq_range_upper_2)
            pulse_ui.mean_value_doubleSpinBox.setValue(pulse_logic.w_distr_mean)
            pulse_ui.sigma_doubleSpinBox.setValue(pulse_logic.w_distr_sigma)
            pulse_ui.mean_value_doubleSpinBox_2.setValue(pulse_logic.w_distr_mean_2)
            pulse_ui.sigma_doubleSpinBox_2.setValue(pulse_logic.w_distr_sigma_2)

            # LineEdits
            pulse_ui.pulsename_lineEdit.setText(pulse_logic.pulsename)
            pulse_ui.pulsename_lineEdit.editingFinished.connect(self._reload_pulses)
            pulse_ui.freq_distr_function_lineEdit.setText(pulse_logic.function)
            pulse_ui.freq_distr_function_lineEdit_2.setText(pulse_logic.function_2)
            pulse_ui.contr_ampl_time_analytic_scaling_lineEdit.setText(pulse_logic.contr_ampl_time_analytic)
            pulse_ui.contr_ampl_time_analytic_guess_lineEdit.setText(pulse_logic.input_contr_ampl_time_analytic)

            # ComboBoxes
            pulse_ui.basis_choice_comboBox.setCurrentIndex(basis_choice_dict[pulse_logic.basis_choice])
            pulse_ui.w_distr_comboBox.setCurrentIndex(w_distr_dict[str(pulse_logic.w_distr[0])])
            pulse_ui.w_distr_comboBox_2.setCurrentIndex(w_distr_dict[str(pulse_logic.w_distr_2[0])])
            pulse_ui.guess_scale_type_comboBox.setCurrentIndex(guess_scale_type_dict[pulse_logic.guess_scale_type])

            # Radio Buttons
            if pulse_logic.num_gauss is 2:
                pulse_ui.two_gaussians_radioButton.setChecked(True)
            else:
                pulse_ui.single_Gaussian_radioButton.setChecked(True)

    def _save_pulses(self):
        basis_choice_dict = {'fourier': 0, 'tschebyschow': 1, 'gaussian': 2}
        w_distr_dict = {'1': 0, '2': 1, 'acustom': 2}
        guess_scale_type_dict = {'abs': 0, 'rel': 1, 'multiply': 2}
        for i in range(len(self._pulse_option_modules)):
            pulse_ui = self._pulse_option_modules[i]
            pulse_logic = self.redcrabmasterlogic().pulses[i]

            # CheckBoxes
            pulse_logic.flag_reasonable_ampl_var = pulse_ui.reasonable_ampl_var_checkBox.isChecked()

            pulse_logic.flag_num_gaussians = pulse_ui.num_gaussians_checkBox.isChecked()
            pulse_logic.flag_select_basis_f_2 = pulse_ui.select_basis_f_2_checkBox.isChecked()
            pulse_logic.flag_frequency_range = pulse_ui.frequency_range_checkBox.isChecked()
            pulse_logic.flag_frequency_range_2 = pulse_ui.frequency_range_f_2_checkBox.isChecked()
            pulse_logic.flag_freq_select_distr = pulse_ui.freq_select_distr_checkBox.isChecked()
            pulse_logic.flag_freq_select_distr_2 = pulse_ui.freq_select_distr_2_checkBox.isChecked()
            pulse_logic.flag_analytic_scaling_fnct_avail = pulse_ui.analytic_scaling_fnct_avail_checkBox.isChecked()
            pulse_logic.flag_init_guess_avail = pulse_ui.init_guess_avail_checkBox.isChecked()
            pulse_logic.flag_analytic_guess_input = pulse_ui.init_guess_avail_checkBox.isChecked()

            # SpinBoxes
            pulse_logic.amp_limit_low = pulse_ui.amp_limit_low_doubleSpinBox.value()
            pulse_logic.amp_limit_high = pulse_ui.amp_limit_high_doubleSpinBox.value()
            pulse_logic.ampl_var = pulse_ui.ampl_var_doubleSpinBox.value()
            pulse_logic.freq_range_lower = pulse_ui.freq_range_lower_doubleSpinBox.value()
            pulse_logic.freq_range_upper = pulse_ui.freq_range_upper_doubleSpinBox.value()
            pulse_logic.freq_range_lower_2 = pulse_ui.freq_range_upper_doubleSpinBox_2.value()
            pulse_logic.freq_range_upper_2 = pulse_ui.freq_range_lower_doubleSpinBox_2.value()
            pulse_logic.w_distr_mean = pulse_ui.mean_value_doubleSpinBox.value()
            pulse_logic.w_distr_sigma = pulse_ui.sigma_doubleSpinBox.value()
            pulse_logic.w_distr_mean_2 = pulse_ui.mean_value_doubleSpinBox_2.value()
            pulse_logic.w_distr_sigma_2 = pulse_ui.sigma_doubleSpinBox_2.value()

            # LineEdits
            pulse_logic.pulsename = pulse_ui.pulsename_lineEdit.text()
            pulse_logic.function = pulse_ui.freq_distr_function_lineEdit.text()
            pulse_logic.function_2 = pulse_ui.freq_distr_function_lineEdit_2.text()
            pulse_logic.contr_ampl_time_analytic = pulse_ui.contr_ampl_time_analytic_scaling_lineEdit.text()
            pulse_logic.input_contr_ampl_time_analytic = pulse_ui.contr_ampl_time_analytic_guess_lineEdit.text()

            # ComboBoxes
            pulse_logic.basis_choice = list(basis_choice_dict.keys())[list(basis_choice_dict.values()).index(
                pulse_ui.basis_choice_comboBox.currentIndex())]
            pulse_logic.w_distr = list(w_distr_dict.keys())[list(w_distr_dict.values()).index(
                pulse_ui.w_distr_comboBox.currentIndex())]
            pulse_logic.w_distr_2 = list(w_distr_dict.keys())[list(w_distr_dict.values()).index(
                pulse_ui.w_distr_comboBox_2.currentIndex())]
            pulse_logic.guess_scale_type = list(guess_scale_type_dict.keys()
                                                )[list(guess_scale_type_dict.values()
                                                       ).index(pulse_ui.guess_scale_type_comboBox.currentIndex())]

            # Radio Buttons
            if pulse_ui.two_gaussians_radioButton.isChecked():
                pulse_logic.num_gauss = 2
            else:
                pulse_logic.num_gauss = 1

            # else
            pulse_logic.pulsenumber = i + 1

    def _reload_pulses(self):
        self._save_pulses()
        self._load_pulses()

    def _load_parameters(self):
        self._parameters.tabWidget.clear()
        self._parameter_option_modules = []
        for parameter_logic in self.redcrabmasterlogic().parameters:
            parameter_ui = ParameterOptionModule()
            self._parameter_option_modules.append(parameter_ui)
            self._parameters.tabWidget.addTab(parameter_ui, parameter_logic.para_name)
            self._connect_parameters_signals()

            # CheckBoxes
            parameter_ui.init_para_avail_checkBox.setChecked(parameter_logic.flag_init_para_available)
            parameter_ui.reasonable_para_var_checkBox.setChecked(parameter_logic.flag_reasonable_para_variation)

            # SpinBoxes
            parameter_ui.para_limit_lower_doubleSpinBox.setValue(parameter_logic.para_limit_lower)
            parameter_ui.para_limit_upper_doubleSpinBox.setValue(parameter_logic.para_limit_upper)
            parameter_ui.para_value_doubleSpinBox.setValue(parameter_logic.para_value)
            parameter_ui.para_var_doubleSpinBox.setValue(parameter_logic.para_variation)

            # LineEdits
            parameter_ui.para_name_lineEdit.setText(parameter_logic.para_name)
            parameter_ui.para_name_lineEdit.editingFinished.connect(self._reload_parameters)

    def _save_parameters(self):
        for i in range(len(self._parameter_option_modules)):
            parameter_ui = self._parameter_option_modules[i]
            parameter_logic = self.redcrabmasterlogic().parameters[i]

            # CheckBoxes
            parameter_logic.flag_init_para_available = parameter_ui.init_para_avail_checkBox.isChecked()
            parameter_logic.flag_reasonable_para_variation = parameter_ui.reasonable_para_var_checkBox.isChecked()

            # SpinBoxes
            parameter_logic.para_limit_lower = parameter_ui.para_limit_lower_doubleSpinBox.value()
            parameter_logic.para_limit_upper = parameter_ui.para_limit_upper_doubleSpinBox.value()
            parameter_logic.para_value = parameter_ui.para_value_doubleSpinBox.value()
            parameter_logic.para_variation = parameter_ui.para_var_doubleSpinBox.value()

            # LineEdits
            parameter_logic.para_name = parameter_ui.para_name_lineEdit.text()

            # else
            parameter_logic.para_number = i + 1
        # print(len(self.redcrabmasterlogic().parameters))

    def _load_initiation(self):

        # LineEdit
        self._initiation.path_lineEdit.setText(self.redcrabmasterlogic().file_path)
        self._initiation.module_lineEdit.setText(self.redcrabmasterlogic().file_name)

    def _save_initiation(self):

        # LineEdit
        self.redcrabmasterlogic().file_path = self._initiation.path_lineEdit.text()
        self.redcrabmasterlogic().file_name = self._initiation.module_lineEdit.text()

    def _reload_parameters(self):
        self._save_parameters()
        self._load_parameters()

    def _save_all_variables(self):
        self._save_main_settings_variables()
        self._save_pulses()
        self._save_parameters()

    def _create_files(self):
        self._save_main_settings_variables()
        self._save_pulses()
        self._save_parameters()
        self.redcrabmasterlogic().create_config(path='RedCRAB/Config/RedCRAB_config/')
        self._save_initiation()
        self.redcrabmasterlogic().create_chopped()

    def _create_config(self):
        self._save_main_settings_variables()
        self._save_pulses()
        self._save_parameters()
        self.redcrabmasterlogic().create_config()

    def _create_chopped(self):
        self._save_initiation()
        self.redcrabmasterlogic().create_chopped()

    def _run_optimization(self):
        from shutil import copyfile, rmtree
        self._create_files()
        self._create_chopped()
        # copyfile('RedCRAB/Cfg_5.txt', 'RedCRAB/Config/RedCRAB_config/Cfg_5.txt')

        try:
            # adds the bin path to the search path for modules
            sys.path.append(os.path.join(os.getcwd(), "RedCRAB/bin"))
            # changes working directory
            os.chdir("./RedCRAB/bin")

            if os.path.isdir('tmp'):
                print('tmp folder removed')
                rmtree('tmp')

            # calls redcrab code (slightly messy in python 3)
            with open("redcrab.py", encoding="utf-8") as f:
                code = compile(f.read(), "redcrab.py", 'exec')
                exec(code, globals())

            os.chdir(self.old_path)

            self.log.info('Optimization finished')

            # self.redcrabmasterlogic().show_end_message()




            # print('Nothing to do yet')
            # # adds the bin path to the search path for modules
            # sys.path.append(os.path.join(os.getcwd(), "RedCRAB/bin"))
            # # changes working directory
            # os.chdir("./RedCRAB/bin")
            #
            # # calls redcrab code (slightly messy in python 3)
            # with open("redcrab.py", encoding="utf-8") as f:
            #     code = compile(f.read(), "redcrab.py", 'exec')
            #     exec(code, globals())

            # subprocess.call('source activate qudi', shell=True)
            # subprocess.call('source activate qudi && python RedCRAB/RedCRAB.py', shell=True)
            # subprocess.call('python3 RedCRAB/RedCRAB.py', shell=True)
            # subprocess.Popen(['python', 'RedCRAB/RedCRAB.py'], shell=True)
            # os.system("start cmd")
            # subprocess.Popen(args=["gnome-terminal", "--command=python RedCRAB/RedCRAB.py"])
            # subprocess.call('cd RedCRAB && source activate qudi && python RedCRAB/RedCRAB.py', shell=True)
            # subprocess.call('bash -c "source activate qudi"', shell=True)
        except:
            os.chdir(self.old_path)
            self.log.error('Optimization could not be started!')


