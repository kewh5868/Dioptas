# Py2DeX - GUI program for fast processing of 2D X-ray data
# Copyright (C) 2014  Clemens Prescher (clemens.prescher@gmail.com)
# GSECARS, University of Chicago
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.


__author__ = 'Clemens Prescher'

import os
from PyQt4 import QtGui, QtCore
import numpy as np
from Data.HelperModule import get_base_name
from copy import copy
import pyqtgraph as pg


class IntegrationPhaseController(object):
    def __init__(self, working_dir, view, calibration_data,
                 spectrum_data, phase_data):
        self.working_dir = working_dir
        self.view = view
        self.calibration_data = calibration_data
        self.spectrum_data = spectrum_data
        self.phase_data = phase_data
        self.phase_lw_items = []
        self.create_signals()

    def create_signals(self):
        self.connect_click_function(self.view.phase_add_btn, self.add_phase)
        self.connect_click_function(self.view.phase_del_btn, self.del_phase)
        self.connect_click_function(self.view.phase_clear_btn, self.clear_phases)

        self.view.phase_pressure_step_txt.editingFinished.connect(self.update_phase_pressure_step)
        self.view.phase_temperature_step_txt.editingFinished.connect(self.update_phase_pressure_step)

        self.view.phase_pressure_sb.valueChanged.connect(self.phase_pressure_sb_changed)
        self.view.phase_temperature_sb.valueChanged.connect(self.phase_temperature_sb_changed)

        self.view.phase_lw.currentItemChanged.connect(self.phase_item_changed)

        self.view.spectrum_view.view_box.sigRangeChangedManually.connect(self.update_intensities_slot)
        self.view.spectrum_view.spectrum_plot.autoBtn.clicked.connect(self.spectrum_auto_btn_clicked)
        self.spectrum_data.subscribe(self.spectrum_data_changed)

    def connect_click_function(self, emitter, function):
        self.view.connect(emitter, QtCore.SIGNAL('clicked()'), function)

    def add_phase(self, filename=None):
        """
        Loads a new phase from jcpds file.
        :param filename: *.jcpds filename. I not set or None it a FileDialog will open.
        :return:
        """
        if filename is None:
            filenames = QtGui.QFileDialog.getOpenFileNames(
                self.view, "Load Phase(s).", self.working_dir['phase'])
            if len(filenames):
                self.working_dir['phase'] = os.path.dirname(str(filenames[0]))
                progress_dialog = QtGui.QProgressDialog("Loading multiple phases.", "Abort Loading", 0, len(filenames),
                                                        self.view)
                progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
                progress_dialog.show()
                QtGui.QApplication.processEvents()
                for ind, filename in enumerate(filenames):
                    filename = str(filename)
                    progress_dialog.setValue(ind)
                    progress_dialog.setLabelText("Loading: " + os.path.basename(filename))
                    QtGui.QApplication.processEvents()
                    self.phase_data.add_phase(filename)
                    self.phase_lw_items.append(
                        self.view.phase_lw.addItem(get_base_name(filename)))
                    if self.view.phase_apply_to_all_cb.isChecked():
                        self.phase_data.phases[-1].compute_d(
                            pressure=np.float(
                                self.view.phase_pressure_sb.value()),
                            temperature=np.float(
                                self.view.phase_temperature_sb.value()))
                    self.phase_data.get_lines_d(-1)
                    self.view.phase_lw.setCurrentRow(
                        len(self.phase_data.phases) - 1)
                    self.add_phase_plot()
                    if progress_dialog.wasCanceled():
                        break
                progress_dialog.close()
                QtGui.QApplication.processEvents()
        else:
            self.phase_data.add_phase(filename)
            self.phase_lw_items.append(
                self.view.phase_lw.addItem(get_base_name(filename)))
            if self.view.phase_apply_to_all_cb.isChecked():
                self.phase_data.phases[-1].compute_d(
                    pressure=np.float(self.view.phase_pressure_sb.value()),
                    temperature=np.float(
                        self.view.phase_temperature_sb.value()))
            self.phase_data.get_lines_d(-1)
            self.view.phase_lw.setCurrentRow(len(self.phase_data.phases) - 1)
            self.add_phase_plot()
            self.working_dir['phase'] = os.path.dirname(str(filename))

    def add_phase_plot(self):
        """
        Adds a phase to the Spectrum view.
        :return:
        """
        axis_range = self.view.spectrum_view.spectrum_plot.viewRange()
        x_range = axis_range[0]
        y_range = axis_range[1]
        positions, intensities, baseline = \
            self.phase_data.rescale_reflections(
                -1, self.spectrum_data.spectrum,
                x_range, y_range,
                self.calibration_data.geometry.wavelength * 1e10,
                self.get_unit())
        self.view.spectrum_view.add_phase(self.phase_data.phases[-1].name,
                                          positions,
                                          intensities,
                                          baseline)

    def del_phase(self):
        """
        Deletes the currently selected Phase
        """
        cur_ind = self.view.phase_lw.currentRow()
        if cur_ind >= 0:
            self.view.phase_lw.takeItem(cur_ind)
            self.phase_data.del_phase(cur_ind)
            self.view.spectrum_view.del_phase(cur_ind)

    def clear_phases(self):
        """
        Delets all phases from the GUI and phase data
        """
        while self.view.phase_lw.count() > 0:
            self.del_phase()

    def update_phase_pressure_step(self):
        value = np.float(self.view.phase_pressure_step_txt.text())
        self.view.phase_pressure_sb.setSingleStep(value)

    def update_phase_temperature_step(self):
        value = np.float(self.view.phase_temperature_step_txt.text())
        self.view.phase_temperature_sb.setSingleStep(value)

    def phase_pressure_sb_changed(self, val):
        """
        Called when pressure spinbox emits a new value. Calculates the appropriate EOS values and updates line
        positions and intensities.
        """
        if self.view.phase_apply_to_all_cb.isChecked():
            for ind in xrange(self.view.phase_lw.count()):
                self.phase_data.set_pressure(ind, np.float(val))
            self.update_intensities()

        else:
            cur_ind = self.view.phase_lw.currentRow()
            self.phase_data.set_pressure(cur_ind, np.float(val))
            self.update_intensity(cur_ind)

    def phase_temperature_sb_changed(self, val):
        """
        Called when temperature spinbox emits a new value. Calculates the appropriate EOS values and updates line
        positions and intensities.
        """
        if self.view.phase_apply_to_all_cb.isChecked():
            for ind in xrange(self.view.phase_lw.count()):
                self.phase_data.set_temperature(ind, np.float(val))
            self.update_intensities()

        else:
            cur_ind = self.view.phase_lw.currentRow()
            self.phase_data.set_temperature(cur_ind, np.float(val))
            self.update_intensity(cur_ind)

    def phase_item_changed(self):
        """
        updates the pressures and temperatures values in the GUI, which are corresponding the the selected phase.
        :return:
        """
        cur_ind = self.view.phase_lw.currentRow()
        pressure = self.phase_data.phases[cur_ind].pressure
        temperature = self.phase_data.phases[cur_ind].temperature

        self.view.phase_pressure_sb.blockSignals(True)
        self.view.phase_temperature_sb.blockSignals(True)
        self.view.phase_pressure_sb.setValue(pressure)
        self.view.phase_temperature_sb.setValue(temperature)
        self.view.phase_pressure_sb.blockSignals(False)
        self.view.phase_temperature_sb.blockSignals(False)

    def update_intensities_slot(self, *args):
        """
        Used as a slot when autoRange of the view is. Tries to prevent a call on autorange while updating intensities of
        phases.
        """
        axis_range = self.view.spectrum_view.spectrum_plot.viewRange()
        auto_range = copy(self.view.spectrum_view.spectrum_plot.vb.state['autoRange'])

        self.view.spectrum_view.spectrum_plot.disableAutoRange()
        self.update_intensities(axis_range)

        if auto_range[0] and auto_range[1]:
            self.view.spectrum_view.spectrum_plot.enableAutoRange()

    def update_intensity(self, ind, axis_range=None):
        """
        Updates the intensities of a specific phase with index ind.
        :param ind: Index of the phase
        :param axis_range: list/tuple of visible x_range and y_range -- ((x_min, x_max), (y_min, y_max))
        """
        if axis_range is None:
            axis_range = self.view.spectrum_view.spectrum_plot.viewRange()
        x_range = axis_range[0]
        y_range = axis_range[1]
        positions, intensities, baseline = \
            self.phase_data.rescale_reflections(
                ind, self.spectrum_data.spectrum,
                x_range, y_range,
                self.calibration_data.geometry.wavelength * 1e10,
                self.get_unit())
        self.view.spectrum_view.update_phase_intensities(
            ind, positions, intensities, baseline)

    def update_intensities(self, axis_range=None):
        """
        Updates all intensities of all phases in the spectrum view. Also checks if phase lines are still visible.
        (within range of spectrum and/or overlays
        :param axis_range: list/tuple of x_range and y_range -- ((x_min, x_max), (y_min, y_max)
        """
        self.view.spectrum_view.view_box.blockSignals(True)
        for ind in xrange(self.view.phase_lw.count()):
            self.update_intensity(ind, axis_range)
        self.view.spectrum_view.view_box.blockSignals(False)
        self.view.spectrum_view.update_phase_line_visibilities()

    def get_unit(self):
        """
        returns the unit currently selected in the GUI
                possible values: 'tth', 'q', 'd'
        """
        if self.view.spec_tth_btn.isChecked():
            return 'tth'
        elif self.view.spec_q_btn.isChecked():
            return 'q'
        elif self.view.spec_d_btn.isChecked():
            return 'd'


    def spectrum_auto_btn_clicked(self):
        """
        Runs self.update_intensities_slot after 50 ms.
        This is needed because the graph scaling is to slow, to call update_intensities immediately after the autoscale-btn
        was clicked
        """
        QtCore.QTimer.singleShot(50, self.update_intensities_slot)

    def spectrum_data_changed(self):
        """
        Function is called after the specturm data has changed.
        """
        QtCore.QTimer.singleShot(10, self.update_intensities_slot)
        self.view.spectrum_view.view_box.sigRangeChanged.connect(self.update_intensities_spectrum_slot)

    def update_intensities_spectrum_slot(self, *args):
        """
        function will be executed after a sigRangeChange event after a spectrum changed. It will disconnect the first
        handler afterwards. This is needed because of some timing issues.
        """
        self.update_intensities()
        try:
            self.view.spectrum_view.view_box.sigRangeChanged.disconnect(self.update_intensities_spectrum_slot)
        except TypeError:
            pass
