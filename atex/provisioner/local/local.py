import math

from ... import connection
from ..anyconn import AnyConnectionProvisioner


class LocalProvisioner(AnyConnectionProvisioner):
    """
    - `kwargs` are passed to the underlying LocalConnection.
    """

    def __init__(self, **kwargs):
        super().__init__(
            connection.local.LocalConnection,
            conn_kwargs=kwargs,
            max_remotes=math.inf,
        )


