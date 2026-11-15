"""
Telegram Link Distributor Bot
Allows administrators to upload links and organize them into selectable options/buttons.
When users select an option, the bot delivers the corresponding link.
"""

import logging
import re
import time
from typing import Optional, Dict, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    ChatMemberUpdated,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import config
import database

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states for adding a link
WAITING_TITLE, WAITING_URL, WAITING_DESC = range(3)


# --- Helpers ---

def is_valid_url(url: str) -> bool:
    """Basic validation for URL format."""
    url_pattern = re.compile(
        r"^(https?://|t\.me/|tg://)[^\s/$.?#].[^\s]*$",
        re.IGNORECASE
    )
    return bool(url_pattern.match(url.strip()))


def build_user_menu_keyboard(is_admin_user: bool = False, in_group: bool = False, bot_username: str = "") -> InlineKeyboardMarkup:
    """Build the inline keyboard with all available link options."""
    options = database.get_options()
    keyboard = []

    # Two buttons per row for compact presentation, or one for long titles
    row = []
    for opt in options:
        # In groups, use direct Deep-Link button to bot's private chat so user receives link without cluttering the group
        if in_group and bot_username:
            btn = InlineKeyboardButton(text=f"📩 {opt['title']}", url=f"https://t.me/{bot_username}?start=req_{opt['id']}")
        else:
            btn = InlineKeyboardButton(text=f"👉 {opt['title']}", callback_data=f"get_link:{opt['id']}")

        if len(opt['title']) > 20:
            if row:
                keyboard.append(row)
                row = []
            keyboard.append([btn])
        else:
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)

    admin_controls = []
    # Only show admin panel button in private chats, not in public groups
    if is_admin_user and not in_group:
        admin_controls.append(InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"))
    if admin_controls:
        keyboard.append(admin_controls)

    return InlineKeyboardMarkup(keyboard)


# --- User Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start, /links, or /menu command from any user."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    is_group = chat.type in ["group", "supergroup"]

    # Register user in database
    database.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Get bot username for deep linking
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or ""

    # Check for deep-link link request: /start req_<option_id>
    if context.args and len(context.args) > 0 and context.args[0].startswith("req_"):
        try:
            option_id = int(context.args[0].replace("req_", ""))
            await process_link_request(update, context, option_id, user)
            return
        except ValueError:
            pass

    admin_status = config.is_admin(user.id)
    options = database.get_options()

    if not options:
        welcome_text = (
            f"👋 <b>{user.first_name}</b>, lehari me apka sawagat h! kya chahiye aapko?\n\n"
            "Filhal koi options ya links uplabdh nahi hain.\n"
        )
        if admin_status and not is_group:
            welcome_text += "\n🛠️ <i>As an admin, you can add links via the /admin panel or using /add.</i>"
        reply_markup = build_user_menu_keyboard(is_admin_user=admin_status, in_group=is_group, bot_username=bot_username)
        await update.message.reply_html(welcome_text, reply_markup=reply_markup)
        return

    welcome_text = (
        f"👋 <b>{user.first_name}</b>, lehari me apka sawagat h! kya chahiye aapko?\n\n"
        "Neeche diye gaye options me se select karein:"
    )
    reply_markup = build_user_menu_keyboard(is_admin_user=admin_status, in_group=is_group, bot_username=bot_username)
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)


# Cache to prevent duplicate welcome messages: (chat_id, user_id) -> timestamp
_welcomed_cache: Dict[Tuple[int, int], float] = {}
_left_cache: Dict[Tuple[int, int], float] = {}


def estimate_account_age(user_id: int) -> str:
    """Estimate approximate Telegram account registration year range from User ID."""
    if user_id < 200_000_000:
        return "~2013-2015 (Very Old Account)"
    elif user_id < 500_000_000:
        return "~2016-2017"
    elif user_id < 1_000_000_000:
        return "~2018-2019"
    elif user_id < 2_000_000_000:
        return "~2020-2021"
    elif user_id < 5_000_000_000:
        return "~2022-2023"
    elif user_id < 8_000_000_000:
        return "~2024-2025"
    else:
        return "~2025-2026 (Recent Account)"


