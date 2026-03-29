import logging
import os
import re
from functools import wraps
from urllib.parse import urlparse, parse_qs, urlencode

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telemt_api import TelemtAPI

class _RedactToken(logging.Filter):
    def __init__(self):
        super().__init__()
        self._token = os.environ.get("BOT_TOKEN", "")

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token:
            record.msg = str(record.msg).replace(self._token, "***")
        return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
_filter = _RedactToken()
for _h in logging.root.handlers:
    _h.addFilter(_filter)
logger = logging.getLogger(__name__)

api = TelemtAPI()

ALLOWED_USERNAMES = set(
    u.strip() for u in os.environ.get("ALLOWED_USERNAMES", "").split(",") if u.strip()
)

# When set, only proxy links whose server= matches this host are shown.
LINK_HOST = os.environ.get("LINK_HOST", "").strip()

WAITING_FOR_USERNAME = 1

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["➕ Create User", "👥 List Users"]],
    resize_keyboard=True,
)

CANCEL_KB = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖ Cancel", callback_data="cancel_conv")]]
)


def is_allowed(update: Update) -> bool:
    if not ALLOWED_USERNAMES:
        return True
    u = update.effective_user
    return bool(u and u.username in ALLOWED_USERNAMES)


def require_access(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_allowed(update):
            await update.effective_message.reply_text("Access denied.")
            return ConversationHandler.END
        return await func(update, context)

    return wrapper


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_user_info(user: dict) -> str:
    lines = [f"<b>{user['username']}</b>"]
    if user.get("max_unique_ips") is not None:
        lines.append(f"Max IPs: {user['max_unique_ips']}")
    if user.get("expiration_rfc3339"):
        lines.append(f"Expires: {user['expiration_rfc3339'][:10]}")
    if user.get("data_quota_bytes") is not None:
        gb = user["data_quota_bytes"] / 1_000_000_000
        lines.append(f"Quota: {gb:.2f} GB")
    lines.append(f"Connections: {user['current_connections']}")
    lines.append(f"Active IPs: {user['active_unique_ips']}")
    if user.get("active_unique_ips_list"):
        lines.append("IPs: " + ", ".join(user["active_unique_ips_list"]))
    mb = user.get("total_octets", 0) / 1_000_000
    lines.append(f"Traffic: {mb:.1f} MB")
    return "\n".join(lines)


def proxy_message(user: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Returns (text, keyboard) for a forwardable proxy link message."""
    links = user.get("links", {})
    username = user["username"]
    rows = []

    def pick_link(lst: list[str]) -> list[str]:
        """Return at most one link, rewriting server= to LINK_HOST if set."""
        if not lst:
            return []
        link = lst[0]
        if LINK_HOST:
            parsed = urlparse(link)
            params = parse_qs(parsed.query, keep_blank_values=True)
            params["server"] = [LINK_HOST]
            new_query = urlencode({k: v[0] for k, v in params.items()})
            link = parsed._replace(query=new_query).geturl()
        return [link]

    secure = pick_link(links.get("secure", []))
    classic = pick_link(links.get("classic", []))
    tls = pick_link(links.get("tls", []))

    for i, link in enumerate(secure):
        label = "🔒 Secure" if len(secure) == 1 else f"🔒 Secure {i + 1}"
        rows.append([InlineKeyboardButton(label, url=link)])
    for i, link in enumerate(classic):
        label = "📡 Classic" if len(classic) == 1 else f"📡 Classic {i + 1}"
        rows.append([InlineKeyboardButton(label, url=link)])
    for i, link in enumerate(tls):
        label = "🔐 TLS" if len(tls) == 1 else f"🔐 TLS {i + 1}"
        rows.append([InlineKeyboardButton(label, url=link)])

    text = f"🔒 <b>MTProxy</b>\nUser: <code>{username}</code>"
    return text, (InlineKeyboardMarkup(rows) if rows else None)


def users_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for u in users:
        name = u["username"]
        conns = u["current_connections"]
        status = "🟢" if conns > 0 else "⚫"
        rows.append(
            [InlineKeyboardButton(f"{status} {name} ({conns})", callback_data=f"user:{name}")]
        )
    rows.append([InlineKeyboardButton("✖ Close", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


# ── Handlers ──────────────────────────────────────────────────────────────────

@require_access
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Telemt Proxy Manager", reply_markup=MAIN_KEYBOARD)


@require_access
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Enter username <code>[A-Za-z0-9_.-]</code>, up to 64 chars:",
        parse_mode=ParseMode.HTML,
        reply_markup=CANCEL_KB,
    )
    return WAITING_FOR_USERNAME


@require_access
async def create_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    if not USERNAME_RE.match(username):
        await update.message.reply_text(
            "Invalid username. Use only <code>[A-Za-z0-9_.-]</code>, 1–64 chars. Try again:",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )
        return WAITING_FOR_USERNAME

    try:
        result = api.create_user(username)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

    user = result["user"]
    await update.message.reply_text(
        f"✅ Created\n\n{fmt_user_info(user)}",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )
    text, kb = proxy_message(user)
    if kb:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return ConversationHandler.END


@require_access
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        users = api.get_users()
    except Exception as e:
        await update.effective_message.reply_text(f"Error: {e}")
        return
    if not users:
        await update.effective_message.reply_text("No users configured.")
        return
    await update.effective_message.reply_text(
        f"Users ({len(users)}):",
        reply_markup=users_keyboard(users),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data in ("cancel", "cancel_conv"):
        try:
            await q.message.delete()
        except Exception:
            await q.message.edit_reply_markup(None)
        return

    if not is_allowed(update):
        await q.message.edit_text("Access denied.")
        return

    if data == "back_list":
        try:
            users = api.get_users()
        except Exception as e:
            await q.message.edit_text(f"Error: {e}")
            return
        if not users:
            await q.message.edit_text("No users configured.")
            return
        await q.message.edit_text(f"Users ({len(users)}):", reply_markup=users_keyboard(users))

    elif data.startswith("user:"):
        username = data[5:]
        try:
            user = api.get_user(username)
        except Exception as e:
            await q.message.edit_text(f"Error: {e}")
            return
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔗 Get Link", callback_data=f"link:{username}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"del:{username}"),
            ],
            [InlineKeyboardButton("◀ Back", callback_data="back_list")],
        ])
        await q.message.edit_text(
            fmt_user_info(user), parse_mode=ParseMode.HTML, reply_markup=kb
        )

    elif data.startswith("link:"):
        username = data[5:]
        try:
            user = api.get_user(username)
        except Exception as e:
            await q.message.edit_text(f"Error: {e}")
            return
        text, kb = proxy_message(user)
        back_kb = InlineKeyboardMarkup(
            list(kb.inline_keyboard if kb else [])
            + [[InlineKeyboardButton("◀ Back", callback_data=f"user:{username}")]]
        )
        await q.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

    elif data.startswith("del:"):
        username = data[4:]
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, delete", callback_data=f"delconfirm:{username}"),
            InlineKeyboardButton("✖ No", callback_data=f"user:{username}"),
        ]])
        await q.message.edit_text(
            f"Delete user <b>{username}</b>?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )

    elif data.startswith("delconfirm:"):
        username = data[11:]
        try:
            api.delete_user(username)
        except Exception as e:
            await q.message.edit_text(f"Error: {e}")
            return
        await q.message.edit_text(f"✅ Deleted <b>{username}</b>.", parse_mode=ParseMode.HTML)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("create", create_start),
            MessageHandler(filters.Text(["➕ Create User"]), create_start),
        ],
        states={
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(
                lambda u, c: ConversationHandler.END, pattern="^cancel_conv$"
            ),
        ],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Text(["👥 List Users"]), list_users))
    app.add_handler(CallbackQueryHandler(on_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
