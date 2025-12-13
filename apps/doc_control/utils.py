# import hashlib
# from django.conf import settings
# from django.utils import timezone
# import hmac
# import base64

# # --- File Integrity Check ---
# def compute_sha256(file_obj):
#     """Calculates SHA-256 hash for the file content (ISO 17025/21 CFR 11 Data Integrity)."""
#     hasher = hashlib.sha256()
#     # Rewind file pointer to ensure consistent hashing if read multiple times
#     file_obj.seek(0)
#     for chunk in file_obj.chunks():
#         hasher.update(chunk)
#     file_obj.seek(0) # Reset file pointer for subsequent operations (like saving to storage)
#     return hasher.hexdigest()

# # --- 21 CFR Part 11 Verification Data Creation ---
# def create_verification_hash(user_id, password_hash, timestamp_iso):
#     """
#     Creates a unique cryptographic link (verification_data) for the electronic signature.
#     This links the signature to the user's secure credentials (password hash) at the time of signing.
#     """
#     # Use the Django SECRET_KEY as a salt for added security.
#     secret_key = settings.SECRET_KEY
#     payload = f"{user_id}|{password_hash}|{timestamp_iso}"
    
#     sig = hmac.new(secret_key.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest()
#     return base64.b64encode(sig).decode('utf-8')


# # import hashlib
# # from django.conf import settings
# # from django.utils import timezone
# # import hmac
# # import base64


# # def compute_sha256(file_obj):
# #     hasher = hashlib.sha256()
# #     for chunk in file_obj.chunks():
# #         hasher.update(chunk)
# #     return hasher.hexdigest()


# # def sign_electronic_signature(user, document_version, reason, secret_key=None):
# #     """
# #     Create a cryptographic signature value (HMAC) for Part 11 linking.
# #     This is an application-level convenience; for production use HSM/vault.
# #     """
# #     if secret_key is None:
# #         secret_key = settings.SECRET_KEY
# #     payload = f"{document_version.id}|{user.id}|{user.username}|{reason}|{timezone.now().isoformat()}"
# #     sig = hmac.new(secret_key.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest()
# #     return base64.b64encode(sig).decode('utf-8')