async def send_osint_report_to_admin(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE, event_type: str = "Joined") -> None:
    """
    Send public OSINT intelligence card PRIVATELY to administrators only.
    Regular group members never see this card.
    """
    if not user or getattr(user, "is_bot", False):
        return

    chat_title = "Group"
    try:
        group_chat = await context.bot.get_chat(chat_id)
        if group_chat and group_chat.title:
            chat_title = group_chat.title
    except Exception:
        pass

    db_user = database.get_user(user.id)
    first_seen = db_user["first_seen"] if db_user and db_user.get("first_seen") else "Just now"
    past_warnings = database.get_warnings(chat_id, user.id)

    full_name = getattr(user, "full_name", None) or getattr(user, "first_name", "Unknown")
    username_str = f"@{user.username}" if getattr(user, "username", None) else "<i>None (No public username)</i>"
    profile_url = f"https://t.me/{user.username}" if getattr(user, "username", None) else f"tg://user?id={user.id}"
    is_premium = "Yes ⭐" if getattr(user, "is_premium", False) else "No"
    lang_code = getattr(user, "language_code", None) or "Not specified"
    est_age = estimate_account_age(user.id)
    id_type = "Legacy 32-bit ID (< 2022)" if user.id < 2_147_483_647 else "Modern 64-bit ID (>= 2022)"

    event_emoji = "🟢 User Joined" if event_type == "Joined" else "🔴 User Left"

    osint_card = (
        f"🕵️‍♂️ <b>Private OSINT Intelligence Report ({event_emoji})</b>\n\n"
        f"👥 <b>Group:</b> {chat_title}\n"
        f"👤 <b>Name:</b> {full_name}\n"
        f"🌐 <b>Username:</b> {username_str}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Profile Link:</b> <a href=\"{profile_url}\">Open Profile</a>\n"
        f"⭐ <b>Telegram Premium:</b> {is_premium}\n"
        f"🗣️ <b>Language Code:</b> <code>{lang_code}</code>\n"
        f"📅 <b>Est. Account Age:</b> {est_age} ({id_type})\n"
        f"🕒 <b>Recorded:</b> <code>{first_seen}</code>\n"
        f"⚠️ <b>Past Warnings:</b> <b>{past_warnings}/3</b>\n\n"
        "🔎 <i>Neeche diye gaye buttons se user ke public footprints check karein:</i>"
    )

    # Build Social & OSINT Lookup Buttons
    osint_buttons = []
    if getattr(user, "username", None):
        u = user.username
        osint_buttons.append([
            InlineKeyboardButton("🔍 Google OSINT", url=f"https://www.google.com/search?q=%22{u}%22"),
            InlineKeyboardButton("🐙 GitHub", url=f"https://github.com/{u}")
        ])
        osint_buttons.append([
            InlineKeyboardButton("📸 Instagram", url=f"https://instagram.com/{u}"),
            InlineKeyboardButton("🐦 X (Twitter)", url=f"https://x.com/{u}")
        ])
        osint_buttons.append([
            InlineKeyboardButton("🌐 Cross-Platform Search", url=f"https://www.google.com/search?q=site%3Ax.com+OR+site%3Ainstagram.com+OR+site%3Agithub.com+%22{u}%22")
        ])
    else:
        osint_buttons.append([
            InlineKeyboardButton("👤 Direct Telegram Profile", url=f"tg://user?id={user.id}")
        ])

    reply_markup = InlineKeyboardMarkup(osint_buttons)

    # Deliver PRIVATELY to configured admins
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=osint_card,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send private OSINT card to admin {admin_id}: {e}")


