# SPDX-License-Identifier: GPL-3.0-or-later
"""
ToSee-B PPCS packet decryption.

XOR lookup table sourced from the GPLv3 cloudedge-client project.
Decryption implementation based on independently verified PPCS behaviour.
"""

XOR_TABLE = bytes.fromhex(
    "7c9ce84a13dedcb22f2123e4307b3d8cbc0b270c3cf79ae7087196009785efc11fc4dba1c2ebd901faba3b05b81587832872d18b5ad6da9358feaacc6e1bf0a388ab43c00db545384f502266207f075b14981d9ba72ab9a8cbf1fc4947063eb10e043a945eee541134dd4df9ecc7c9e3781a6f706ba4bda95dd5f8e5bb26af4237d8e1020aae5f1cc573094e6924906d12b319ad748a2940f52dbea559e0f479d24bce8982488425c6912ba2fb8fe9a6b09e3f65f603312eac0f952c5ced39b7336c567eb4a0fd7a815351868d9f77ff6a80dfe2bf10d775645776f355cdd0c818e6364162cf99f2324c67606192cad3ea637d16b68ed46835c3529d46441e17"
)

# State recovered from two independent ToSee-B packet captures.
# Compatibility with other devices/firmware is not yet established.
DEFAULT_STATE = bytes.fromhex("fd034d4f")


def decrypt_packet(data: bytes, state: bytes = DEFAULT_STATE) -> bytes:
    """Decrypt a PPCS UDP payload."""
    if len(state) != 4:
        raise ValueError("PPCS cipher state must contain exactly 4 bytes")

    result = bytearray()
    previous = 0

    for value in data:
        index = (previous + state[previous & 3]) & 0xff
        result.append(value ^ XOR_TABLE[index])
        previous = value

    return bytes(result)



def encrypt_packet(data: bytes, state: bytes = DEFAULT_STATE) -> bytes:
    """Encrypt a PPCS UDP payload using the four-byte cipher state."""
    if len(state) != 4:
        raise ValueError("PPCS cipher state must contain exactly 4 bytes")

    result = bytearray()
    previous = 0

    for value in data:
        index = (previous + state[previous & 3]) & 0xff
        encrypted = value ^ XOR_TABLE[index]
        result.append(encrypted)
        previous = encrypted

    return bytes(result)

def is_valid_ppcs_packet(data: bytes) -> bool:
    """Validate the four-byte PPCS header and payload length."""
    return (
        len(data) >= 4
        and data[0] == 0xf1
        and int.from_bytes(data[2:4], "big") == len(data) - 4
    )
