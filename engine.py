import asyncio
import random
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetFullChatRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import DataJSON
from config import API_ID, API_HASH
from database import increment_payloads

active_logins = {}

async def send_otp(user_id: int, phone: str):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    sent = await client.send_code_request(phone)
    active_logins[user_id] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}

async def verify_otp(user_id: int, otp_code: str):
    login_data = active_logins.get(user_id)
    if not login_data:
        return "EXPIRED", None
    client, phone, phone_code_hash = login_data["client"], login_data["phone"], login_data["phone_code_hash"]
    try:
        await client.sign_in(phone=phone, code=otp_code, phone_code_hash=phone_code_hash)
        session_str = client.session.save()
        await client.disconnect()
        del active_logins[user_id]
        return "SUCCESS", session_str
    except SessionPasswordNeededError:
        return "2FA_REQUIRED", None
    except Exception as e:
        await client.disconnect()
        del active_logins[user_id]
        return f"ERROR: {str(e)}", None

async def verify_2fa(user_id: int, password: str):
    login_data = active_logins.get(user_id)
    if not login_data:
        return "EXPIRED", None
    client = login_data["client"]
    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        await client.disconnect()
        del active_logins[user_id]
        return "SUCCESS", session_str
    except Exception as e:
        await client.disconnect()
        del active_logins[user_id]
        return f"ERROR: {str(e)}", None

async def execute_channel_requests(user_id: int, accounts: list, target: str, status_message):
    total, success, failed = len(accounts), 0, 0
    for idx, acc in enumerate(accounts, start=1):
        _, _, session_str = acc
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await client.connect()
            if "+" in target or "joinchat/" in target:
                invite_hash = target.split("+")[-1].split("joinchat/")[-1].strip("/")
                await client(ImportChatInviteRequest(invite_hash))
            else:
                username = target.replace("https://t.me/", "").replace("@", "").strip("/")
                await client(JoinChannelRequest(username))
            success += 1
        except Exception:
            failed += 1
        finally:
            await client.disconnect()
        try:
            await status_message.edit_text(f"📊 Progress: {idx}/{total} | Success: {success} | Failed: {failed}")
        except Exception:
            pass
        await asyncio.sleep(2)
    if success > 0:
        await increment_payloads(user_id, success)
    return success, failed

async def execute_vc_action(user_id: int, accounts: list, target: str, mode: str, status_message):
    total, success, failed = len(accounts), 0, 0
    for idx, acc in enumerate(accounts, start=1):
        _, _, session_str = acc
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await client.connect()
            entity = await client.get_entity(target)
            try:
                full_chat = await client(GetFullChannelRequest(entity))
                input_call = full_chat.full_chat.call
            except Exception:
                full_chat = await client(GetFullChatRequest(entity.id))
                input_call = full_chat.full_chat.call
            if input_call:
                me = await client.get_me()
                params = DataJSON(data=f'{{"ufrag":"m2m","pwd":"m2m","fingerprints":[],"ssrc":{random.randint(100000, 999999)}}}')
                try:
                    await client(JoinGroupCallRequest(call=input_call, join_as=me, params=params, muted=True))
                except Exception:
                    pass
                if mode == "live_listen":
                    await asyncio.sleep(3)
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        finally:
            await client.disconnect()
        try:
            await status_message.edit_text(f"🎙️ VC Progress: {idx}/{total} | Connected: {success} | Failed: {failed}")
        except Exception:
            pass
        await asyncio.sleep(2)
    if success > 0:
        await increment_payloads(user_id, success)
    return success, failed
    