async def greet_user_in_chat(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE, in_group: bool = True) -> None:
    """Helper to send the welcome greeting with link options and prevent duplicate messages."""
    current_time = time.time()
    cache_key = (chat_id, user.id)

    # Ignore if user was already welcomed in this chat in the last 15 seconds
    if cache_key in _welcomed_cache and current_time - _welcomed_cache[cache_key] < 15:
        return
    _welcomed_cache[cache_key] = current_time

    # Clean old cache entries occasionally
    if len(_welcomed_cache) > 200:
        for k, v in list(_welcomed_cache.items()):
            if current_time - v > 60:
                _welcomed_cache.pop(k, None)

    database.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or ""

    welcome_text = (
        f"👋 <b>{user.first_name}</b>, lehari me apka sawagat h! kya chahiye aapko?\n\n"
        "Neeche diye gaye options me se select karein:"
    )
    reply_markup = build_user_menu_keyboard(
        is_admin_user=False,
        in_group=in_group,
        bot_username=bot_username
    )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to send welcome message in chat {chat_id}: {e}")

    # Send OSINT report PRIVATELY to Admin only when user joins a group (hidden from group members)
    if in_group:
        await send_osint_report_to_admin(chat_id=chat_id, user=user, context=context, event_type="Joined")


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome new members when they join via regular group service message."""
    if not update.message or not update.message.new_chat_members:
        return

    chat = update.effective_chat
    if not chat:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await greet_user_in_chat(chat.id, member, context, in_group=True)


async def chat_member_welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome new members in Supergroups/Groups via ChatMemberUpdated event."""
    chat_member_update = update.chat_member
    if not chat_member_update:
        return

    chat = chat_member_update.chat
    new_chat_member = chat_member_update.new_chat_member
    old_chat_member = chat_member_update.old_chat_member
    user = new_chat_member.user

    # Ignore bots
    if user.is_bot:
        return

    was_member = old_chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    is_member = new_chat_member.status in [ChatMember.MEMBER, ChatMember.RESTRICTED]

    # User joined the chat
    if not was_member and is_member:
        await greet_user_in_chat(chat.id, user, context, in_group=True)
    # User left or was removed from the chat
    elif was_member and new_chat_member.status in [ChatMember.LEFT, ChatMember.BANNED]:
        await handle_user_left_group(chat.id, user, context)


