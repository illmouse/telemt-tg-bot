import logging
import os
import re
import warnings
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


warnings.filterwarnings("ignore", message=".*per_message=False.*")


class _RedactToken(logging.Filter):
    def __init__(self):
        super().__init__()
        self._token = os.environ.get("BOT_TOKEN", "")

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token:
            record.msg = str(record.msg).replace(self._token, "***")
            record.args = None
        return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
_filter = _RedactToken()
logging.root.addFilter(_filter)
logger = logging.getLogger(__name__)

api = TelemtAPI()

ALLOWED_USERNAMES = set(
    u.strip() for u in os.environ.get("ALLOWED_USERNAMES", "").split(",") if u.strip()
)

LINK_HOST = os.environ.get("LINK_HOST", "").strip()

# Conversation states
WAITING_FOR_USERNAME = 1
WAITING_FOR_MAX_IPS = 2
WAITING_FOR_PATCH_IPS = 3

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["➕ Create User", "👥 List Users"]],
    resize_keyboard=True,
)

CANCEL_KB = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖ Cancel", callback_data="cancel_conv")]]
)

MAX_IPS_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("1 (default)", callback_data="maxips:1"),
        InlineKeyboardButton("2", callback_data="maxips:2"),
        InlineKeyboardButton("5", callback_data="maxips:5"),
        InlineKeyboardButton("Unlimited", callback_data="maxips:0"),
    ],
    [InlineKeyboardButton("✖ Cancel", callback_data="cancel_conv")],
])

# max_tcp_conns value used to re-enable a disabled user
ENABLED_TCP_CONNS = 65535


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
    disabled = user.get("max_tcp_conns") == 0
    lines = [f"<b>{user['username']}</b>" + (" 🔴 disabled" if disabled else "")]
    if user.get("max_unique_ips") is not None:
        lines.append(f"Max IPs: {user['max_unique_ips']}")
    if user.get("max_tcp_conns") is not None and not disabled:
        lines.append(f"Max connections: {user['max_tcp_conns']}")
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


def user_keyboard(username: str, user: dict) -> InlineKeyboardMarkup:
    disabled = user.get("max_tcp_conns") == 0
    toggle_label = "🟢 Enable" if disabled else "🔴 Disable"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Get Link", callback_data=f"link:{username}"),
            InlineKeyboardButton("✏️ Max IPs", callback_data=f"patchips:{username}"),
        ],
        [
            InlineKeyboardButton(toggle_label, callback_data=f"toggle:{username}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"del:{username}"),
        ],
        [InlineKeyboardButton("◀ Back", callback_data="back_list")],
    ])


def proxy_message(user: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    links = user.get("links", {})
    username = user["username"]
    rows = []

    def pick_link(lst: list[str]) -> list[str]:
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
        disabled = u.get("max_tcp_conns") == 0
        status = "🔴" if disabled else ("🟢" if conns > 0 else "⚫")
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
async def create_receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    if not USERNAME_RE.match(username):
        await update.message.reply_text(
            "Invalid username. Use only <code>[A-Za-z0-9_.-]</code>, 1–64 chars. Try again:",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )
        return WAITING_FOR_USERNAME

    context.user_data["new_username"] = username
    await update.message.reply_text(
        f"Max unique IPs for <b>{username}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=MAX_IPS_KB,
    )
    return WAITING_FOR_MAX_IPS


@require_access
async def create_receive_max_ips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    max_ips = int(q.data.split(":")[1])
    username = context.user_data.get("new_username")

    try:
        result = api.create_user(username, max_unique_ips=max_ips)
    except Exception as e:
        await q.message.edit_text(f"Error: {e}")
        return ConversationHandler.END

    user = result["user"]
    await q.message.edit_text(
        f"✅ Created\n\n{fmt_user_info(user)}",
        parse_mode=ParseMode.HTML,
    )
    text, kb = proxy_message(user)
    if kb:
        await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return ConversationHandler.END


@require_access
async def patch_ips_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    username = q.data.split(":", 1)[1]
    context.user_data["patch_username"] = username
    await q.message.edit_text(
        f"Enter new max unique IPs for <b>{username}</b>\n(0 = unlimited):",
        parse_mode=ParseMode.HTML,
        reply_markup=CANCEL_KB,
    )
    return WAITING_FOR_PATCH_IPS


@require_access
async def patch_ips_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.user_data.get("patch_username")
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Enter a number:", reply_markup=CANCEL_KB)
        return WAITING_FOR_PATCH_IPS

    value = int(text)
    try:
        if value == 0:
            user = api.patch_user(username)  # can't clear — just refresh
        else:
            user = api.patch_user(username, max_unique_ips=value)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Updated\n\n{fmt_user_info(user)}",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )
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
        await q.message.edit_text(
            fmt_user_info(user), parse_mode=ParseMode.HTML, reply_markup=user_keyboard(username, user)
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

    elif data.startswith("toggle:"):
        username = data[7:]
        try:
            user = api.get_user(username)
            if user.get("max_tcp_conns") == 0:
                user = api.patch_user(username, max_tcp_conns=ENABLED_TCP_CONNS)
            else:
                user = api.patch_user(username, max_tcp_conns=0)
        except Exception as e:
            await q.message.edit_text(f"Error: {e}")
            return
        await q.message.edit_text(
            fmt_user_info(user), parse_mode=ParseMode.HTML, reply_markup=user_keyboard(username, user)
        )

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
            CallbackQueryHandler(patch_ips_start, pattern="^patchips:"),
        ],
        states={
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_receive_username),
            ],
            WAITING_FOR_MAX_IPS: [
                CallbackQueryHandler(create_receive_max_ips, pattern="^maxips:"),
            ],
            WAITING_FOR_PATCH_IPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, patch_ips_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(
                lambda u, c: ConversationHandler.END, pattern="^cancel_conv$"
            ),
        ],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Text(["👥 List Users"]), list_users))
    app.add_handler(CallbackQueryHandler(on_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
