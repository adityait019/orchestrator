#services/file_service.py

import time
import hashlib
import hmac
from urllib.parse import quote

class FileService:
    """Responsible for 
    - _signed_token
    - make_signed_url
    - verify_sig
    - get_file endpoint logic"""

    def __init__(self,signing_secret,base_url,ttl:int=600):
        self.secret=signing_secret
        self.base_url=base_url.rstrip("/")
        self.ttl=ttl



    def _sign(self,file_id:str,filename:str,exp:int)->str:
        msg=f"{file_id}:{filename}:{exp}".encode("utf-8")

        return hmac.new(
            self.secret.encode("utf-8"),
            msg,
            hashlib.sha256
        ).hexdigest()
    

    def make_signed_url(self,file_id:str,filename:str)->str:
        exp=int(time.time())+self.ttl

        encoded_filename=quote(filename,safe="")

        sig=self._sign(file_id,filename,exp)
        return f"{self.base_url}/files/{file_id}/{filename}?exp={exp}&sig={sig}"
    

    def verify_sig(self,file_id: str, filename: str, exp: int, sig: str) -> bool:
        if exp < int(time.time()):
            return False
        
        expected_sig=self._sign(file_id,filename,exp)
        return hmac.compare_digest(sig, expected_sig)
    