async def handle_user_left_group(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post public OSINT information card PRIVATELY to Admin when a user leaves the group."""
    if not user or getattr(user, "is_bot", False):
        return

    current_time = time.time()
    cache_key = (chat_id, user.id)
    if cache_key in _left_cache and current_time - _left_cache[cache_key] < 15:
        return
    _left_cache[cache_key] = current_time

    if len(_left_cache) > 200:
        for k, v in list(_left_cache.items()):
            if current_time - v > 60:
                _left_cache.pop(k, None)

    # Deliver PRIVATELY to Admin only (group members never see it)
    await send_osint_report_to_admin(chat_id=chat_id, user=user, context=context, event_type="Left")


async def handle_left_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle service messages when a member leaves a regular group."""
    if not update.message or not update.message.left_chat_member:
        return
    chat = update.effective_chat
    user = update.message.left_chat_member
    if chat:
        await handle_user_left_group(chat.id, user, context)


async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with greeting and menu when a user types anything in private chat."""
    chat = update.effective_chat
    if not chat or chat.type in ["group", "supergroup"]:
        return

    user = update.effective_user
    if not user:
        return

    admin_status = config.is_admin(user.id)
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or ""

    welcome_text = (
        f"👋 <b>{user.first_name}</b>, lehari me apka sawagat h! kya chahiye aapko?\n\n"
        "Neeche diye gaye options me se select karein:"
    )
    reply_markup = build_user_menu_keyboard(is_admin_user=admin_status, in_group=False, bot_username=bot_username)
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)


async def process_link_request(update: Update, context: ContextTypes.DEFAULT_TYPE, option_id: int, user, query=None) -> None:
    """Process a link request: deliver directly or notify admin for approval."""
    option = database.get_option(option_id)
    if not option:
        msg = "⚠️ This link is no longer available."
        if query:
            await query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
        return

    admin_status = config.is_admin(user.id)
    approval_needed = database.is_approval_required() and not admin_status

    if not approval_needed:
        # Deliver link directly
        database.record_click(user.id, option_id)
        title = option["title"]
        url = option["url"]
        description = option.get("description", "").strip()

        message_text = f"🎯 <b>{title}</b>\n\n"
        if description:
            message_text += f"📝 <i>{description}</i>\n\n"
        message_text += f"🔗 <b>Your Link:</b> <a href=\"{url}\">{url}</a>"

        action_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open Link Directly", url=url)],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ])

        if query:
            await query.message.reply_html(message_text, reply_markup=action_keyboard)
        elif update.message:
            await update.message.reply_html(message_text, reply_markup=action_keyboard)
    else:
        # Create approval request
        req_id = database.create_link_request(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            option_id=option_id
        )

        ack_text = (
            f"⏳ <b>Request Submitted!</b>\n\n"
            f"Aapne <b>{option['title']}</b> ke link ke liye request ki hai.\n\n"
            f"Jaise hi Admin ise approve karenge, aapko link turant yahan mil jayega! 🚀"
        )
        ack_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]])

        # If clicked in a group, show modal alert so link is not exposed and group menu stays intact
        in_group_query = False
        if query and query.message and query.message.chat:
            in_group_query = query.message.chat.type in ["group", "supergroup"]

        if in_group_query and query:
            await query.answer(
                f"⏳ Aapki request '{option['title']}' ke liye Admin ko bhej di gayi hai!\n\n"
                "Admin ke approve karte hi link aapki private chat me mil jayega.",
                show_alert=True
            )
        elif query:
            await query.edit_message_text(ack_text, reply_markup=ack_kb, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_html(ack_text, reply_markup=ack_kb)

        # Notify admins
        user_mention = f"@{user.username}" if user.username else f"User {user.first_name}"
        admin_text = (
            f"🔔 <b>Nayi Link Request Aayi Hai!</b>\n\n"
            f"👤 <b>User:</b> {user.first_name} ({user_mention})\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"📌 <b>Requested Link:</b> <b>{option['title']}</b>\n"
            f"🔗 <b>URL:</b> {option['url']}"
        )
        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve & Send", callback_data=f"appr_req:{req_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rejc_req:{req_id}")
            ]
        ])
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin_kb
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")


async def handle_link_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle click on an option button."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data or not data.startswith("get_link:"):
        return

    try:
        option_id = int(data.split(":")[1])
    except ValueError:
        await query.message.reply_text("⚠️ Invalid option selected.")
        return

    await process_link_request(update, context, option_id, query.from_user, query=query)

    # Action buttons
    action_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Open Link Directly", url=url)],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
    ])

    await query.message.reply_html(
        message_text,
        reply_markup=action_keyboard,
        disable_web_page_preview=False
    )


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main option selection menu."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    admin_status = config.is_admin(user.id)
    reply_markup = build_user_menu_keyboard(is_admin_user=admin_status)

    options = database.get_options()
    if not options:
        text = "ℹ️ No links are currently available."
    else:
        text = "📋 <b>Main Menu</b>\n\nPlease select an option below:"

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_html(text, reply_markup=reply_markup)


# --- Admin Handlers ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the admin management dashboard."""
    user = update.effective_user
    if not user or not config.is_admin(user.id):
        if update.message:
            await update.message.reply_text("⛔ Access denied. You are not configured as an administrator.")
        elif update.callback_query:
            await update.callback_query.answer("⛔ Access denied.", show_alert=True)
        return

    chat = update.effective_chat
    if chat and chat.type in ["group", "supergroup"]:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username or ""
        text = (
            "🔒 <b>Security Notice:</b>\n\n"
            "Admin Panel contains sensitive link management options. "
            "Please use the Admin Panel in a private chat with the bot."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Open in Private Chat", url=f"https://t.me/{bot_username}")]
        ]) if bot_username else None

        if update.message:
            await update.message.reply_html(text, reply_markup=keyboard)
        elif update.callback_query:
            await update.callback_query.answer("⚠️ Please open Admin Panel in private chat with the bot.", show_alert=True)
        return

    stats = database.get_stats()
    approval_on = database.is_approval_required()
    approval_status_text = "🔒 ON (Admin must approve)" if approval_on else "⚡ OFF (Instant Delivery)"
    toggle_btn_text = "🔓 Switch to Instant Mode" if approval_on else "🔒 Enable Approval Mode"

    text = (
        "🛠️ <b>Admin Control Panel</b>\n\n"
        f"📊 <b>Statistics:</b>\n"
        f"• Total Link Options: <b>{stats['total_options']}</b>\n"
        f"• Registered Users: <b>{stats['total_users']}</b>\n"
        f"• Total Link Accesses: <b>{stats['total_clicks']}</b>\n"
        f"• Request Approval: <b>{approval_status_text}</b>\n\n"
        "Choose an action below:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add New Link", callback_data="admin_add")],
        [InlineKeyboardButton("📋 Manage / Delete Links", callback_data="admin_manage")],
        [InlineKeyboardButton(toggle_btn_text, callback_data="toggle_approval")],
        [InlineKeyboardButton("📊 Refresh Statistics", callback_data="admin_panel")],
        [InlineKeyboardButton("⬅️ View User Menu", callback_data="main_menu")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text, reply_markup=keyboard)


