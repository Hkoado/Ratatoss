"""Run Croc in a Windows Job Object with noninteractive standard handles."""

import os
import subprocess
import time
from dataclasses import dataclass

if os.name == "nt":
    import _winapi
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("per_process_time", ctypes.c_longlong),
            ("per_job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("min_working_set", ctypes.c_size_t),
            ("max_working_set", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", _BasicLimits),
            ("io_counters", ctypes.c_ulonglong * 6),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    class _Accounting(ctypes.Structure):
        _fields_ = [
            ("times", ctypes.c_longlong * 4),
            ("page_faults", wintypes.DWORD),
            ("total_processes", wintypes.DWORD),
            ("active_processes", wintypes.DWORD),
            ("terminated_processes", wintypes.DWORD),
        ]

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _kernel.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    )
    _kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel.ResumeThread.argtypes = (wintypes.HANDLE,)
    _kernel.ResumeThread.restype = wintypes.DWORD
    _kernel.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    )
    _kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)

    JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    CREATE_SUSPENDED = 0x4
    CREATE_UNICODE_ENVIRONMENT = 0x400

    def _require(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())


@dataclass(frozen=True)
class JobCleanup:
    active_before_stop: int
    active_after_stop: int
    total_processes: int
    exit_code: int


class WindowsChild:
    def __init__(self, argv, *, cwd, env):
        if os.name != "nt":
            raise OSError("The Croc process supervisor requires Windows")

        self._job = _kernel.CreateJobObjectW(None, None)
        _require(self._job)
        self._process = None
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _require(_kernel.SetInformationJobObject(
                self._job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits),
            ))
            with open(os.devnull, "r+b", buffering=0) as stream:
                null_handle = msvcrt.get_osfhandle(stream.fileno())
                os.set_handle_inheritable(null_handle, True)
                startup = subprocess.STARTUPINFO(
                    dwFlags=subprocess.STARTF_USESTDHANDLES,
                    hStdInput=null_handle, hStdOutput=null_handle, hStdError=null_handle,
                    lpAttributeList={"handle_list": [null_handle]},
                )
                self._process, thread, self.pid, _ = _winapi.CreateProcess(
                    str(argv[0]), subprocess.list2cmdline(argv), None, None, True,
                    CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | subprocess.CREATE_NO_WINDOW,
                    env, str(cwd), startup,
                )
            try:
                _require(_kernel.AssignProcessToJobObject(self._job, self._process))
                _require(_kernel.ResumeThread(thread) != 0xFFFFFFFF)
            finally:
                _winapi.CloseHandle(thread)
        except BaseException:
            try:
                if self._process is not None:
                    try:
                        _winapi.TerminateProcess(self._process, 1)
                        _winapi.WaitForSingleObject(self._process, 5000)
                    finally:
                        _winapi.CloseHandle(self._process)
            finally:
                _winapi.CloseHandle(self._job)
            raise

    def poll(self):
        if _winapi.WaitForSingleObject(self._process, 0) == _winapi.WAIT_OBJECT_0:
            return _winapi.GetExitCodeProcess(self._process)
        return None

    def _accounting(self):
        accounting = _Accounting()
        _require(_kernel.QueryInformationJobObject(
            self._job, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting), ctypes.sizeof(accounting), None,
        ))
        return accounting

    def stop(self):
        """Confirm every Job Object member exited before releasing staging."""
        try:
            before = self._accounting()
            if before.active_processes:
                _require(_kernel.TerminateJobObject(self._job, 1))
            deadline = time.monotonic() + 5
            while True:
                after = self._accounting()
                if not after.active_processes:
                    if _winapi.WaitForSingleObject(self._process, 1000) != _winapi.WAIT_OBJECT_0:
                        raise OSError("Croc process did not signal exit after job termination")
                    return JobCleanup(
                        before.active_processes, after.active_processes, after.total_processes,
                        _winapi.GetExitCodeProcess(self._process),
                    )
                if time.monotonic() >= deadline:
                    raise OSError("Croc Job Object did not empty before cleanup deadline")
                time.sleep(0.01)
        finally:
            _winapi.CloseHandle(self._job)
            _winapi.CloseHandle(self._process)
