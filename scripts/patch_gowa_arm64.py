"""Raise the WhatsApp gateway's 45 s request limit to 300 s in the pinned ARM64 binary (v9.7.0).

Same change as the amd64 patch in `Dockerfile`, but on ARM64 a constant is not stored as 8 bytes: it is built by
three instructions (MOVZ + MOVK + MOVK). The 45 s value sits in `cmd.restServer`, at file offset 0xAECC38 of the
`linux-arm64` file inside `whatsapp_9.7.0_linux_arm64.zip` (sha256 a1e3b393...). The script refuses to patch
anything that is not exactly the expected three instructions, so a different gateway build fails the image build
instead of being silently changed.

Usage: python patch_gowa_arm64.py /usr/local/bin/whatsapp
"""

import struct
import sys
from pathlib import Path

OFFSET = 0xAECC38
OLD, NEW = 45 * 10**9, 300 * 10**9
RD = 4  # the register the three instructions fill (x4)


def build(value):
    """MOVZ x4,#lo ; MOVK x4,#mid,lsl 16 ; MOVK x4,#hi,lsl 32 (the 4th chunk must be 0)."""
    chunks = [(value >> (16 * i)) & 0xFFFF for i in range(4)]
    assert chunks[3] == 0, "value too large for three instructions"
    return [
        0xD2800000 | chunks[0] << 5 | RD,
        0xF2A00000 | chunks[1] << 5 | RD,
        0xF2C00000 | chunks[2] << 5 | RD,
    ]


def main(path):
    p = Path(path)
    data = bytearray(p.read_bytes())
    want_old, want_new = build(OLD), build(NEW)
    found = list(struct.unpack_from("<3I", data, OFFSET))
    assert found == want_old, "gateway changed: expected 45 s at 0x%X, found %s" % (
        OFFSET,
        [hex(w) for w in found],
    )
    struct.pack_into("<3I", data, OFFSET, *want_new)
    p.write_bytes(data)
    check = list(struct.unpack_from("<3I", p.read_bytes(), OFFSET))
    assert check == want_new
    print("gateway limit raised from 45 s to 300 s at 0x%X" % OFFSET)


if __name__ == "__main__":
    main(sys.argv[1])