async def toggle_approval_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle whether links require admin approval or are delivered instantly."""
    query = update.callback_query
    user = query.from_user
    if not config.is_admin(user.id):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    new_state = database.toggle_approval_mode()
    state_str = "🔒 ON (Approval Required)" if new_state else "⚡ OFF (Instant Delivery)"
    await query.answer(f"Approval Mode set to: {state_str}", show_alert=True)
    await admin_panel(update, context)


async def handle_admin_request_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin clicking Approve or Reject on a user link request."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not config.is_admin(user.id):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    data = query.data
    action, req_id_str = data.split(":")
    req_id = int(req_id_str)

    req = database.get_link_request(req_id)
    if not req:
        await query.edit_message_text("⚠️ Request not found or expired.")
        return

    if req["status"] != "pending":
        await query.answer(f"This request has already been {req['status']}.", show_alert=True)
        return

    target_user_id = req["user_id"]
    option_title = req["option_title"] or "Requested Link"
    option_url = req["option_url"]

    if action == "appr_req":
        database.update_request_status(req_id, "approved")
        database.record_click(target_user_id, req["option_id"])
        # Send link to user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 <b>Aapki Request Approve Ho Gayi!</b>\n\n"
                    f"Admin ne aapki request approve kar di hai:\n\n"
                    f"📌 <b>{option_title}</b>\n"
                    f"🔗 <b>Link:</b> <a href=\"{option_url}\">{option_url}</a>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Open Link Directly", url=option_url)]
                ])
            )
            await query.edit_message_text(
                f"✅ <b>Approved!</b> Link successfully delivered to {req['first_name']} (<code>{target_user_id}</code>).",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await query.edit_message_text(f"⚠️ Approved in database, but failed to message user: {e}")
    elif action == "rejc_req":
        database.update_request_status(req_id, "rejected")
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"❌ <b>Request Declined</b>\n\nSorry, aapki request <b>{option_title}</b> ke liye reject kar di gayi hai.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        await query.edit_message_text(
            f"❌ <b>Rejected!</b> Request for {req['first_name']} was declined.",
            parse_mode=ParseMode.HTML
        )


async def admin_manage_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all options with individual delete buttons for the admin."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not config.is_admin(user.id):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    options = database.get_options()
    if not options:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add a Link", callback_data="admin_add")],
            [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
        ])
        await query.edit_message_text("ℹ️ There are currently no links to manage.", reply_markup=keyboard)
        return

    text = "📋 <b>Existing Links & Options:</b>\n\nClick 🗑️ to delete an option:"
    keyboard = []
    for opt in options:
        keyboard.append([
            InlineKeyboardButton(f"🔗 {opt['title']} ({opt['clicks']} clicks)", url=opt['url']),
            InlineKeyboardButton(f"🗑️ Delete", callback_data=f"admin_del:{opt['id']}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def admin_delete_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete an option after admin clicks its delete button."""
    query = update.callback_query
    user = query.from_user

    if not config.is_admin(user.id):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    option_id = int(query.data.split(":")[1])
    option = database.get_option(option_id)
    if option:
        database.delete_option(option_id)
        await query.answer(f"✅ Deleted '{option['title']}'", show_alert=True)
    else:
        await query.answer("⚠️ Link not found or already deleted.", show_alert=True)

    # Refresh the manage links list
    await admin_manage_links(update, context)


# --- Add Link Conversation Flow ---

async def start_add_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiate interactive flow to add a new link."""
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
    else:
        user = update.effective_user

    if not user or not config.is_admin(user.id):
        if query:
            await query.answer("⛔ Access denied.", show_alert=True)
        else:
            await update.message.reply_text("⛔ Access denied.")
        return ConversationHandler.END

    text = (
        "➕ <b>Add a New Option & Link</b>\n\n"
        "<b>Step 1 of 3:</b> What should be the <b>Title / Button Name</b> for this option?\n"
        "<i>(e.g., 'Python Tutorial', 'VIP Channel', 'Download File')</i>\n\n"
        "Type /cancel to abort at any time."
    )
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")]])

    if query:
        await query.edit_message_text(text, reply_markup=cancel_kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text, reply_markup=cancel_kb)

    return WAITING_TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save title and ask for URL."""
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Please enter a valid title.")
        return WAITING_TITLE

    context.user_data["new_link_title"] = title

    text = (
        f"✅ Title: <b>{title}</b>\n\n"
        "<b>Step 2 of 3:</b> Please send the <b>URL / Link</b>.\n"
        "<i>(e.g., https://example.com, https://t.me/yourchannel)</i>"
    )
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")]])
    await update.message.reply_html(text, reply_markup=cancel_kb)
    return WAITING_URL


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save URL and ask for optional description."""
    url = update.message.text.strip()

    # Prepend https:// if user simply typed example.com
    if not url.startswith(("http://", "https://", "tg://", "t.me/")):
        url = "https://" + url

    if not is_valid_url(url):
        await update.message.reply_text(
            "⚠️ That doesn't look like a valid link. Please enter a valid URL starting with http://, https://, or t.me/"
        )
        return WAITING_URL

    context.user_data["new_link_url"] = url

    text = (
        f"✅ Link: <code>{url}</code>\n\n"
        "<b>Step 3 of 3:</b> Send an optional <b>short description</b> to display when users select this option.\n\n"
        "Or click the button below to skip this step."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Skip Description", callback_data="skip_desc")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")]
    ])
    await update.message.reply_html(text, reply_markup=keyboard)
    return WAITING_DESC


async def receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save description and insert into database."""
    desc = update.message.text.strip()
    return await finalize_new_link(update, context, description=desc)


