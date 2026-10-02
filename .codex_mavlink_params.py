import argparse
import struct
import time

import serial


def x25(data, extra):
    crc = 0xFFFF
    for byte in data + bytes([extra]):
        tmp = byte ^ (crc & 0xFF)
        tmp ^= (tmp << 4) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


class Mavlink:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.1)
        self.seq = 0
        self.buf = bytearray()

    def close(self):
        self.ser.close()

    def send(self, msgid, payload, extra):
        header = bytes([
            len(payload), 0, 0, self.seq, 255, 190,
            msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF,
        ])
        self.seq = (self.seq + 1) & 0xFF
        crc = x25(header + payload, extra)
        self.ser.write(b"\xFD" + header + payload + struct.pack("<H", crc))
        self.ser.flush()

    def messages(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.buf.extend(self.ser.read(4096))
            while True:
                try:
                    start = self.buf.index(0xFD)
                except ValueError:
                    self.buf.clear()
                    break
                if start:
                    del self.buf[:start]
                if len(self.buf) < 10:
                    break
                length = self.buf[1]
                signed = bool(self.buf[2] & 1)
                total = 10 + length + 2 + (13 if signed else 0)
                if len(self.buf) < total:
                    break
                packet = bytes(self.buf[:total])
                del self.buf[:total]
                msgid = packet[7] | (packet[8] << 8) | (packet[9] << 16)
                yield msgid, packet[10:10 + length]


def read_param(link, name, timeout=3):
    payload = struct.pack("<hBB16s", -1, 1, 1, name.encode().ljust(16, b"\0"))
    link.send(20, payload, 214)
    for msgid, data in link.messages(timeout):
        if msgid == 22 and len(data) >= 25:
            found = data[8:24].split(b"\0", 1)[0].decode(errors="replace")
            if found == name:
                return struct.unpack_from("<f", data, 0)[0]
    raise TimeoutError(f"No PARAM_VALUE response for {name}")


def set_param(link, name, value):
    payload = struct.pack("<fBB16sB", float(value), 1, 1, name.encode().ljust(16, b"\0"), 6)
    link.send(23, payload, 168)
    time.sleep(0.3)
    actual = read_param(link, name)
    if abs(actual - float(value)) > 0.25:
        raise RuntimeError(f"{name} read back as {actual}, expected {value}")
    print(f"{name}={actual:g}")


def reboot(link):
    payload = struct.pack("<7fHBBB", 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 246, 1, 1, 0)
    link.send(76, payload, 152)
    print("reboot command sent")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port")
    parser.add_argument("action", choices=["read", "set", "setraw", "reboot"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("value", nargs="?", type=float)
    args = parser.parse_args()
    link = Mavlink(args.port)
    try:
        if args.action == "read":
            print(f"{args.name}={read_param(link, args.name):g}")
        elif args.action == "set":
            set_param(link, args.name, args.value)
        elif args.action == "setraw":
            payload = struct.pack("<fBB16sB", float(args.value), 1, 1, args.name.encode().ljust(16, b"\0"), 6)
            link.send(23, payload, 168)
            print(f"{args.name} write sent")
        else:
            reboot(link)
    finally:
        link.close()


if __name__ == "__main__":
    main()
