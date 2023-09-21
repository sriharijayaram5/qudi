# my_client.py

from msl.loadlib import Client64

class MyClient(Client64):
    """Call a function in 'my_lib.dll' via the 'MyServer' wrapper."""

    def __init__(self):
        # Specify the name of the Python module to execute on the 32-bit server (i.e., 'my_server')
        super(MyClient, self).__init__(module32='my_server')

    def add(self, a, b):
        # The Client64 class has a 'request32' method to send a request to the 32-bit server
        # Send the 'a' and 'b' arguments to the 'add' method in MyServer
        return self.request32('add', a, b)

    def version(self):
        # Get the version
        return self.request32('version')