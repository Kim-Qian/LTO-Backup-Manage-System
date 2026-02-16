import os
import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

# =========================
# KEY DERIVATION
# =========================

def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte (256-bit) key from a passphrase."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
        backend=default_backend()
    )
    return kdf.derive(passphrase)

# =========================
# STREAMING ENCRYPTION WRAPPERS
# =========================

class EncryptionWriter:
    """
    Streaming AES-GCM Encryption.
    Calculates the Auth Tag upon finalization.
    """
    def __init__(self, wrapped_file, key: bytes, iv: bytes):
        self._file = wrapped_file
        # GCM mode initialization (12-byte IV recommended)
        self._cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
        self._encryptor = self._cipher.encryptor()
        self.tag = None 

    def write(self, data: bytes):
        if not data: return
        self._file.write(self._encryptor.update(data))

    def finalize(self):
        """Must be called to generate the authentication tag."""
        self._encryptor.finalize()
        self.tag = self._encryptor.tag
        return self.tag

    def flush(self):
        self._file.flush()
    
    def tell(self):
        return self._file.tell()

class DecryptionReader:
    """
    Streaming AES-GCM Decryption.
    Validates integrity on the fly (at EOF).
    """
    def __init__(self, wrapped_file, key: bytes, iv: bytes, tag: bytes):
        self._file = wrapped_file
        self._cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
        self._decryptor = self._cipher.decryptor()

    def read(self, size=-1):
        data = self._file.read(size)
        if not data:
            # EOF reached: finalize to verify tag
            try:
                self._decryptor.finalize()
                return b""
            except Exception as e:
                raise ValueError("Integrity check failed! Data corrupted or tampered.") from e
        
        return self._decryptor.update(data)
    
class HashReader:
    """
    Passthrough reader that calculates SHA256 of the stream.
    """
    def __init__(self, wrapped_file):
        self._file = wrapped_file
        self._hash = hashlib.sha256()

    def read(self, size=-1):
        data = self._file.read(size)
        if data:
            self._hash.update(data)
        return data

    def get_hash(self):
        return self._hash.hexdigest()
    
    def close(self):
        self._file.close()

# =========================
# RSA & STATIC HELPERS
# =========================

def generate_rsa_keypair(output_dir: str) -> bytes:
    """Generate RSA key pair and save to disk."""
    os.makedirs(output_dir, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    with open(os.path.join(output_dir, "private.pem"), "wb") as f:
        f.write(private_pem)
    with open(os.path.join(output_dir, "public.pem"), "wb") as f:
        f.write(public_pem)
    
    return public_pem

def encrypt_symmetric_key(sym_key: bytes, public_pem: bytes) -> bytes:
    public_key = serialization.load_pem_public_key(public_pem)
    return public_key.encrypt(
        sym_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

def decrypt_symmetric_key(enc_key: bytes, private_pem: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    return private_key.decrypt(
        enc_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def encrypt_name(name: str, key: bytes) -> str:
    # Use Fernet for small string encryption (filenames)
    # Adapt raw AES key to Fernet url-safe key
    f_key = base64.urlsafe_b64encode(key)
    return Fernet(f_key).encrypt(name.encode()).decode()

def decrypt_name(enc_name: str, key: bytes) -> str:
    f_key = base64.urlsafe_b64encode(key)
    return Fernet(f_key).decrypt(enc_name.encode()).decode()