# -*- coding: utf-8 -*-
"""
Generic color scale implementation for qafm gui
as taken from the Matplotlib colormap documentation:
https://matplotlib.org/stable/tutorials/colors/colormaps.html

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
import logging
import copy
import numpy as np
from matplotlib import cm
import matplotlib.pyplot as plt
from numpy.core.numeric import ones

from gui.colordefs import ColorScale
from collections import OrderedDict

# color maps of matplotlib
colormap_type_name = OrderedDict({
    'Perceptually Uniform Sequential': ['viridis', 'plasma', 'inferno', 'magma', 'cividis'],

    'Sequential'                     : [ 'Greys', 'Purples', 'Blues', 'Greens', 'Oranges', 'Reds',
                                         'YlOrBr', 'YlOrRd', 'OrRd', 'PuRd', 'RdPu', 'BuPu',
                                         'GnBu', 'PuBu', 'YlGnBu', 'PuBuGn', 'BuGn', 'YlGn'],

    'Sequential (2)'                 : [ 'binary', 'gist_yarg', 'gist_gray', 'gray', 'bone', 'pink',
                                         'spring', 'summer', 'autumn', 'winter', 'cool', 'Wistia',
                                         'hot', 'afmhot', 'gist_heat', 'copper'],

    'Diverging'                      : [ 'PiYG', 'PRGn', 'BrBG', 'PuOr', 'RdGy', 'RdBu',
                                         'RdYlBu', 'RdYlGn', 'Spectral', 'coolwarm', 'bwr', 'seismic'],

    'Cyclic'                         : [ 'twilight', 'twilight_shifted', 'hsv'],

    'Qualitative'                    : [ 'Pastel1', 'Pastel2', 'Paired', 'Accent', 'Dark2', 
                                         'Set1', 'Set2', 'Set3', 'tab10', 'tab20', 'tab20b', 'tab20c'],

    'Miscellaneous'                  : [ 'flag', 'prism', 'ocean', 'gist_earth', 'terrain', 
                                         'gist_stern', 'gnuplot', 'gnuplot2', 'CMRmap', 'cubehelix', 
                                         'brg', 'gist_rainbow', 'rainbow', 'jet',  'nipy_spectral', # 'turbo',
                                         'gist_ncar']
})

colormap_names = [ name for clist in colormap_type_name.values() for name in clist] 
_valid_colormap_names = plt.colormaps()

# ---------------------------
# Helper functions
# ---------------------------

def linear_segment(x_range, y_range, n_points):
    """ Creates a continous linear segmented interpolation of y
        based upon equally distributed n_points in a segment definition
        
    @param list x_range: list of x vertex points of segments; e.g. [ 0.0, 0.2, 0.5, 0.8, 1.0] --> must be ascending, monotonic, & unique
    @param list y_range: list of y vertex points of segments; e.g. [ 10.0, 15.0 , 8.2, 15.0, 20.0]

    @return list y_points: list of interpolated range of y values for x values
    """
    x_min = min(x_range)
    x_max = max(x_range)
    x_points = [ x_min + (ii/(n_points-1))*(x_max-x_min) for ii in range(n_points)]
    y_points = []
    
    i = 0
    for x_p in x_points:
        while x_p > x_range[i+1]:
            i += 1
        
        y = (y_range[i+1] - y_range[i])/(x_range[i+1] - x_range[i])*(x_p - x_range[i]) + y_range[i]
        y_points.append(y)
        
    return y_points


def generate_linear_scale(cmap_name):
    """ Creates a linear scale color map for various definitions
        type 1: contiuous scale (defined by .colors)
        type 2: defined by segments; scale is derived from segments
        type 3: function based; static definition is derived from x = [0.0 .. 1.0] inputs
    
    @param str cmap_name: name of matplotlib color map

    @return list colors list of n tuples/list of r,g,b triplets for a scale; shape = (cmap.N,3)
    """
    cmap = cm.get_cmap(cmap_name) 

    if hasattr(cmap,'colors'):
        # continuous range type color maps
        colors = copy.copy(cmap.colors)

    elif isinstance(cmap._segmentdata['red'],list):
        # segmented color maps, in which we must create a linear map
        rgba = cmap._segmentdata

        tones = []
        for c in ('red', 'green', 'blue'):
            tone_x = [v[0] for v in rgba[c]]
            tone_y = [v[1] for v in rgba[c]]

            tone = linear_segment(tone_x, tone_y, cmap.N)
            tones.append(tone)

        colors = [[r,g,b] for r,g,b in zip(*tones)]
    
    elif callable(cmap._segmentdata['red']):
        # color is defined by a function(x)
        rgba = cmap._segmentdata

        tones = []
        for c in ('red', 'green', 'blue'):
            x = [v/(cmap.N-1) for v in range(cmap.N)] 
            y = list(map(rgba[c],x))
            y_min = min(y)
            y_max = max(y)
            y_norm = [(v-y_min)/(y_max-y_min) for v in y ]

            tones.append(y_norm)

        colors = [[r,g,b] for r,g,b in zip(*tones)]
    
    else:
        # unknown method of implmentation; raise an error
        colors = None

    return colors


# ---------------------------
# Class definitions
# ---------------------------

class ColorScaleGen(ColorScale):
    """ Color scale generator based upon Matplotlib color maps
        
        Supplied defnition of 'cmap_type', and 'cmap_name' correpsond to the 
        key and list item in colormaps definition (above)
    """
    def __init__(self, cmap_name='inferno'):

        self.log = logging.getLogger(__name__)

        if (cmap_name not in colormap_names) or (cmap_name not in _valid_colormap_names):
            self.log.error(f"Invalid color map name specified={cmap_name}, not found in colormap_names ={colormap_names}, using default='inferno'")
            cmap_name = 'inferno'
        
        colors = generate_linear_scale(cmap_name)

        if colors is None:
            self.log.error(f"Colormap = {cmap_name} has a ._segmentdata definition method which has not yet been implemented")
            colors = generate_linear_scale('inferno')  # default to 'inferno' if such things happen

        cmap_arr = np.array(colors)

        self._cmap_name = cmap_name
        self.COLORS = np.hstack((cmap_arr, np.ones((cmap_arr.shape[0], 1), dtype=np.float)))*255
        self.COLORS_INV = self.COLORS[::-1]

        super().__init__()