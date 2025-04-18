import argparse
from base64 import b64decode
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import struct

def decrypt_cache_index(ciphertext: bytes, key: bytes):
    """Decrypts the AES-CBC-PKCS5 encrypted cache index."""
    iv = ciphertext[:16]
    ciphertext = ciphertext[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()

    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS5 padding
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext


class CacheIdxParser(object):
    """Parses the exo player encrypted cache index file.
    
    Format:
    u8 header:8
    u32 count
      u32 id
      str key
      u32 count
        str key
        long-str values
    """
    def __init__(self, contents: bytes, key: bytes):
        self.contents = decrypt_cache_index(contents[8:], key)
        self.offset = 0
        self.entries = {}
        count, = self.unpack('>L')
        for i in range(count):
            id, = self.unpack('>L')
            key = self.unpack_bytes()
            count_2, = self.unpack('>L')
            items = {}
            self.entries[key] = dict(id=id, items=items)
            for j in range(count_2):
                key2 = self.unpack_bytes()
                count_3, = self.unpack('>L')
                values = self.unpack_bytes(count_3)
                items[key2] = values
    
    def __getitem__(self, key: bytes):
        """Returns the id for a given cache key."""
        return self.entries[key]['id']

    def unpack(self, fmt):
        res = struct.unpack_from(fmt, self.contents, self.offset)
        self.offset += struct.calcsize(fmt)
        return res
    
    def unpack_bytes(self, strlen=None):
        if strlen is None:
            strlen, = self.unpack('>H')
        new_offset = self.offset + strlen
        res = self.contents[self.offset:new_offset]
        self.offset = new_offset
        return res
    


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse and read the AES-CBC-PKCS5 encrypted exo player cache index.")
    parser.add_argument("filename", help="Path to the cached_content_index.exi file")
    parser.add_argument("key", help="Base64 encoded decryption key.")
    args = parser.parse_args()

    # Decode the base64 encoded key
    key = b64decode(args.key) 

    ci = CacheIdxParser(args.filename, key)
    for k, v in ci.entries.items():
        print(k, '->', v)
    
