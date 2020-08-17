# -*- coding: utf-8 -*-
"""
This file contains methods for hyperbolic saturation fitting, these methods
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

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""


from lmfit.models import Model
from lmfit import Parameters, minimize
import numpy as np
import math

################################################################################
#                                                                              #
#                Hyperbolic saturation models                                  #
#                                                                              #
################################################################################


def make_hyperbolicsaturation_model(self, prefix=None):
    """ Create a model of the fluorescence depending on excitation power with
        linear offset.

    @return tuple: (object model, object params)

    Explanation of the objects:
        object lmfit.model.CompositeModel model:
            A model the lmfit module will use for that fit. Here a
            gaussian model. Returns an object of the class
            lmfit.model.CompositeModel.

        object lmfit.parameter.Parameters params:
            It is basically an OrderedDict, so a dictionary, with keys
            denoting the parameters as string names and values which are
            lmfit.parameter.Parameter (without s) objects, keeping the
            information about the current value.
    """

    def hyperbolicsaturation_function(x, I_sat, P_sat):
        """ Fluorescence depending excitation power function

        @param numpy.array x: 1D array as the independent variable e.g. power
        @param float I_sat: Saturation Intensity
        @param float P_sat: Saturation power

        @return: hyperbolicsaturation function: for using it as a model
        """

        return I_sat * (x / (x + P_sat))

    if not isinstance(prefix, str) and prefix is not None:
        self.log.error('The passed prefix <{0}> of type {1} is not a string and'
                       'cannot be used as a prefix and will be ignored for now.'
                       'Correct that!'.format(prefix, type(prefix)))

        mod_sat = Model(hyperbolicsaturation_function, independent_vars='x')
    else:
        mod_sat = Model(hyperbolicsaturation_function, independent_vars='x',
                        prefix=prefix)

    linear_model, params = self.make_linear_model(prefix=prefix)
    complete_model = mod_sat + linear_model

    params = complete_model.make_params()

    return complete_model, params


def make_hyperbolicsaturation_fit(self, x_axis, data, estimator, units=None, add_params=None, **kwargs):
    """ Perform a fit on the provided data with a fluorescence depending function.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param method estimator: Pointer to the estimator method
    @param list units: List containing the ['horizontal', 'vertical'] units as strings
    @param Parameters or dict add_params: optional, additional parameters of
                type lmfit.parameter.Parameters, OrderedDict or dict for the fit
                which will be used instead of the values from the estimator.

    @return object result: lmfit.model.ModelFit object, all parameters
                           provided about the fitting, like: success,
                           initial fitting values, best fitting values, data
                           with best fit with given axis,...
    """

    mod_final, params = self.make_hyperbolicsaturation_model()

    error, params = estimator(x_axis, data, params)

    # overwrite values of additional parameters
    params = self._substitute_params(
        initial_params=params,
        update_params=add_params)

    result = mod_final.fit(data, x=x_axis, params=params, **kwargs)

    if units is None:
        units = ['arb. unit', 'arb. unit']

    result_str_dict = {}

    result_str_dict['I_sat'] = {'value': result.params['I_sat'].value,
                                'unit': units[1]}
    result_str_dict['P_sat'] = {'value': result.params['P_sat'].value,
                                'unit': units[0]}
    result_str_dict['Slope'] = {'value': result.params['slope'].value,
                                'unit': '{0}/{1}'.format(units[1], units[0])}
    result_str_dict['Offset'] = {'value': result.params['offset'].value,
                                 'unit': units[1]}

    if result.errorbars:
        result_str_dict['I_sat']['error'] = result.params['I_sat'].stderr
        result_str_dict['P_sat']['error'] = result.params['P_sat'].stderr
        result_str_dict['Slope']['error'] = result.params['slope'].stderr
        # result_str_dict['Offset']['error'] = result.params['offset'].stderr
    result.result_str_dict = result_str_dict

    return result


def estimate_hyperbolicsaturation(self, x_axis, data, params):
    """ Provides an estimation for a saturation like function.

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

    x_axis_half = x_axis[len(x_axis)//2:]
    data_half = data[len(x_axis)//2:]

    results_lin = self.make_linear_fit(x_axis=x_axis_half, data=data_half,
                                       estimator=self.estimate_linear)

    est_slope = results_lin.params['slope'].value
    est_offset = data.min()

    data_red = data - est_slope*x_axis - est_offset
    est_I_sat = np.mean(data_red[len(data_red)//2:])
    # FIXME: It should be f(est_P_sat) = est_I_sat/2, not est_P_sat = est_I_sat/2
    est_P_sat = est_I_sat/2

    params['I_sat'].value = est_I_sat
    params['slope'].value = est_slope
    params['offset'].value = est_offset
    params['P_sat'].value = est_P_sat

    return error, params


def estimate_hyperbolicsaturation_2(self, x_axis, data, params):
    """ Provides an estimation for a saturation like function.

    @param numpy.array x_axis: 1D axis values
    @param numpy.array data: 1D data, should have the same dimension as x_axis.
    @param lmfit.Parameters params: object includes parameter dictionary which
                                    can be set

    @return tuple (error, params):

    Explanation of the return parameter:
        int error: error code (0:OK, -1:error)
        Parameters object params: set parameters of initial values

    Another version of the estimator. May work better on some datasets. Note that here the offset 
    of the linear model is set to zero and will not vary during the fit. 
    """

    error = self._check_1D_input(x_axis=x_axis, data=data, params=params)

    n = len(x_axis)
    m = min(math.floor(n*0.8), n-2)
    p = max(math.ceil(n*0.1), 2)

    x_tail = x_axis[m:]
    data_tail = data[m:]

    result_lin_tail = self.make_linear_fit(
        x_axis=x_tail, data=data_tail, estimator=self.estimate_linear)
    est_slope = result_lin_tail.params['slope'].value

    data_red = data - est_slope*x_axis
    est_I_sat = np.mean(data_red[m:])

    x_red_head = x_axis[:p]
    data_red_head = data_red[:p]

    no_offset = Parameters()
    no_offset.add('offset', value=0, vary=False)
    result_lin_head = self.make_linear_fit(
        x_axis=x_red_head, data=data_red_head, estimator=self.estimate_linear, add_params=no_offset)
    origin_slope = result_lin_head.params['slope'].value

    est_P_sat = est_I_sat/origin_slope

    params['I_sat'].value = est_I_sat
    params['P_sat'].value = est_P_sat
    params['slope'].value = est_slope
    params['I_sat'].min = 0
    params['P_sat'].min = 0
    params['slope'].min = 0

    params['offset'].value = 0
    params['offset'].vary = False

    return error, params
