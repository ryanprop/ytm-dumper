import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def fnv1a(data: bytes) -> int:
    """fnv1a hash function, returns a uint64"""
    res = 0
    for i in data:
        res ^= i
        res = (res + (res << 1) + (res << 4) + (res << 5) + (res << 7) + (res << 8) + (res << 40)) & 0xffffffffffffffff
    return res

def decrypt_media(exo_file: bytes, key: bytes, cache_key: bytes) -> bytes:
    """Returns the decrypted media file contents."""
    iv = struct.pack('>QQ', fnv1a(cache_key), 0)
    decryptor = Cipher(algorithms.AES(key), modes.CTR(nonce=iv)).decryptor()
    return decryptor.update(exo_file) + decryptor.finalize()