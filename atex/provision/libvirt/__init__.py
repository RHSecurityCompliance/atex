from .. import base
from ... import util, ssh


class LibvirtProvisioner(base.Provisioner):
    number = 123

    def reserve(self):
        util.debug(f"reserving {self.number}")

    # TODO: as simple attribute, to be guaranteed set when reserve() returns,
    #       can be overriden by a getter function if you need to keep track
    #       how many times it was accessed
    def connection(self):
        #return {"Hostname": "1.2.3.4", "User": "root", "IdentityFile": ...}
        util.debug(f"returning ssh for {self.number}")
        return ssh.SSHConn({"Hostname": "1.2.3.4", "User": "root"})

    def release(self):
        util.debug(f"releasing {self.number}")

    def alive(self):
        util.debug(f"always alive: {self.number}")
        return True
