"""
single_instance.py
Prevents two Capris at once (e.g. autostart + manual launch).
If Capri is already running, the second launch just pokes the first one
so it pops back up, then exits.
"""

from typing import Callable, Optional
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance:
    def __init__(self, name: str = "capri-desktop-construct"):
        self._name = name
        self._server: Optional[QLocalServer] = None
        self.on_activate: Optional[Callable[[], None]] = None

    def acquire(self) -> bool:
        """True if we are the only instance. False if another one is running."""
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return False

        QLocalServer.removeServer(self._name)   # clean up after a crash
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(self._name)
        return True

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn:
            conn.disconnected.connect(conn.deleteLater)
        if self.on_activate:
            self.on_activate()
