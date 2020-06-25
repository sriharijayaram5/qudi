# -*- coding: utf-8 -*-
"""
This file contains methods for voigt and pseudo-Voigt fitting, these methods
are imported by class FitLogic.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Developed from PI3diamond code Copyright (C) 2009 Helmut Rathgen <helmut.rathgen@gmail.com>

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
from lmfit.models import VoigtModel, PseudoVoigtModel
from scipy.interpolate import InterpolatedUnivariateSpline
from scipy.special import wofz


################################################################################
#                                                                              #
#                   Defining Voigt and pseudo-Voigt Models                     #
#                                                                              #
################################################################################

###############################
# Voigt model with offset     #
###############################

def make_voigt_model(self, prefix=None):
    """ Create a Voigt model with offset. In this model, gamma is constrained 
                                                to have a value equal to sigma

    @param str prefix: optional, if multiple models should be used in a
                       composite way and the parameters of each model should be
                       distinguished from each other to prevent name collisions.

    @return tuple: (object model, object params).
    """
    voigt_model = VoigtModel(prefix=prefix)
    constant_model, _ = self.make_constant_model(prefix=prefix)
    voigt_offset_model = voigt_model + constant_model

    if prefix is None:
        prefix = ''

    voigt_offset_model.set_param_hint('{0}contrast'.format(prefix),
                                        expr='({0}height/{0}offset)*100'.format(prefix))

    params = voigt_offset_model.make_params()

    return voigt_offset_model, params

############################################
#    Double Voigt model with offset        #
############################################

def make_voigtdouble_model(self):
    """ Create a model with double voigt with offset. The two voigt models will 
                                             have the same sigma and amplitude.

    @return tuple: (object model, object params).
    """
    double_voigt_model, _ = self.make_voigt_model(prefix='v0_')
    double_voigt_model = double_voigt_model + VoigtModel(prefix = 'v1_')

    double_voigt_model.set_param_hint('v1_amplitude', expr='v0_amplitude')
    double_voigt_model.set_param_hint('v1_sigma', expr='v0_sigma')

    params = double_voigt_model.make_params()

    return double_voigt_model, params

###################################################
#    Second version of Voigt model with offset    #
###################################################

def make_voigt2_model(self, prefix=None):
    """ Create a Voigt model with offset. In this model, gamma is no more 
                             constrained to have a value equal to sigma.

    @param str prefix: optional, if multiple models should be used in a
                       composite way and the parameters of each model should be
                       distinguished from each other to prevent name collisions.

    @return tuple: (object model, object params).
    """
    voigt_model = VoigtModel(prefix=prefix)
    constant_model, _ = self.make_constant_model(prefix=prefix)
    voigt_offset_model = voigt_model + constant_model

    if prefix is None:
        prefix = ''

    voigt_offset_model.set_param_hint('{0}contrast'.format(prefix),
                                        expr='({0}height/{0}offset)*100'.format(prefix))
    voigt_offset_model.set_param_hint('{0}gamma'.format(prefix), expr='', vary=True)
    voigt_offset_model.set_param_hint('{0}fwhm'.format(prefix), expr='1.0692 * {0}gamma + sqrt(0.8664 * {0}gamma**2 + 5.5452 * {0}sigma**2)'.format(prefix))
    #voigt_offset_model.set_param_hint('{0}fwhm2'.format(prefix), expr='((2.3548 * {0}sigma)**5 + 2.69269 * (2.3548 * {0}sigma)**4 * (2 * {0}gamma) + 2.42843 * (2.3548 * {0}sigma)**3 * (2 * {0}gamma)**2 + 4.47163 * (2.3548 * {0}sigma)**2 * (2 * {0}gamma)**3 + 0.07842 * (2.3548 * {0}sigma) * (2 * {0}gamma)**4 + (2 * {0}gamma)**5) ** (1/5)'.format(prefix))
    voigt_offset_model.set_param_hint('{0}fraction'.format(prefix), expr='136.603 * (2 * {0}gamma / {0}fwhm) - 47.719 * (2 * {0}gamma / {0}fwhm)**2 + 11.116 * (2 * {0}gamma / {0}fwhm)**3'.format(prefix))
    
    params = voigt_offset_model.make_params()

    return voigt_offset_model, params

##########################################################
#    Second version of double Voigt model with offset    #
##########################################################

def make_voigtdouble2_model(self):
    """ Create a model with double Voigt with offset and gamma not constrained to have a value 
                             equal to sigma. The two Voigt models will have the same sigma, gamma 
                             and amplitude.

    @return tuple: (object model, object params).
    """

    double_voigt_model, _ = self.make_voigt2_model(prefix='v0_')
    double_voigt_model = double_voigt_model + VoigtModel(prefix = 'v1_')

    double_voigt_model.set_param_hint('v1_sigma', expr='v0_sigma')
    double_voigt_model.set_param_hint('v1_amplitude', expr='v0_amplitude')
    double_voigt_model.set_param_hint('v1_gamma', expr='v0_gamma')

    params = double_voigt_model.make_params()

    return double_voigt_model, params

#####################################
#  Pseudo-Voigt model with offset   #
#####################################

def make_pseudovoigt_model(self, prefix=None):
    """ Create a pseudo-Voigt model with offset.

    @param str prefix: optional, if multiple models should be used in a
                       composite way and the parameters of each model should be
                       distinguished from each other to prevent name collisions.

    @return tuple: (object model, object params).
    """
    pseudovoigt_model = PseudoVoigtModel(prefix=prefix)
    constant_model, _ = self.make_constant_model(prefix=prefix)
    pseudovoigt_offset_model = pseudovoigt_model + constant_model

    if prefix is None:
        prefix = ''

    pseudovoigt_offset_model.set_param_hint('{0}contrast'.format(prefix),
                                 expr='({0}height/{0}offset)*100'.format(prefix))

    params = pseudovoigt_offset_model.make_params()

    return pseudovoigt_offset_model, params

###############################################
#    Double Pseudo-Voigt model with offset    #
###############################################

def make_pseudovoigtdouble_model(self):
    """ Create a model with double pseudo-voigt with offset. The two pseudo-voigt models will 
                                                 have the same sigma and amplitude and fraction.

    @return tuple: (object model, object params).
    """
    double_pseudovoigt_model, _ = self.make_pseudovoigt_model(prefix='v0_')
    double_pseudovoigt_model = double_pseudovoigt_model + PseudoVoigtModel(prefix = 'v1_')

    double_pseudovoigt_model.set_param_hint('v1_sigma', expr='v0_sigma')
    double_pseudovoigt_model.set_param_hint('v1_amplitude', expr='v0_amplitude')
    double_pseudovoigt_model.set_param_hint('v1_fraction', expr='v0_fraction')

    params = double_pseudovoigt_model.make_params()

    return double_pseudovoigt_model, params

################################################################################
#                                                                              #
#                    Fit functions and their estimators                        #
#                                                                              #
################################################################################

############################################################################
#                 Single Voigt with offset fitting                         #
############################################################################

def make_voigt_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D voigt fit on the provided data.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...
    """

    model, params = self.make_voigt_model()

    error, params = estimator(x_axis, data, params)

    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.warning('The 1D Voigt fit did not work. Error '
                         'message: {0}\n'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}
    if units is None:
        units = ["arb. units", "arb. units"]

    # result_str_dict['Sigma'] = {'value': result.params['sigma'].value,
    #                                'error': result.params['sigma'].stderr,
    #                                'unit': units[0]}
    result_str_dict['Position'] = {'value': result.params['center'].value,
                                   'error': result.params['center'].stderr,
                                   'unit': units[0]}
    # result_str_dict['Amplitude'] = {'value': result.params['amplitude'].value,
    #                                'error': result.params['amplitude'].stderr,
    #                                'unit': units[1]}
    result_str_dict['Contrast'] = {'value': abs(result.params['contrast'].value),
                                   'error': result.params['contrast'].stderr,
                                   'unit': '%'}
    result_str_dict['FWHM'] = {'value': result.params['fwhm'].value,
                               'error': result.params['fwhm'].stderr,
                               'unit': units[0]}
    result_str_dict['Offset'] = {'value': result.params['offset'].value,
                                   'error': result.params['offset'].stderr,
                                   'unit': units[1]}
    # result_str_dict['Gamma'] = {'value': result.params['gamma'].value,
    #                                'error': result.params['gamma'].stderr,
    #                                'unit': units[0]}
    # result_str_dict['Height'] = {'value': result.params['height'].value,
    #                                'error': result.params['height'].stderr,
    #                                'unit': units[1]}
    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_voigt_dip(self, x_axis, data, params):
    """ Provides an estimator to obtain initial values for the voigt function.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """
    # check if parameters make sense
    error = self._check_1D_input(x_axis=x_axis, data=data, params=params)

    # check if input x-axis is ordered and increasing
    sorted_indices = np.argsort(x_axis)
    if not np.all(sorted_indices == np.arange(len(x_axis))):
        x_axis = x_axis[sorted_indices]
        data = data[sorted_indices]

    data_smooth, offset = self.find_offset_parameter(x_axis, data)

    # data_level = data-offset
    data_level = data_smooth - offset

    # calculate from the leveled data the height:
    height = data_level.min()

    smoothing_spline = 1    # must be 1<= smoothing_spline <= 5
    fit_function = InterpolatedUnivariateSpline(x_axis, data_level,
                                            k=smoothing_spline)
    numerical_integral = fit_function.integral(x_axis[0], x_axis[-1])

    x_zero = x_axis[np.argmin(data_smooth)]

    # according to the derived formula, calculate sigma. The crucial part is
    # here that the offset was estimated correctly, then the area under the
    # curve is calculated correctly:
    sigma = np.abs(numerical_integral / (2 * np.pi * height))

    # auxiliary variables
    stepsize = x_axis[1] - x_axis[0]
    n_steps = len(x_axis)

    amplitude = (height * sigma * np.sqrt(2 * np.pi)) / (wofz((1j * sigma) / (sigma * np.sqrt(2))).real)

    params['amplitude'].set(value=amplitude, max=-1e-12)
    params['sigma'].set(value=sigma, min=stepsize / 2,
                        max=(x_axis[-1] - x_axis[0]) * 10)
    params['center'].set(value=x_zero, min=(x_axis[0]) - n_steps * stepsize,
                         max=(x_axis[-1]) + n_steps * stepsize)
    params['offset'].set(value=offset)

    return error, params

