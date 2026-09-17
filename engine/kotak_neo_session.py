import os
import sys
import json
import pyotp
import socket

# Force IPv4 socket resolution globally to eliminate IPv6 dual-stack mismatch with Kotak API gateway
old_getaddrinfo = socket.getaddrinfo
def _force_ipv4(*args, **kwargs):
    return [r for r in old_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]
socket.getaddrinfo = _force_ipv4

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from neo_api_client import NeoAPI

CONFIG_PATH = os.path.join(ENGINE_DIR, "kotak_config.json")
SESSION_CACHE_PATH = os.path.join(ENGINE_DIR, "shared_session.json")

def load_config():
    """
    Loads config from local kotak_config.json or environment variables (GitHub Actions secrets).
    """
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass

    # Environment variables take precedence for cloud runners
    return {
        "consumer_key": os.environ.get("KOTAK_CONSUMER_KEY", cfg.get("consumer_key", "REDACTED")),
        "mobile_number": os.environ.get("KOTAK_MOBILE_NUMBER", cfg.get("mobile_number", "REDACTED")),
        "ucc": os.environ.get("KOTAK_UCC", cfg.get("ucc", "REDACTED")),
        "mpin": os.environ.get("KOTAK_MPIN", cfg.get("mpin", "REDACTED")),
        "totp_secret": os.environ.get("KOTAK_TOTP_SECRET", cfg.get("totp_secret", "REDACTED")),
        "environment": os.environ.get("KOTAK_ENV", cfg.get("environment", "prod"))
    }

def get_kotak_session():
    """
    Returns an authenticated Kotak NeoAPI client session.
    Uses cached session if valid, otherwise performs automated TOTP login.
    """
    cfg = load_config()
    consumer_key = cfg["consumer_key"]
    mobile_number = cfg["mobile_number"]
    ucc = cfg["ucc"]
    mpin = cfg["mpin"]
    totp_secret = cfg["totp_secret"]

    client = NeoAPI(environment="prod", consumer_key=consumer_key)

    # 1. Check for valid cached session token
    if os.path.exists(SESSION_CACHE_PATH):
        try:
            with open(SESSION_CACHE_PATH, "r") as f:
                cache = json.load(f)
            
            if cache.get("edit_token") and cache.get("edit_sid"):
                client.configuration.view_token = cache.get("view_token")
                client.configuration.sid = cache.get("sid")
                client.configuration.edit_token = cache.get("edit_token")
                client.configuration.edit_sid = cache.get("edit_sid")
                client.configuration.edit_rid = cache.get("edit_rid")
                client.configuration.serverId = cache.get("serverId", "")
                client.configuration.data_center = cache.get("data_center", "E21")
                client.configuration.base_url = cache.get("base_url", "https://e21.kotaksecurities.com")

                try:
                    probe = client.quotes([{"instrument_token": "Nifty 50", "exchange_segment": "nse_cm"}])
                    if isinstance(probe, list) and len(probe) > 0:
                        print(f"[+] Reused active Kotak Neo shared session for UCC: {ucc}")
                        return client
                except Exception:
                    print("[-] Cached session expired. Re-authenticating via TOTP...")
        except Exception:
            pass

    # 2. Re-authenticate via TOTP
    if not totp_secret:
        raise ValueError("TOTP secret not found in config or environment variables!")

    totp_code = pyotp.TOTP(totp_secret).now()
    print(f"[*] Generated live TOTP code for UCC: {ucc}")
    res_totp = client.totp_login(mobile_number=mobile_number, ucc=ucc, totp=totp_code)

    if not isinstance(res_totp, dict) or not res_totp.get("data") or not res_totp.get("data").get("token"):
        raise Exception(f"Kotak TOTP Login failed: {res_totp}")

    res_mpin = client.totp_validate(mpin=mpin)
    if not isinstance(res_mpin, dict) or not res_mpin.get("data") or not res_mpin.get("data").get("token"):
        raise Exception(f"Kotak MPIN Validation failed: {res_mpin}")

    cache_data = {
        "view_token": client.configuration.view_token,
        "sid": client.configuration.sid,
        "edit_token": client.configuration.edit_token,
        "edit_sid": client.configuration.edit_sid,
        "edit_rid": client.configuration.edit_rid,
        "serverId": client.configuration.serverId,
        "data_center": client.configuration.data_center,
        "base_url": client.configuration.base_url
    }
    try:
        with open(SESSION_CACHE_PATH, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass

    user_name = res_mpin.get('data', {}).get('greetingName', 'User')
    print(f"[+] Successfully authenticated Kotak Neo session for UCC: {ucc} ({user_name})")
    return client

if __name__ == "__main__":
    session = get_kotak_session()
    print("[+] Session test successful.")
