import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from config import BOT_TOKEN, ADMIN_ID, BOT_USERNAME, CREATOR_TAG
from database import init_db, get_or_create_user, add_account_session, get_all_accounts, create_redeem_code, use_redeem_code
from engine import send_otp, verify_otp, verify_2fa, execute_channel_requests, execute_vc_action, leave_vc_action
from keep_alive import keep_alive

WAIT_PHONE, WAIT_OTP, WAIT_2FA, WAIT_REDEEM, WAIT_TARGET_LINK, WAIT_ACCOUNT_COUNT, WAIT_VC_TARGET, WAIT_VC_COUNT = range(8)

BANNER_IMAGE_URL = "https://i.ibb.co/tTZmsWrQ/62270897-7b06-4f65-b0cf-958f37cf6ba9.png"

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 My Profile", callback_data="menu_profile"), InlineKeyboardButton("🎁 Redeem Code", callback_data="menu_redeem")],
        [InlineKeyboardButton("🟢 Add Account", callback_data="menu_add_account"), InlineKeyboardButton("🔵 Automation Setting", callback_data="menu_setting")],
        [InlineKeyboardButton("💎 VIP Plans", callback_data="menu_plans"), InlineKeyboardButton("🔗 Refer & Earn", callback_data="menu_refer")],
        [InlineKeyboardButton("🛑 Leave VC / Disconnect All", callback_data="op_leave_vc")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_main")]])

def get_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Send Channel Request", callback_data="op_channel_req")],
        [InlineKeyboardButton("🎙️ Join Voice Chat (VC)", callback_data="op_join_vc")],
        [InlineKeyboardButton("🔴 Live VC / Listen Mode", callback_data="op_live_vc")],
        [InlineKeyboardButton("🛑 Leave VC / Disconnect All", callback_data="op_leave_vc")],
        [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_main")]
    ])