############################################################################
#                   Double Voigt with offset fitting                       #
############################################################################

def make_voigtdouble_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D double voigt dip fit with offset on the provided data.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...

    """

    model, params = self.make_voigtdouble_model()

    error, params = estimator(x_axis, data, params)

    # redefine values of additional parameters
    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.error('The double voigt fit did not '
                     'work: {0}'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}

    if units is None:
        units = ["arb. units", "arb. units"]

    result_str_dict['Position 0'] = {'value': result.params['v0_center'].value,
                                     'error': result.params['v0_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Position 1'] = {'value': result.params['v1_center'].value,
                                     'error': result.params['v1_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Splitting'] = {'value': (result.params['v1_center'].value -
                                              result.params['v0_center'].value),
                                    'error': (result.params['v0_center'].stderr +
                                              result.params['v1_center'].stderr),
                                    'unit': units[0]}

    result_str_dict['Contrast'] = {'value': abs(result.params['v0_contrast'].value),
                                     'error': result.params['v0_contrast'].stderr,
                                     'unit': '%'}

    result_str_dict['FWHM'] = {'value': result.params['v0_fwhm'].value,
                                 'error': result.params['v0_fwhm'].stderr,
                                 'unit': units[0]}

    result_str_dict['Offset'] = {'value': result.params['v0_offset'].value,
                                 'error': result.params['v0_offset'].stderr,
                                 'unit': units[1]}

    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_voigtdouble_dip(self, x_axis, data, params,
                                  threshold_fraction=0.3,
                                  minimal_threshold=0.01,
                                  sigma_threshold_fraction=0.3):
    """ Provide an estimator for double voigt dip with offset.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """

    error = self._check_1D_input(x_axis=x_axis, data=data, params=params)

    # smooth with gaussian filter and find offset:
    data_smooth, offset = self.find_offset_parameter(x_axis, data)

    # level data:
    data_level = data_smooth - offset

    # search for double lorentzian dip:
    ret_val = self._search_double_dip(x_axis, data_level, threshold_fraction,
                                      minimal_threshold,
                                      sigma_threshold_fraction)

    error = ret_val[0]
    sigma0_argleft, dip0_arg, sigma0_argright = ret_val[1:4]
    sigma1_argleft, dip1_arg, sigma1_argright = ret_val[4:7]    

    voigt0_height = data_level[dip0_arg]

    voigt0_center = x_axis[dip0_arg]
    voigt1_center = x_axis[dip1_arg]

    smoothing_spline = 1    # must be 1<= smoothing_spline <= 5
    fit_function = InterpolatedUnivariateSpline(x_axis, data_level,
                                            k=smoothing_spline)
    numerical_integral_0 = fit_function.integral(x_axis[sigma0_argleft],
                                             x_axis[sigma0_argright])

    voigt0_sigma = (1 / 2) * abs(numerical_integral_0 / (np.pi * voigt0_height))

    voigt0_amplitude = (voigt0_height * voigt0_sigma * np.sqrt(2 * np.pi)) / (wofz((1j * voigt0_sigma) / (voigt0_sigma * np.sqrt(2))).real)

    stepsize = x_axis[1] - x_axis[0]
    full_width = x_axis[-1] - x_axis[0]
    n_steps = len(x_axis)

    if voigt0_center < voigt1_center:
        params['v0_center'].set(value=voigt0_center,
                                min=(x_axis[0]) - n_steps * stepsize,
                                max=(x_axis[-1]) + n_steps * stepsize)
        params['v1_center'].set(value=voigt1_center,
                                min=(x_axis[0]) - n_steps * stepsize,
                                max=(x_axis[-1]) + n_steps * stepsize)
    else:
        params['v0_center'].set(value=voigt1_center,
                                min=(x_axis[0]) - n_steps * stepsize,
                                max=(x_axis[-1]) + n_steps * stepsize)
        params['v1_center'].set(value=voigt0_center,
                                min=(x_axis[0]) - n_steps * stepsize,
                                max=(x_axis[-1]) + n_steps * stepsize)
    params['v0_amplitude'].set(value=voigt0_amplitude, max=-0.01)
    params['v0_sigma'].set(value=voigt0_sigma, min=stepsize / 2,
                            max=full_width * 4)
    params['v0_offset'].set(value=offset)

    return error, params

############################################################################
#           Second version of single Voigt with offset fitting             #
############################################################################

def make_voigt2_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D voigt fit on the provided data. In that fit, gamma won't 
                             be constrained to have a value equal to sigma

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...
    """

    model, params = self.make_voigt2_model()

    error, params = estimator(x_axis, data, params)

    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.warning('The 1D Voigt fit did not work. Error '
                         'message: {0}\n'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}
    if units is None:
        units = ["arb. units", "arb. units"]

    result_str_dict['Position'] = {'value': result.params['center'].value,
                                   'error': result.params['center'].stderr,
                                   'unit': units[0]}
    result_str_dict['Contrast'] = {'value': abs(result.params['contrast'].value),
                                   'error': result.params['contrast'].stderr,
                                   'unit': '%'}
    result_str_dict['FWHM'] = {'value': result.params['fwhm'].value,
                               'error': result.params['fwhm'].stderr,
                               'unit': units[0]}
    result_str_dict['Offset'] = {'value': result.params['offset'].value,
                                   'error': result.params['offset'].stderr,
                                   'unit': units[1]}
    result_str_dict['Lorentzian fraction'] = {'value': result.params['fraction'].value,
                                   'error': result.params['fraction'].stderr,
                                   'unit': '%'}
    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_voigt2_dip(self, x_axis, data, params):
    """ Provides an estimator to obtain initial values for the voigt function.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """
    error, params = self.estimate_voigt_dip(x_axis, data, params)

    sigma = params['sigma'].value
    stepsize = x_axis[1] - x_axis[0]

    params['gamma'].set(value=sigma, min=stepsize / 2,
                         max=(x_axis[-1] - x_axis[0]) * 10)

    return error, params

