"""Account-scoped Windows objects for the packaged starter."""

import stat
import struct
import time
from contextlib import contextmanager

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32pipe
import win32security
import winerror

PORT = struct.Struct("!H")
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
SECURITY_IDENTIFICATION = 0x00010000
SECURITY_SQOS_PRESENT = 0x00100000
SYSTEM_SID = win32security.ConvertStringSidToSid("S-1-5-18")
ADMINISTRATORS_SID = win32security.ConvertStringSidToSid("S-1-5-32-544")


class NodeDataPermissionError(PermissionError):
    """The existing Node data is not private to the account."""


class NodeIPC:
    def __init__(self):
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            self.sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        finally:
            token.Close()
        self.sid_string = win32security.ConvertSidToStringSid(self.sid)
        # Global scopes the mutex to the account across Windows logon sessions.
        self.mutex_name = rf"Global\Ratatoss.Node.{self.sid_string}"
        self.pipe_name = rf"\\.\pipe\Ratatoss.Node.v1.{self.sid_string}"

    def security(self, *, inherit_acl=False):
        attributes = pywintypes.SECURITY_ATTRIBUTES()
        flags = "OICI" if inherit_acl else ""
        attributes.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            f"O:{self.sid_string}D:P(A;{flags};GA;;;{self.sid_string})", win32security.SDDL_REVISION_1
        )
        return attributes

    @contextmanager
    def claim_node(self):
        mutex = win32event.CreateMutex(self.security(), False, self.mutex_name)
        try:
            state = win32event.WaitForSingleObject(mutex, 0)
            claimed = state in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED)
            try:
                yield claimed
            finally:
                if claimed:
                    win32event.ReleaseMutex(mutex)
        finally:
            mutex.Close()

    def create_data_dir(self, path, database_name):
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            win32file.CreateDirectory(str(path), self.security(inherit_acl=True))
        except pywintypes.error as exc:
            if exc.winerror != winerror.ERROR_ALREADY_EXISTS:
                raise
        self.check_data_acl(path, stat.S_ISDIR)
        for suffix in ("", "-wal", "-shm", "-journal"):
            db_file = path / f"{database_name}{suffix}"
            try:
                self.check_data_acl(db_file, stat.S_ISREG)
            except FileNotFoundError:
                continue

    def check_data_acl(self, path, expected_type):
        info = path.lstat()
        if not expected_type(info.st_mode) or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise NodeDataPermissionError()

        security = win32security.GetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
        )
        trusted = (self.sid, SYSTEM_SID, ADMINISTRATORS_SID)
        acl = security.GetSecurityDescriptorDacl()
        if acl is None or security.GetSecurityDescriptorOwner() not in trusted:
            raise NodeDataPermissionError()
        for index in range(acl.GetAceCount()):
            ace = acl.GetAce(index)
            if ace[0][0] == win32security.ACCESS_DENIED_ACE_TYPE:
                continue
            if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE or ace[-1] not in trusted:
                raise NodeDataPermissionError()

    @contextmanager
    def create_pipe(self):
        pipe = win32pipe.CreateNamedPipe(
            self.pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_NOWAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1, PORT.size, 1, 0, self.security(),
        )
        try:
            yield pipe
        finally:
            pipe.Close()

    @staticmethod
    def publish_port(pipe, port, stop):
        payload = PORT.pack(port)
        while not stop.is_set():
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
            except pywintypes.error as exc:
                if exc.winerror == winerror.ERROR_PIPE_LISTENING:
                    stop.wait(0.05)
                    continue
                if exc.winerror == winerror.ERROR_NO_DATA:
                    win32pipe.DisconnectNamedPipe(pipe)
                    continue
                if exc.winerror != winerror.ERROR_PIPE_CONNECTED:
                    raise

            try:
                win32file.WriteFile(pipe, payload)
                # Let the client read before disconnecting, with a bound for stalled readers.
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline and not stop.is_set():
                    try:
                        win32file.ReadFile(pipe, 1)
                        break
                    except pywintypes.error as exc:
                        if exc.winerror != winerror.ERROR_NO_DATA:
                            raise
                        stop.wait(0.02)
            except pywintypes.error as exc:
                if exc.winerror not in (winerror.ERROR_BROKEN_PIPE, winerror.ERROR_NO_DATA,
                                        winerror.ERROR_PIPE_NOT_CONNECTED):
                    raise
            finally:
                win32pipe.DisconnectNamedPipe(pipe)

    def read_port(self, timeout):
        try:
            pipe = win32file.CreateFile(
                self.pipe_name, win32con.GENERIC_READ | win32con.GENERIC_WRITE | win32con.READ_CONTROL, 0, None,
                win32con.OPEN_EXISTING, SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, None,
            )
        except pywintypes.error as exc:
            if exc.winerror in (winerror.ERROR_FILE_NOT_FOUND, winerror.ERROR_PIPE_BUSY):
                return None
            raise

        try:
            security = win32security.GetSecurityInfo(
                pipe, win32security.SE_KERNEL_OBJECT, win32security.OWNER_SECURITY_INFORMATION
            )
            if security.GetSecurityDescriptorOwner() != self.sid:
                raise PermissionError("Unexpected Node pipe owner")
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline:
                    _, available, _ = win32pipe.PeekNamedPipe(pipe, 0)
                    if available >= PORT.size:
                        _, payload = win32file.ReadFile(pipe, PORT.size)
                        win32file.WriteFile(pipe, b"\0")
                        return PORT.unpack(payload)[0] or None
                    time.sleep(0.02)
            except pywintypes.error as exc:
                if exc.winerror not in (winerror.ERROR_BROKEN_PIPE, winerror.ERROR_PIPE_NOT_CONNECTED,
                                        winerror.ERROR_NO_DATA):
                    raise
        finally:
            pipe.Close()
        return None