async def skip_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip description step and insert into database."""
    query = update.callback_query
    await query.answer()
    return await finalize_new_link(update, context, description="")


async def finalize_new_link(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str) -> int:
    """Save the new link option to the database."""
    title = context.user_data.get("new_link_title", "Untitled")
    url = context.user_data.get("new_link_url", "")

    option_id = database.add_option(title=title, url=url, description=description)

    success_text = (
        "🎉 <b>Link Option Added Successfully!</b>\n\n"
        f"📌 <b>Title:</b> {title}\n"
        f"🔗 <b>Link:</b> <a href=\"{url}\">{url}</a>\n"
    )
    if description:
        success_text += f"📝 <b>Description:</b> {description}\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Another Link", callback_data="admin_add")],
        [InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")],
        [InlineKeyboardButton("👁️ Preview Main Menu", callback_data="main_menu")]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(success_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(success_text, reply_markup=keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the active conversation."""
    context.user_data.clear()
    text = "❌ Operation cancelled."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")]])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)

    return ConversationHandler.END


# --- Quick Command Handlers ---

async def quick_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Quick add via command syntax:
    /add Title | https://example.com | Optional Description
    """
    user = update.effective_user
    if not user or not config.is_admin(user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    text = update.message.text
    # Remove /add command prefix
    content = text.split(maxsplit=1)
    if len(content) < 2:
        await update.message.reply_html(
            "<b>Usage:</b>\n"
            "<code>/add Title | URL | Optional Description</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/add Python Tutorial | https://python.org | Learn Python 3</code>"
        )
        return

    parts = [p.strip() for p in content[1].split("|")]
    title = parts[0]
    if len(parts) < 2:
        await update.message.reply_text("⚠️ Please provide both a Title and a URL separated by '|'.")
        return

    url = parts[1]
    desc = parts[2] if len(parts) > 2 else ""

    if not url.startswith(("http://", "https://", "tg://", "t.me/")):
        url = "https://" + url

    if not is_valid_url(url):
        await update.message.reply_text("⚠️ Invalid URL provided.")
        return

    opt_id = database.add_option(title, url, desc)
    await update.message.reply_html(
        f"✅ Option added!\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>URL:</b> <a href=\"{url}\">{url}</a>\n"
        f"<b>ID:</b> {opt_id}"
    )


async def send_to_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send a link directly to a specific user ID:
    /sendto <user_id> <option_id or custom_url>
    """
    user = update.effective_user
    if not user or not config.is_admin(user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_html(
            "<b>Usage:</b>\n"
            "<code>/sendto &lt;user_id&gt; &lt;link_url_or_option_id&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/sendto 123456789 https://example.com/special-access</code>"
        )
        return

    target_user_id = int(args[0]) if args[0].isdigit() else None
    target_payload = args[1]

    if not target_user_id:
        await update.message.reply_text("⚠️ Invalid user ID.")
        return

    # Check if target_payload is an existing option ID
    link_url = target_payload
    link_title = "Special Link"
    if target_payload.isdigit():
        opt = database.get_option(int(target_payload))
        if opt:
            link_url = opt["url"]
            link_title = opt["title"]

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 <b>You have received a link from the administrator!</b>\n\n"
                 f"📌 <b>{link_title}</b>\n"
                 f"🔗 <a href=\"{link_url}\">{link_url}</a>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Link", url=link_url)]
            ])
        )
        await update.message.reply_text(f"✅ Link successfully delivered to user {target_user_id}!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send message to user {target_user_id}: {str(e)}")