############################################################################
#         Second version of double Voigt with offset fitting               #
############################################################################

def make_voigtdouble2_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D double voigt dip fit with offset on the provided data. In that fit, gamma 
                                         won't be constrained to have a value equal to sigma

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...

    """

    model, params = self.make_voigtdouble2_model()

    error, params = estimator(x_axis, data, params)

    # redefine values of additional parameters
    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.error('The double voigt fit did not '
                     'work: {0}'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}

    if units is None:
        units = ["arb. units", "arb. units"]

    result_str_dict['Position 0'] = {'value': result.params['v0_center'].value,
                                     'error': result.params['v0_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Position 1'] = {'value': result.params['v1_center'].value,
                                     'error': result.params['v1_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Splitting'] = {'value': (result.params['v1_center'].value -
                                              result.params['v0_center'].value),
                                    'error': (result.params['v0_center'].stderr +
                                              result.params['v1_center'].stderr),
                                    'unit': units[0]}

    result_str_dict['Contrast'] = {'value': abs(result.params['v0_contrast'].value),
                                     'error': result.params['v0_contrast'].stderr,
                                     'unit': '%'}

    result_str_dict['FWHM'] = {'value': result.params['v0_fwhm'].value,
                                 'error': result.params['v0_fwhm'].stderr,
                                 'unit': units[0]}

    result_str_dict['Offset'] = {'value': result.params['v0_offset'].value,
                                 'error': result.params['v0_offset'].stderr,
                                 'unit': units[1]}

    result_str_dict['Lorentzian fraction'] = {'value': result.params['v0_fraction'].value,
                                   'error': result.params['v0_fraction'].stderr,
                                   'unit': '%'}  

    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_voigtdouble2_dip(self, x_axis, data, params,
                                  threshold_fraction=0.3,
                                  minimal_threshold=0.01,
                                  sigma_threshold_fraction=0.3):
    """ Provide an estimator for double voigt dip with offset.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """

    error, params = self.estimate_voigtdouble_dip(x_axis, data, params)

    voigt0_sigma = params['v0_sigma'].value
    stepsize = x_axis[1] - x_axis[0]
    full_width = x_axis[-1] - x_axis[0]

    params['v0_gamma'].set(value=voigt0_sigma, min=stepsize / 2,
                            max=full_width * 4)

    return error, params

############################################################################
#               Single Pseudo-Voigt with offset fitting                    #
############################################################################

def make_pseudovoigt_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D pseudo-voigt fit on the provided data.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...
    """

    model, params = self.make_pseudovoigt_model()

    error, params = estimator(x_axis, data, params)

    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.warning('The 1D Pseudo-Voigt fit did not work. Error '
                         'message: {0}\n'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}
    if units is None:
        units = ["arb. units", "arb. units"]

    result_str_dict['Position'] = {'value': result.params['center'].value,
                                   'error': result.params['center'].stderr,
                                   'unit': units[0]}

    result_str_dict['Contrast'] = {'value': abs(result.params['contrast'].value),
                                   'error': result.params['contrast'].stderr,
                                   'unit': '%'}

    result_str_dict['FWHM'] = {'value': result.params['fwhm'].value,
                               'error': result.params['fwhm'].stderr,
                               'unit': units[0]}

    result_str_dict['Offset'] = {'value': result.params['offset'].value,
                                   'error': result.params['offset'].stderr,
                                   'unit': units[1]}

    result_str_dict['Lorentzian fraction'] = {'value': result.params['fraction'].value * 100,
                                   'error': result.params['fraction'].stderr * 100,
                                   'unit': '%'}

    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_pseudovoigt_dip(self, x_axis, data, params):
    """ Provides an estimator to obtain initial values for the pseudo-voigt function.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """
    error, params = self.estimate_voigt_dip(x_axis, data, params)

    params['fraction'].set(value=0.5)

    return error, params

