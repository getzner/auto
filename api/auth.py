import os
import secrets
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def verify(credentials: HTTPBasicCredentials = Depends(security)):
    """
    HTTP Basic Auth verification logic moved here to avoid circular imports.
    Used by server.py and config_router.py.
    """
    req_user = os.getenv("DASHBOARD_USER", "admin")
    req_pass = os.getenv("DASHBOARD_PASS", "admin123")
    
    ok_user = secrets.compare_digest(credentials.username, req_user)
    ok_pass = secrets.compare_digest(credentials.password, req_pass)
    
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
