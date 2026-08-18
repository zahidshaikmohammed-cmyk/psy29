"""Minimal DhanHQ v2 HTTP client for PSY29 live acquisition.

Authentication failures are handled once per client/cycle so one bad token can
never make a 29-symbol cycle hang for many minutes. Tokens are never logged.
"""
from __future__ import annotations
import os, random, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
import requests
BASE_URL="https://api.dhan.co/v2"; AUTH_URL="https://auth.dhan.co/app/generateAccessToken"; MAX_RETRY_AFTER_SECONDS=30.0; REQUEST_TIMEOUT_SECONDS=12

def _retry_after_seconds(response):
    if response is None:return None
    value=response.headers.get("Retry-After")
    if not value:return None
    try:return max(0.0,min(float(value),MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        try:
            target=parsedate_to_datetime(value)
            if target.tzinfo is None:target=target.replace(tzinfo=timezone.utc)
            return max(0.0,min((target-datetime.now(timezone.utc)).total_seconds(),MAX_RETRY_AFTER_SECONDS))
        except (TypeError,ValueError,OverflowError):return None

def _backoff(attempt,base):return base*(2**attempt)+random.uniform(0.0,min(0.25,base))
def _response_error(response):
    if response is None:return "DHAN_HTTP_UNKNOWN"
    try:body=response.json()
    except ValueError:body=response.text.strip()
    return f"DHAN_HTTP_{response.status_code}: {body}"
def _is_invalid_token(response,body=None):
    if response is not None and response.status_code in (401,403):return True
    text=str(body if body is not None else "").lower()
    return any(code.lower() in text for code in ("DH-901","DH-906","807","808","809","invalid token","expired"))

class DhanClient:
    def __init__(self,client_id=None,access_token=None):
        self.client_id=client_id or os.getenv("DHAN_CLIENT_ID");self.access_token=access_token or os.getenv("DHAN_ACCESS_TOKEN");self._last_auth_refresh=0.0;self._auth_failed=False
        if not self.access_token:raise RuntimeError("DHAN_ACCESS_TOKEN is not configured")
        print("PSY29 DHAN client initialized; access token present.",flush=True)
    @property
    def headers(self):
        h={"Accept":"application/json","Content-Type":"application/json","access-token":self.access_token or ""}
        if self.client_id:h["client-id"]=self.client_id
        return h
    def _generate_totp_token(self):
        client_id=self.client_id or os.getenv("DHAN_CLIENT_ID");pin=os.getenv("DHAN_PIN");secret=os.getenv("DHAN_TOTP_SECRET")
        if not client_id:raise RuntimeError("DHAN_CLIENT_ID is required for automatic token recovery")
        if not pin or not secret:raise RuntimeError("DHAN token rejected and automatic recovery is unavailable: configure DHAN_PIN and DHAN_TOTP_SECRET")
        try:import pyotp
        except ImportError as exc:raise RuntimeError("pyotp is required for automatic Dhan token recovery") from exc
        totp=pyotp.TOTP(secret).now();r=requests.post(AUTH_URL,params={"dhanClientId":client_id,"pin":pin,"totp":totp},timeout=12)
        if r.status_code>=400:raise RuntimeError(f"DHAN_AUTH_HTTP_{r.status_code}: {r.text.strip()}")
        try:body=r.json()
        except ValueError as exc:raise RuntimeError("DHAN_AUTH_INVALID_RESPONSE") from exc
        token=body.get("accessToken")
        if not token:raise RuntimeError(f"DHAN_AUTH_NO_ACCESS_TOKEN: {body}")
        self.access_token=str(token);self._last_auth_refresh=time.time();self._auth_failed=False;print("PSY29 DHAN authentication: fresh access token generated.",flush=True);return self.access_token
    def _recover_authentication(self):
        if time.time()-self._last_auth_refresh<10:return
        self._generate_totp_token()
    def post(self,path,payload,timeout=15,retries=2,backoff_seconds=1.0):
        if self._auth_failed:raise RuntimeError("DHAN_AUTH_CIRCUIT_OPEN: previous authentication attempt failed; aborting this cycle")
        auth_retried=False;effective_timeout=min(max(3,int(timeout)),REQUEST_TIMEOUT_SECONDS)
        for attempt in range(retries+1):
            started=time.time()
            try:
                response=requests.post(f"{BASE_URL}{path}",headers=self.headers,json=payload,timeout=effective_timeout)
                elapsed=time.time()-started
                try:data=response.json()
                except ValueError:data=None
                if response.status_code>=400:
                    if _is_invalid_token(response,data):
                        if not auth_retried:
                            auth_retried=True;print(f"PSY29 DHAN AUTH REJECTED on {path}; recovering once.",flush=True)
                            try:self._recover_authentication()
                            except Exception as exc:self._auth_failed=True;raise RuntimeError(f"DHAN_AUTH_RECOVERY_FAILED: {exc}") from exc
                            continue
                        self._auth_failed=True;raise RuntimeError(_response_error(response))
                    if response.status_code==429 or response.status_code>=500:
                        if attempt>=retries:raise RuntimeError(_response_error(response))
                        delay=_retry_after_seconds(response) or _backoff(attempt,backoff_seconds);print(f"PSY29 DHAN transient HTTP {response.status_code}; retrying in {delay:.2f}s",flush=True);time.sleep(delay);continue
                    raise RuntimeError(_response_error(response))
                if isinstance(data,dict) and data.get("status")=="failure":
                    if _is_invalid_token(response,data):
                        if not auth_retried:
                            auth_retried=True;print(f"PSY29 DHAN AUTH REJECTED on {path}; recovering once.",flush=True)
                            try:self._recover_authentication()
                            except Exception as exc:self._auth_failed=True;raise RuntimeError(f"DHAN_AUTH_RECOVERY_FAILED: {exc}") from exc
                            continue
                        self._auth_failed=True;raise RuntimeError(f"DHAN_RESPONSE_FAILURE: {data}")
                    raise RuntimeError(f"DHAN_RESPONSE_FAILURE: {data}")
                if not isinstance(data,dict):raise RuntimeError(f"DHAN_INVALID_RESPONSE: expected object, got {type(data).__name__}")
                print(f"PSY29 DHAN request PASS {path} in {elapsed:.2f}s",flush=True);return data
            except (requests.Timeout,requests.ConnectionError) as exc:
                if attempt>=retries:raise RuntimeError(f"DHAN_NETWORK_TIMEOUT_OR_CONNECTION: {exc}") from exc
                delay=_backoff(attempt,backoff_seconds);print(f"PSY29 DHAN network error; retrying in {delay:.2f}s: {exc}",flush=True);time.sleep(delay)
        raise RuntimeError("DHAN request failed without a response")
