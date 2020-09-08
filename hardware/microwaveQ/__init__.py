# handle the integration of the core communication protocols for the microwaveQ.

import os
import sys

mq_lib_path = os.path.dirname(__file__)
mq_dev_path = os.path.join(mq_lib_path, 'microwaveq_py')
mq_comm_path = os.path.join(mq_lib_path, 'slac_protocols')

if mq_dev_path not in sys.path:
    sys.path.append(mq_dev_path)

if mq_comm_path not in sys.path:
    sys.path.append(mq_comm_path)