async def get_dashboard_text(user_id: int, referred_by: int = None):
    user = await get_or_create_user(user_id, referred_by)
    accounts = await get_all_accounts()
    return (
        f"<b>🌟 ⚡ M2M AUTOMATION CONTROL PANEL ⚡ 🌟</b>\n"
        f"<b>──────────────────────────────</b>\n"
        f"<b>🤖 Developer:</b> {CREATOR_TAG}\n"
        f"<b>💎 Current Plan:</b> <code>{user['plan']}</code>\n"
        f"<b>⏳ Validity:</b> {user['expiry']}\n"
        f"<b>📱 Active Bot Pool IDs:</b> <b>{len(accounts)} Accounts</b>\n"
        f"<b>🚀 Total Payloads Delivered:</b> <code>{user['payloads_sent']}</code>\n"
        f"<b>🪙 Referral Rewards:</b> {user['refers']} refers ({user['points']} pts)\n"
        f"<b>──────────────────────────────</b>\n"
        f"<b>👇 Choose an option from the menu below:</b>"
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referred_by = int(context.args[0].replace("ref_", "")) if context.args and context.args[0].startswith("ref_") else None
    text = await get_dashboard_text(user_id, referred_by)
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.reply_photo(photo=BANNER_IMAGE_URL, caption=text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
            await update.callback_query.message.delete()
        except Exception:
            await update.callback_query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_photo(photo=BANNER_IMAGE_URL, caption=text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def gen_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or len(context.args) < 3:
        return
    code, plan, expiry = context.args[0], context.args[1], context.args[2]
    pts = int(context.args[3]) if len(context.args) > 3 else 0
    await create_redeem_code(code, plan, expiry, pts)
    await update.message.reply_text(f"<b>✅ Admin Success: Redeem Code <code>{code}</code> created for <b>{plan}</b>!</b>", parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id, data = query.from_user.id, query.data

    if data == "back_main":
        text = await get_dashboard_text(user_id)
        try:
            await query.message.reply_photo(photo=BANNER_IMAGE_URL, caption=text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
            await query.message.delete()
        except Exception:
            await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
        return ConversationHandler.END

    elif data == "menu_profile":
        user, accounts = await get_or_create_user(user_id), await get_all_accounts()
        profile_text = (
            f"<b>👤 USER PROFILE DASHBOARD</b>\n"
            f"<b>──────────────────────────────</b>\n"
            f"<b>🆔 Telegram ID:</b> <code>{user_id}</code>\n"
            f"<b>💎 Active Plan:</b> {user['plan']}\n"
            f"<b>⏳ Plan Expiry:</b> {user['expiry']}\n"
            f"<b>🚀 Total Tasks Executed:</b> {user['payloads_sent']}\n"
            f"<b>👥 Total Referrals:</b> {user['refers']} users\n"
            f"<b>🪙 Earned Points:</b> {user['points']} pts"
        )
        await query.edit_message_caption(caption=profile_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif data == "menu_setting":
        user = await get_or_create_user(user_id)
        if "Locked" in user['plan']:
            await query.answer("❌ Access Denied! Please purchase or redeem a plan first.", show_alert=True)
            return ConversationHandler.END
        await query.edit_message_caption(
            caption=f"<b>⚙️ AUTOMATION CONTROL CENTER</b>\n<b>──────────────────────────────</b>\n<b>Select your desired automation operation below:</b>",
            reply_markup=get_settings_keyboard(), parse_mode="HTML"
        )

    elif data == "menu_plans":
        plans_text = (
            f"<b>💎 VIP SUBSCRIPTION PLANS & PRICING</b>\n"
            f"<b>──────────────────────────────</b>\n"
            f"🥉 <b>3 Days Trial Pass:</b> ₹250\n"
            f"🥈 <b>7 Days Pro Pass:</b> ₹599\n"
            f"🥇 <b>1 Month Ultimate Pass:</b> ₹1299\n\n"
            f"<b>📩 To purchase a plan instantly, contact developer:</b> <b>{CREATOR_TAG}</b>"
        )
        await query.edit_message_caption(caption=plans_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif data == "menu_refer":
        user = await get_or_create_user(user_id)
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        refer_text = (
            f"<b>🔗 REFER & EARN PROGRAM</b>\n"
            f"<b>──────────────────────────────</b>\n"
            f"<b>Share your unique referral link with friends and earn +4 points per join!</b>\n\n"
            f"<b>📌 Your Personal Link:</b>\n<code>{ref_link}</code>"
        )
        await query.edit_message_caption(caption=refer_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif data == "menu_add_account":
        await query.edit_message_caption(
            caption=f"<b>➕ ADD ACCOUNT TO POOL</b>\n<b>──────────────────────────────</b>\n<b>Please send your Telegram phone number with country code (e.g., +919876543210):</b>",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )
        return WAIT_PHONE

    elif data == "menu_redeem":
        await query.edit_message_caption(
            caption=f"<b>🎁 REDEEM YOUR VOUCHER CODE</b>\n<b>──────────────────────────────</b>\n<b>Please send your active redeem code below:</b>",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )
        return WAIT_REDEEM

    elif data == "op_leave_vc":
        count = await leave_vc_action(user_id)
        await query.answer(f"🛑 Success! Disconnected {count} accounts from VC/Live.", show_alert=True)
        return ConversationHandler.END

    elif data == "op_channel_req":
        accounts = await get_all_accounts()
        if not accounts:
            await query.answer("❌ No accounts available in the bot pool!", show_alert=True)
            return ConversationHandler.END
        await query.edit_message_caption(
            caption=f"<b>📢 CHANNEL JOIN AUTOMATION</b>\n<b>──────────────────────────────</b>\n<b>Send target channel invite link or username (e.g., @channelname):</b>",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )
        return WAIT_TARGET_LINK

    elif data in ["op_join_vc", "op_live_vc"]:
        accounts = await get_all_accounts()
        if not accounts:
            await query.answer("❌ No accounts available in the bot pool!", show_alert=True)
            return ConversationHandler.END
        context.user_data["vc_mode"] = "join_vc" if data == "op_join_vc" else "live_listen"
        await query.edit_message_caption(
            caption=f"<b>🎙️ VOICE CHAT / LIVE AUTOMATION</b>\n<b>──────────────────────────────</b>\n<b>Send target VC group link or @username:</b>",
            reply_markup=get_back_keyboard(), parse_mode="HTML"
        )
        return WAIT_VC_TARGET

    return ConversationHandler.END

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("<b>⏳ Requesting Telegram OTP verification code...</b>", parse_mode="HTML")
    try:
        await send_otp(update.effective_user.id, update.message.text.strip())
        context.user_data["phone"] = update.message.text.strip()
        await msg.edit_text("<b>📩 OTP sent successfully! Send the OTP with spaces (e.g., 1 2 3 4 5):</b>", parse_mode="HTML")
        return WAIT_OTP
    except Exception as e:
        await msg.edit_text(f"<b>❌ Error occurred: {e}</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return ConversationHandler.END

async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status, sess = await verify_otp(update.effective_user.id, update.message.text.replace(" ", "").strip())
    if status == "SUCCESS":
        await add_account_session(update.effective_user.id, context.user_data.get("phone"), sess)
        await update.message.reply_text("<b>✅ Account successfully added to the central pool!</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return ConversationHandler.END
    elif status == "2FA_REQUIRED":
        await update.message.reply_text("<b>🔐 Two-Step Verification enabled. Send your 2FA password:</b>", parse_mode="HTML")
        return WAIT_2FA
    await update.message.reply_text(f"<b>❌ Verification failed: {status}</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status, sess = await verify_2fa(update.effective_user.id, update.message.text.strip())
    if status == "SUCCESS":
        await add_account_session(update.effective_user.id, context.user_data.get("phone"), sess)
        await update.message.reply_text("<b>✅ Account successfully verified with 2FA and added!</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(f"<b>❌ 2FA verification failed: {status}</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def receive_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = await use_redeem_code(update.effective_user.id, update.message.text.strip())
    text = await get_dashboard_text(update.effective_user.id)
    if res:
        await update.message.reply_photo(photo=BANNER_IMAGE_URL, caption=f"<b>🎉 CONGRATULATIONS! Plan <b>{res[0]}</b> activated successfully!</b>\n\n{text}", reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
        return ConversationHandler.END
    else:
        await update.message.reply_text("<b>❌ Invalid or expired redeem code! Try again or click back:</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return WAIT_REDEEM

async def receive_target_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["target_link"] = update.message.text.strip()
    accounts = await get_all_accounts()
    await update.message.reply_text(f"<b>🔢 Total pool accounts: {len(accounts)}. Send how many members to join (or type ALL):</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
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
    msg = await update.message.reply_text("<b>🚀 Executing channel automation task...</b>", parse_mode="HTML")
    s, f = await execute_channel_requests(user_id, accounts, context.user_data.get("target_link"), msg)
    await update.message.reply_text(f"<b>✅ Task Completed!\n📊 Success: {s} | Failed: {f}</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def receive_vc_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["vc_target"] = update.message.text.strip()
    accounts = await get_all_accounts()
    await update.message.reply_text(f"<b>🔢 Total pool accounts: {len(accounts)}. Send how many accounts to join VC/Live (or type ALL):</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
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
    msg = await update.message.reply_text("<b>🎙️ Connecting accounts to Voice Chat / Live stream...</b>", parse_mode="HTML")
    s, f = await execute_vc_action(user_id, accounts, context.user_data.get("vc_target"), context.user_data.get("vc_mode", "join_vc"), msg)
    await update.message.reply_text(f"<b>✅ VC Connected Successfully!\n🟢 Active IDs in Live: {s} | Failed: {f}\n\n📌 Accounts will stay connected until you click 'Leave VC / Disconnect All' in Menu or Settings.</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")
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
    print("🔥 M2M Control Bot is live with persistent sessions and menu leave button!")
    app.run_polling()

if __name__ == "__main__":
    main()
    
