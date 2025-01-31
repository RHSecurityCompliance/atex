#from ... import connection

from .. import Provisioner, Remote

#from . import api


class TestingFarmRemote(Remote):
    def __init__(self, connection, request):
        """
        'connection' is a class Connection instance.

        'request' is a testing farm Request class instance.
        """
        super().__init__(connection)
        self.request = request
        self.valid = True

    def release(self):
        self.disconnect()
        self.request.cancel()
        self.valid = False

    def alive(self):
        return self.valid


class TestingFarmProvisioner(Provisioner):
    pass