############################################################################
#                Double Pseudo-Voigt with offset fitting                   #
############################################################################

def make_pseudovoigtdouble_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a 1D double pseudo-voigt dip fit with offset on the provided data.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object model: lmfit.model.ModelFit object, all parameters
                          provided about the fitting, like: success,
                          initial fitting values, best fitting values, data
                          with best fit with given axis,...

    """

    model, params = self.make_pseudovoigtdouble_model()

    error, params = estimator(x_axis, data, params)

    # redefine values of additional parameters
    params = self._substitute_params(initial_params=params,
                                     update_params=add_params)
    try:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
    except:
        result = model.fit(data, x=x_axis, params=params, **kwargs)
        self.log.error('The double pseudo-voigt fit did not '
                     'work: {0}'.format(result.message))

    # Write the parameters to allow human-readable output to be generated
    result_str_dict = {}

    if units is None:
        units = ["arb. units", "arb. units"]

    result_str_dict['Position 0'] = {'value': result.params['v0_center'].value,
                                     'error': result.params['v0_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Position 1'] = {'value': result.params['v1_center'].value,
                                     'error': result.params['v1_center'].stderr,
                                     'unit': units[0]}

    result_str_dict['Splitting'] = {'value': (result.params['v1_center'].value -
                                              result.params['v0_center'].value),
                                    'error': (result.params['v0_center'].stderr +
                                              result.params['v1_center'].stderr),
                                    'unit': units[0]}

    result_str_dict['Contrast'] = {'value': abs(result.params['v0_contrast'].value),
                                     'error': result.params['v0_contrast'].stderr,
                                     'unit': '%'}

    result_str_dict['FWHM'] = {'value': result.params['v0_fwhm'].value,
                                 'error': result.params['v0_fwhm'].stderr,
                                 'unit': units[0]}

    result_str_dict['Offset'] = {'value': result.params['v0_offset'].value,
                                 'error': result.params['v0_offset'].stderr,
                                 'unit': units[1]}
    
    result_str_dict['Lorentzian fraction'] = {'value': result.params['v0_fraction'].value * 100,
                                   'error': result.params['v0_fraction'].stderr * 100,
                                   'unit': '%'}

    result_str_dict['chi_sqr'] = {'value': result.chisqr, 'unit': ''}

    result.result_str_dict = result_str_dict
    return result

def estimate_pseudovoigtdouble_dip(self, x_axis, data, params,
                                  threshold_fraction=0.3,
                                  minimal_threshold=0.01,
                                  sigma_threshold_fraction=0.3):
    """ Provide an estimator for double pseudo-voigt dip with offset.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values
    """
    error, params = self.estimate_voigtdouble_dip(x_axis, data, params)

    params['v0_fraction'].set(value=0.5)

    return error, params

