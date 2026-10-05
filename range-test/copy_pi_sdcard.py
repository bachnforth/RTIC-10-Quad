"""Copy the mesh logs off a Raspberry Pi SD card (ext4 root partition) on Windows. READ-ONLY: it never writes to the card.

Needs administrator rights to open the raw disk.
Usage (elevated):  python copy_pi_sdcard.py <disk_number> <partition_offset_bytes> <partition_size_bytes> <out_dir>
"""
import os, sys, traceback
import ext4

disk, part_off, part_size, out_dir = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
os.makedirs(out_dir, exist_ok=True)
LOG = open(os.path.join(out_dir, "copy_log.txt"), "w", encoding="utf-8", buffering=1)


def log(*a):
    print(*a)
    print(*a, file=LOG)


class RawPartition:
    """File-like view of one partition of a raw disk; reads are padded to 512-byte sectors, as Windows requires."""

    def __init__(self, path, offset, size):
        self.f = open(path, "rb", buffering=0)
        self.base, self.size, self.pos = offset, size, 0

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        if n == 0:
            return b""
        a = self.base + self.pos
        s = a & ~511
        e = (a + n + 511) & ~511
        self.f.seek(s)
        buf = self.f.read(e - s)
        data = buf[a - s:a - s + n]
        self.pos += len(data)
        return data

    def peek(self, n=1):
        d = self.read(n)
        self.pos -= len(d)
        return d

    def readable(self): return True
    def seekable(self): return True
    def close(self): self.f.close()


def walk(vol, ino, path, dest, depth=0):
    """Copy a directory tree. Returns (files, bytes)."""
    nfiles, nbytes = 0, 0
    os.makedirs(dest, exist_ok=True)
    d = ino.opendir()
    for item in d:
        ent = item[0] if isinstance(item, tuple) else item
        name = ent.name_str
        if name in (".", ".."):
            continue
        try:
            child = ent.inode if not isinstance(ent.inode, int) else vol.inodes[ent.inode]
            mode = child.i_mode
            target = os.path.join(dest, name)
            if (mode & 0o170000) == 0o040000:
                f2, b2 = walk(vol, child, path + "/" + name, target, depth + 1)
                nfiles += f2; nbytes += b2
            elif (mode & 0o170000) == 0o100000:
                with child.open() as src, open(target, "wb") as dst:
                    data = src.read()
                    dst.write(data)
                nfiles += 1; nbytes += len(data)
        except Exception as e:
            log("  skipped", path + "/" + name, "->", repr(e)[:150])
    return nfiles, nbytes


try:
    log("opening disk", disk, "partition offset", part_off, "size", part_size)
    stream = RawPartition(rf"\\.\PhysicalDrive{disk}", part_off, part_size)
    vol = ext4.Volume(stream, ignore_checksum=True, ignore_flags=True)
    log("ext4 volume opened; label/uuid:", getattr(vol, "uuid", None))
    for path in ("/home/ebach/jam_logs",):
        try:
            ino = vol.inode_at(path)
        except Exception as e:
            log("not found:", path, repr(e)[:150])
            continue
        dest = os.path.join(out_dir, "jam_logs")
        n, b = walk(vol, ino, path, dest)
        log(f"copied {n} files, {b / 1e6:.1f} MB from {path} to {dest}")
    log("DONE")
except Exception:
    log("FAILED")
    log(traceback.format_exc())
