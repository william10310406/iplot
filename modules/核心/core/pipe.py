"""主程序與工作程序之間的管道（D161）。一則訊息是 4 位元組的長度加上 pickle；兩頭都是 iPLoT 自己開的程序。

訊息只有四種：主程序 → 工作程序 ("start", 資料)、("res", 編號, 成功?, 值)；
工作程序 → 主程序 ("req", 編號, 名稱, 參數)、("done", Result, memory)。"""

import pickle
import struct
import threading
from typing import Any, BinaryIO


class Pipe:
    """一進一出兩條位元組流。send 可以從多條執行緒同時呼叫；recv 只給一條執行緒用。"""

    def __init__(self, read: BinaryIO, write: BinaryIO) -> None:
        self._read, self._write, self._lock = read, write, threading.Lock()

    def send(self, message: tuple) -> None:
        """送一則；pickle 不了（例如模組回傳了一個視窗物件）丟 pickle.PicklingError 等，呼叫的人決定怎麼說。"""
        data = pickle.dumps(message)
        with self._lock:
            self._write.write(struct.pack(">I", len(data)) + data)
            self._write.flush()

    def recv(self) -> Any:
        """收一則；對方關掉了（程序結束）丟 EOFError。"""
        head = self._read.read(4)
        if len(head) < 4:
            raise EOFError
        size = struct.unpack(">I", head)[0]
        data = self._read.read(size)
        if len(data) < size:
            raise EOFError
        return pickle.loads(data)  # noqa: S301  兩頭都是 iPLoT 自己開的程序
