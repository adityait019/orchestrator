# services/file_service.py

import time
import hashlib
import hmac
from urllib.parse import quote
import uuid

class FileService:
    """
    Responsible for:
    - make_signed_url
    - verify_sig
    - signature binding to tenant + user + session + file
    """

    def __init__(self, signing_secret: str, base_url: str, ttl: int = 600):
        self.secret = signing_secret
        self.base_url = base_url.rstrip("/")
        self.ttl = ttl

    # ------------------------------------------------
    # Internal signing
    # ------------------------------------------------

    def _sign(self, path: str, exp: int) -> str:
        """
        Sign the *exact request path* + expiry.
        This prevents token reuse across users or sessions.
        """
        msg = f"{path}:{exp}".encode("utf-8")

        return hmac.new(
            self.secret.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

    # ------------------------------------------------
    # Public API
    # ------------------------------------------------

    def make_signed_url(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        file_id: str,
        filename: str,
    ) -> str:
        """
        Produces a user-scoped, session-scoped signed URL.
        """
        exp = int(time.time()) + self.ttl
        encoded_filename = quote(filename, safe="")
        if not tenant_id:
            tenant_id=str(uuid.uuid4())
        path = (
            f"/files/{tenant_id}"
            f"/{user_id}"
            f"/{session_id}"
            f"/{file_id}"
            f"/{encoded_filename}"
        )

        sig = self._sign(path, exp)

        return f"{self.base_url}{path}?exp={exp}&sig={sig}"

    def verify_sig(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        file_id: str,
        filename: str,
        exp: int,
        sig: str,
    ) -> bool:
        """
        Verifies:
        - URL has not expired
        - Signature matches path + expiry
        """
        if exp < int(time.time()):
            return False

        encoded_filename = quote(filename, safe="")

        path = (
            f"/files/{tenant_id}"
            f"/{user_id}"
            f"/{session_id}"
            f"/{file_id}"
            f"/{encoded_filename}"
        )

        expected_sig = self._sign(path, exp)
        return hmac.compare_digest(expected_sig, sig)