async def is_caller_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user invoking the moderation command is an administrator."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if config.is_admin(user.id):
        return True
    try:
        member = await chat.get_member(user.id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Warn a user. On 3 warnings, the user is kicked from the group.
    Usage:
    - Reply to a user's message with: /warn [reason]
    - Or /warn <user_id> [reason]
    """
    chat = update.effective_chat
    if not chat or chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("ℹ️ /warn command sirf groups me kaam karta hai.")
        return

    if not await is_caller_admin(update, context):
        await update.message.reply_text("⛔ Sirf group administrators /warn command use kar sakte hain.")
        return

    target_user = None
    reason = ""

    # Check if command was sent in reply to a message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        reason = " ".join(context.args) if context.args else ""
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        try:
            target_member = await chat.get_member(target_id)
            target_user = target_member.user
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        except Exception:
            await update.message.reply_text(f"⚠️ User ID {target_id} group me nahi mila.")
            return
    else:
        await update.message.reply_html(
            "ℹ️ <b>Usage:</b>\n"
            "• Kisi ke message ka reply karke <code>/warn [reason]</code> likhein.\n"
            "• Ya <code>/warn &lt;user_id&gt; [reason]</code> likhein."
        )
        return

    # Check safety: cannot warn bot itself
    if target_user.id == context.bot.id:
        await update.message.reply_text("🤖 Main khud ko warn nahi kar sakta!")
        return

    # Check safety: cannot warn group admins
    try:
        target_member = await chat.get_member(target_user.id)
        if target_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            await update.message.reply_html("⛔ Administrators ko warn nahi kiya ja sakta.")
            return
    except Exception:
        pass

    # Increment warning count in database
    warn_count = database.add_warning(chat.id, target_user.id)
    target_name = target_user.first_name
    user_mention = f"@{target_user.username}" if target_user.username else target_name

    if warn_count < 3:
        msg = (
            f"⚠️ <b>Warning [{warn_count}/3]</b>\n\n"
            f"👤 <b>User:</b> {target_name} ({user_mention})\n"
        )
        if reason:
            msg += f"📝 <b>Reason:</b> {reason}\n"
        msg += (
            f"\n<i>3 warnings hone par aapko group se nikal diya jayega!</i>\n"
            f"Remaining warnings: <b>{3 - warn_count}</b>"
        )
        await update.message.reply_html(msg)
    else:
        # 3 or more warnings reached: Kick the user
        database.reset_warnings(chat.id, target_user.id)
        try:
            # ban and unban effectively kicks the member so they are removed
            await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
            await context.bot.unban_chat_member(chat_id=chat.id, user_id=target_user.id)
            kick_msg = (
                f"🚫 <b>3 Warnings Reached!</b>\n\n"
                f"👤 <b>{target_name}</b> ({user_mention}) ko 3 warnings poori hone par group se <b>remove/kick</b> kar diya gaya hai."
            )
            await update.message.reply_html(kick_msg)
        except Exception as e:
            logger.error(f"Failed to kick user {target_user.id}: {e}")
            await update.message.reply_html(
                f"⚠️ <b>{target_name}</b> has reached 3 warnings!\n\n"
                f"❌ Failed to kick user. Please ensure the bot is an <b>Administrator</b> with 'Ban Users' permission in this group."
            )


async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a warning from a user. Usage: Reply with /unwarn or /unwarn <user_id>."""
    chat = update.effective_chat
    if not chat or chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("ℹ️ /unwarn command sirf groups me kaam karta hai.")
        return

    if not await is_caller_admin(update, context):
        await update.message.reply_text("⛔ Sirf group administrators /unwarn use kar sakte hain.")
        return

    target_user = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        try:
            target_member = await chat.get_member(target_id)
            target_user = target_member.user
        except Exception:
            await update.message.reply_text(f"⚠️ User ID {target_id} group me nahi mila.")
            return
    else:
        await update.message.reply_html("ℹ️ Kisi user ke message ka reply karke <code>/unwarn</code> karein.")
        return

    new_count = database.remove_warning(chat.id, target_user.id)
    await update.message.reply_html(
        f"✅ 1 warning removed for <b>{target_user.first_name}</b>.\n"
        f"Current warnings: <b>{new_count}/3</b>"
    )


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check warning count. Usage: /warns or reply with /warns."""
    chat = update.effective_chat
    if not chat or chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("ℹ️ /warns command sirf groups me kaam karta hai.")
        return

    target_user = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
    elif context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        try:
            target_member = await chat.get_member(target_id)
            target_user = target_member.user
        except Exception:
            await update.message.reply_text(f"⚠️ User ID {target_id} group me nahi mila.")
            return
    else:
        target_user = update.effective_user

    count = database.get_warnings(chat.id, target_user.id)
    await update.message.reply_html(
        f"📋 <b>Warnings for {target_user.first_name}:</b> <b>{count}/3</b>"
    )


COURSE_QUERY_PATTERN = re.compile(
    r"\b(course|courses|cohort|cohorts|batch|batches|lecture|lectures|classes|syllabus|tutorial|tutorials|notes|fees)\b",
    re.IGNORECASE
)


async def course_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond 'mt kr lala' to course queries in group chats."""
    message = update.effective_message or update.message
    if not message:
        return

    raw_text = getattr(message, "text", None) or getattr(message, "caption", None)
    if not isinstance(raw_text, str) or not raw_text.strip():
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    # Check if sender is a bot or admin
    if getattr(user, "is_bot", False) or config.is_admin(getattr(user, "id", 0)):
        return

    if COURSE_QUERY_PATTERN.search(raw_text):
        try:
            await message.reply_text("mt kr lala")
        except Exception as e:
            logger.error(f"Failed to reply 'mt kr lala': {e}")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unexpected errors gracefully without crashing the bot."""
    logger.error("Exception while handling an update:", exc_info=context.error)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information."""
    user = update.effective_user
    is_adm = config.is_admin(user.id) if user else False

    help_text = (
        "🤖 <b>Telegram Link Bot Help</b>\n\n"
        "• /start - View available options and retrieve links\n"
        "• /help - Display this help guide\n"
    )

    if is_adm:
        help_text += (
            "\n🛠️ <b>Admin Commands:</b>\n"
            "• /admin - Open the admin dashboard\n"
            "• <code>/add &lt;Title&gt; | &lt;URL&gt; | [Description]</code> - Quickly add a link\n"
            "• <code>/sendto &lt;user_id&gt; &lt;URL or Option_ID&gt;</code> - Send link directly to a user\n"
            "• <code>/warn [reason]</code> - Warn a member (kicks on 3 warnings)\n"
            "• <code>/unwarn</code> - Remove 1 warning from member\n"
            "• <code>/warns</code> - View warning count of a member\n"
        )

    await update.message.reply_html(help_text)


def main() -> None:
    """Start the bot application."""
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in config or environment variables!")
        print("\n[ERROR] Telegram BOT_TOKEN is missing! Please configure BOT_TOKEN in .env file.\n")
        return

    # Initialize the database
    database.init_db()

    # Build the Application
    app = Application.builder().token(config.BOT_TOKEN).build()

    # Conversation handler for adding links
    add_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_conversation, pattern="^admin_add$"),
            CommandHandler("newlink", start_add_conversation),
        ],
        states={
            WAITING_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel_conv$"),
            ],
            WAITING_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel_conv$"),
            ],
            WAITING_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_desc),
                CallbackQueryHandler(skip_desc, pattern="^skip_desc$"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel_conv$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern="^cancel_conv$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    # Register handlers
    app.add_handler(CommandHandler(["start", "links", "menu", "options"], start_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("add", quick_add_command))
    app.add_handler(CommandHandler("sendto", send_to_user_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler(["unwarn", "resetwarn"], unwarn_command))
    app.add_handler(CommandHandler(["warns", "warnings"], warnings_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(add_conv_handler)

    # Welcome new group members (Supergroups via ChatMemberUpdated and regular groups via status update)
    app.add_handler(ChatMemberHandler(chat_member_welcome_handler, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_chat_member))

    # Respond to regular messages in private chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_private_message))

    # Respond 'mt kr lala' to course queries in group chats
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, course_query_handler))

    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_manage_links, pattern="^admin_manage$"))
    app.add_handler(CallbackQueryHandler(admin_delete_link, pattern="^admin_del:"))
    app.add_handler(CallbackQueryHandler(toggle_approval_handler, pattern="^toggle_approval$"))
    app.add_handler(CallbackQueryHandler(handle_admin_request_action, pattern="^(appr_req|rejc_req):"))
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(handle_link_selection, pattern="^get_link:"))

    # Global error handler so unexpected errors do not crash the bot process
    app.add_error_handler(global_error_handler)

    logger.info("Bot is starting polling...")
    print("🚀 Telegram bot is active and listening for messages. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
