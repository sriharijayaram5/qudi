# my_server.py

from msl.loadlib import Server32


class MyServer(Server32):
    """Wrapper around a 32-bit C++ library 'my_lib.dll' that has an 'add' and 'version' function."""

    def __init__(self, host, port, **kwargs):
        # Load the 'my_lib' shared-library file using ctypes.CDLL
        libname = "C:/Users/yy3/Documents/Software/proteusq-modules-develop-src-labq/proteusq-modules-develop-src-labq/src/labq/logic/scanlogic/Tracking_default.dll"
        super(MyServer, self).__init__(libname, 'cdll', host, port)
        import numpy as np

        # The Server32 class has a 'lib' property that is a reference to the ctypes.CDLL object
        
        self.lib.track.restype = ctypes.c_int
        self.lib.track.argtypes = [np.ctypeslib.ndpointer(ctypes.c_double), # Freqs
                                         np.ctypeslib.ndpointer(ctypes.c_double), # Counts
                                         ctypes.c_int, # numElem
                                         ctypes.c_double, # stepwidth
                                         ctypes.c_bool, # dip
                                         np.ctypeslib.ndpointer(ctypes.c_double) # NewFreqs
                                        ]
        
    def track(self, frequency_list,esr_meas_mean,numElems_c,stepwidth_c,dip_c):
        numElems_c = ctypes.c_int(numElems_c)
        stepwidth_c = ctypes.c_double(stepwidth_c)
        dip_c = ctypes.c_bool(dip_c)

        self.lib.track(frequency_list,esr_meas_mean,numElems_c,stepwidth_c,dip_c,frequency_list)
