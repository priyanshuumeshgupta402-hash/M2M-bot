import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from config import BOT_TOKEN, ADMIN_ID, BOT_USERNAME, CREATOR_TAG
from database import init_db, get_or_create_user, add_account_session, get_all_accounts, delete_account_session, create_redeem_code, use_redeem_code
from engine import send_otp, verify_otp, verify_2fa, execute_channel_requests, execute_vc_action
from keep_alive import keep_alive

WAIT_PHONE, WAIT_OTP, WAIT_2FA, WAIT_REDEEM, WAIT_TARGET_LINK, WAIT_ACCOUNT_COUNT, WAIT_VC_TARGET, WAIT_VC_COUNT = range(8)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Profile", callback_data="menu_profile")],
        [InlineKeyboardButton("Add Account", callback_data="menu_add_account"), InlineKeyboardButton("Setting", callback_data="menu_setting")],
        [InlineKeyboardButton("Plans", callback_data="menu_plans")],
        [InlineKeyboardButton("Redeem", callback_data="menu_redeem"), InlineKeyboardButton("Refer", callback_data="menu_refer")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_main")]])

def get_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Send Channel Request", callback_data="op_channel_req")],
        [InlineKeyboardButton("🎙️ Join VC", callback_data="op_join_vc"), InlineKeyboardButton("🔴 Live VC / Listen", callback_data="op_live_vc")],
        [InlineKeyboardButton("👥 Account Manager", callback_data="op_acc_manager")],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_main")]
    ])

async def get_dashboard_text(user_id: int, referred_by: int = None):
    user = await get_or_create_user(user_id, referred_by)
    accounts = await get_all_accounts()
    return (
        f"📊 <b>AFFILIATE METRICS</b>\n"
        f"⭐ Bot by {CREATOR_TAG}\n"
        f"🪙 Referral Earnings: {user['refers']} refers / {user['points']} pts\n"
        f"💎 Plan: <b>{user['plan']}</b> ({user['expiry']})\n"
        f"📱 Total Bot IDs: <b>{len(accounts)}</b> | 🚀 Payloads Sent: <b>{user['payloads_sent']}</b>\n"
        f"──────────────────────\n"
        f"Select an operation below to continue."
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referred_by = int(context.args[0].replace("ref_", "")) if context.args and context.args[0].startswith("ref_") else None
    text = await get_dashboard_text(user_id, referred_by)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def gen_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or len(context.args) < 3:
        return
    code, plan, expiry = context.args[0], context.args[1], context.args[2]
    pts = int(context.args[3]) if len(context.args) > 3 else 0
    await create_redeem_code(code, plan, expiry, pts)
    await update.message.reply_text(f"✅ Code Created: <code>{code}</code> ({plan})", parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id, data = query.from_user.id, query.data

    if data == "back_main":
        text = await get_dashboard_text(user_id)
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
        return ConversationHandler.END

    elif data == "menu_profile":
        user, accounts = await get_or_create_user(user_id), await get_all_accounts()
        await query.edit_message_text(
            f"👤 <b>USER PROFILE</b>\n🆔 ID: <code>{user_id}</code>\n💎 Plan: {user['plan']} ({user['expiry']})\n📱 Total Bot IDs: {len(accounts)}\n🚀 Payloads: {user['payloads_sent']}",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )

    elif data == "menu_setting":
        user = await get_or_create_user(user_id)
        if "Locked" in user['plan']:
            await query.answer("❌ Purchase plan first!", show_alert=True)
            return ConversationHandler.END
        await query.edit_message_text("⚙️ <b>AUTOMATION SETTINGS</b>", reply_markup=get_settings_keyboard(), parse_mode="HTML")

    elif data == "menu_plans":
        await query.edit_message_text(
            f"💎 <b>SUBSCRIPTION PLANS</b>\n🥉 3 Days: ₹250\n🥈 7 Days: ₹599\n🥇 1 Month: ₹1299\n\n📩 Contact {CREATOR_TAG} to buy.",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )

    elif data == "menu_refer":
        user = await get_or_create_user(user_id)
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        await query.edit_message_text(f"🔗 <b>REFERRAL</b>\n<code>{ref_link}</code>", reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif data == "menu_add_account":
        await query.edit_message_text("➕ Send phone number (e.g. <code>+919876543210</code>):", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return WAIT_PHONE

    elif data == "menu_redeem":
        await query.edit_message_text("🎁 Send your redeem code:", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return WAIT_REDEEM

    elif data == "op_acc_manager":
        accounts = await get_all_accounts()
        if not accounts:
            await query.edit_message_text("❌ No accounts added in bot.", reply_markup=get_settings_keyboard())
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(f"🗑️ Remove {phone}", callback_data=f"del_acc_{a_id}")] for a_id, phone, _ in accounts]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="menu_setting")])
        await query.edit_message_text("👥 <b>ACCOUNTS MANAGER</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif data.startswith("del_acc_"):
        await delete_account_session(int(data.replace("del_acc_", "")), user_id)
        accounts = await get_all_accounts()
        kb = [[InlineKeyboardButton(f"🗑️ Remove {phone}", callback_data=f"del_acc_{a_id}")] for a_id, phone, _ in accounts]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="menu_setting")])
        await query.edit_message_text("✅ Account deleted.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "op_channel_req":
        accounts = await get_all_accounts()
        if not accounts:
            await query.answer("❌ No accounts available in bot!", show_alert=True)
            return ConversationHandler.END
        await query.edit_message_text("📢 Send target link or @username:", reply_markup=get_back_keyboard())
        return WAIT_TARGET_LINK

    elif data in ["op_join_vc", "op_live_vc"]:
        accounts = await get_all_accounts()
        if not accounts:
            await query.answer("❌ No accounts available in bot!", show_alert=True)
            return ConversationHandler.END
        context.user_data["vc_mode"] = "join_vc" if data == "op_join_vc" else "live_listen"
        await query.edit_message_text("🎙️ Send target VC link or @username:", reply_markup=get_back_keyboard())
        return WAIT_VC_TARGET

    return ConversationHandler.END

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Sending OTP...")
    try:
        await send_otp(update.effective_user.id, update.message.text.strip())
        context.user_data["phone"] = update.message.text.strip()
        await msg.edit_text("📩 Send OTP with spaces (e.g. <code>1 2 3 4 5</code>):", parse_mode="HTML")
        return WAIT_OTP
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}", reply_markup=get_back_keyboard())
        return ConversationHandler.END

async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status, sess = await verify_otp(update.effective_user.id, update.message.text.replace(" ", "").strip())
    if status == "SUCCESS":
        await add_account_session(update.effective_user.id, context.user_data.get("phone"), sess)
        await update.message.reply_text("✅ Account added to bot pool!", reply_markup=get_back_keyboard())
        return ConversationHandler.END
    elif status == "2FA_REQUIRED":
        await update.message.reply_text("🔐 Send 2FA password:")
        return WAIT_2FA
    await update.message.reply_text(f"❌ Failed: {status}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status, sess = await verify_2fa(update.effective_user.id, update.message.text.strip())
    if status == "SUCCESS":
        await add_account_session(update.effective_user.id, context.user_data.get("phone"), sess)
        await update.message.reply_text("✅ Account added with 2FA!", reply_markup=get_back_keyboard())
    else:
        await update.message.reply_text(f"❌ Failed: {status}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def receive_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = await use_redeem_code(update.effective_user.id, update.message.text.strip())
    text = await get_dashboard_text(update.effective_user.id)
    if res:
        await update.message.reply_text(f"🎉 Activated: {res[0]} ({res[1]})\n\n{text}", reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Invalid code! Try again or click back:", reply_markup=get_back_keyboard())
        return WAIT_REDEEM

async def receive_target_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["target_link"] = update.message.text.strip()
    accounts = await get_all_accounts()
    await update.message.reply_text(f"🔢 Total accounts in bot: {len(accounts)}. Send how many members to join (or type ALL):", reply_markup=get_back_keyboard())
    return WAIT_ACCOUNT_COUNT

async def receive_account_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    accounts = await get_all_accounts()
    if text != "ALL":
        try:
            accounts = accounts[:max(1, int(text))]
        except ValueError:
            pass
    msg = await update.message.reply_text("🚀 Running task across accounts...")
    s, f = await execute_channel_requests(user_id, accounts, context.user_data.get("target_link"), msg)
    await update.message.reply_text(f"✅ Done! Success: {s} | Failed: {f}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def receive_vc_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["vc_target"] = update.message.text.strip()
    accounts = await get_all_accounts()
    await update.message.reply_text(f"🔢 Total accounts in bot: {len(accounts)}. Send how many accounts to join VC/Live (or type ALL):", reply_markup=get_back_keyboard())
    return WAIT_VC_COUNT

async def receive_vc_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    accounts = await get_all_accounts()
    if text != "ALL":
        try:
            accounts = accounts[:max(1, int(text))]
        except ValueError:
            pass
    msg = await update.message.reply_text("🎙️ Joining VC/Live instantly...")
    s, f = await execute_vc_action(user_id, accounts, context.user_data.get("vc_target"), context.user_data.get("vc_mode", "join_vc"), msg)
    await update.message.reply_text(f"✅ VC Done! Connected: {s} | Failed: {f}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).post_init(lambda a: init_db()).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone), CallbackQueryHandler(button_handler)],
            WAIT_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp), CallbackQueryHandler(button_handler)],
            WAIT_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa), CallbackQueryHandler(button_handler)],
            WAIT_REDEEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_redeem), CallbackQueryHandler(button_handler)],
            WAIT_TARGET_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target_link), CallbackQueryHandler(button_handler)],
            WAIT_ACCOUNT_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_account_count), CallbackQueryHandler(button_handler)],
            WAIT_VC_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vc_target), CallbackQueryHandler(button_handler)],
            WAIT_VC_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vc_count), CallbackQueryHandler(button_handler)],
        },
        fallbacks=[CommandHandler("start", start_cmd), CallbackQueryHandler(button_handler)],
        per_message=False
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("gen_code", gen_code_cmd))
    app.add_handler(conv)
    print("🔥 M2M Control Bot is live!")
    app.run_polling()

if __name__ == "__main__":
    main()
                                     
