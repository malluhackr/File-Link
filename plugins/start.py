import random
import humanize
from Script import script
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from info import AUTH_CHANNEL, URL, LOG_CHANNEL, SHORTLINK
from urllib.parse import quote_plus
from TechVJ.util.file_properties import get_name, get_hash, get_media_file_size
from TechVJ.util.human_readable import humanbytes
from database.users_chats_db import db
from utils import temp, get_shortlink
import asyncio # Import asyncio for better async operations
import logging # Import logging for better error handling

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def is_subscribed(bot, user_id, channels):
    """
    Checks if a user is subscribed to all required channels.
    Returns a list of buttons for unsubscribed channels, or empty list if subscribed to all.
    """
    unsubscribed_channels = []
    for channel_id in channels:
        try:
            chat = await bot.get_chat(channel_id)
            # Check if user is a member
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in [enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT]:
                raise UserNotParticipant # Treat banned/left as not participant
        except UserNotParticipant:
            try:
                invite_link = chat.invite_link or await bot.export_chat_invite_link(channel_id)
                unsubscribed_channels.append([InlineKeyboardButton(f"Join {chat.title}", url=invite_link)])
            except Exception as e:
                logger.error(f"Error getting invite link for channel {channel_id}: {e}")
                # Optionally, you can add a generic button or just skip if invite link fails
                unsubscribed_channels.append([InlineKeyboardButton(f"Join Channel", url="https://t.me/telegram")]) # Fallback
        except Exception as e:
            logger.error(f"Error checking subscription for channel {channel_id}: {e}")
            # If there's an error fetching chat/member, assume they need to join
            unsubscribed_channels.append([InlineKeyboardButton(f"Join Channel", url="https://t.me/telegram")]) # Generic fallback

    return unsubscribed_channels

@Client.on_message(filters.command("start") & filters.private)
async def start(client, message):
    """
    Handles the /start command. Checks subscription, adds user to DB, and sends welcome message.
    """
    user_id = message.from_user.id
    user_mention = message.from_user.mention
    first_name = message.from_user.first_name

    # React with multiple emojis for a lively welcome
    try:
        await message.react("👋")
        await asyncio.sleep(0.5) # Small delay for multiple reactions
        await message.react("🤩")
    except Exception as e:
        logger.warning(f"Could not react to message: {e}")

    # Force subscription logic
    if AUTH_CHANNEL:
        try:
            subscription_buttons = await is_subscribed(client, user_id, AUTH_CHANNEL)
            if subscription_buttons:
                # Add a "Try Again" button for convenience
                subscription_buttons.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{(await client.get_me()).username}?start=true")])
                await message.reply_text(
                    text=f"👋 Hi {user_mention},\n\nPlease join the required channel(s) to use this bot. Click 'Try Again' after joining.",
                    reply_markup=InlineKeyboardMarkup(subscription_buttons),
                    parse_mode=enums.ParseMode.HTML
                )
                return
        except Exception as e:
            logger.error(f"Error during force subscription check: {e}")
            # Inform user if there's an issue with the subscription check
            await message.reply_text("Oops! Something went wrong while checking your subscription. Please try again later.")
            return # Prevent further execution if subscription check fails critically

    # Add user to the database if they don't exist
    try:
        if not await db.is_user_exist(user_id):
            await db.add_user(user_id, first_name)
            # Log new user in the LOG_CHANNEL
            if LOG_CHANNEL:
                try:
                    await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user_id, user_mention))
                except Exception as e:
                    logger.error(f"Failed to send log to LOG_CHANNEL for new user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error adding user {user_id} to database: {e}")

    # Send welcome message
    welcome_text = script.START_TXT.format(user_mention, temp.U_NAME, temp.B_NAME)
    welcome_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/KeralaCaptain")]]
    )
    # Add an "About" button for more info
    welcome_markup.inline_keyboard.append([InlineKeyboardButton("About Bot 🤖", callback_data="about_bot")])

    try:
        await message.reply_text(
            text=welcome_text,
            reply_markup=welcome_markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error sending start message to user {user_id}: {e}")


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio)) # Added audio filter
async def stream_start(client, message):
    """
    Handles incoming media files (document, video, audio) in private chat.
    Generates stream and download links and sends them to the user and log channel.
    """
    user_id = message.from_user.id

    # Check for force subscription again before processing file
    if AUTH_CHANNEL:
        try:
            subscription_buttons = await is_subscribed(client, user_id, AUTH_CHANNEL)
            if subscription_buttons:
                subscription_buttons.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{(await client.get_me()).username}?start=true")])
                await message.reply_text(
                    text=f"👋 Hi {message.from_user.mention},\n\nPlease join the required channel(s) to use this bot. Click 'Try Again' after joining.",
                    reply_markup=InlineKeyboardMarkup(subscription_buttons),
                    parse_mode=enums.ParseMode.HTML
                )
                return
        except Exception as e:
            logger.error(f"Error during force subscription check for media: {e}")
            await message.reply_text("Oops! Something went wrong while checking your subscription. Please try again later.")
            return

    # Indicate processing to the user
    processing_msg = await message.reply_text("Processing your file... Please wait.")

    try:
        file = getattr(message, message.media.value)
        
        # Ensure file has necessary attributes
        if not all(hasattr(file, attr) for attr in ['file_name', 'file_size', 'file_id']):
            await processing_msg.edit_text("Could not get file details. Please try sending a valid media file.")
            return

        filename = file.file_name
        filesize_readable = humanize.naturalsize(file.file_size)
        fileid = file.file_id
        username = message.from_user.mention

        # Send file to log channel and get the message object
        if LOG_CHANNEL:
            log_msg = await client.send_cached_media(
                chat_id=LOG_CHANNEL,
                file_id=fileid,
                caption=f"**File from:** {username} (ID: `{user_id}`)\n**Original Filename:** `{filename}`\n**File Size:** `{filesize_readable}`"
            )
        else:
            await processing_msg.edit_text("Error: Log channel is not configured. Please contact bot admin.")
            return

        file_name_quoted = quote_plus(get_name(log_msg))

        stream_url = ""
        download_url = ""

        if not SHORTLINK:
            stream_url = f"{URL}watch/{log_msg.id}/{file_name_quoted}?hash={get_hash(log_msg)}"
            download_url = f"{URL}{log_msg.id}/{file_name_quoted}?hash={get_hash(log_msg)}"
        else:
            # Use asyncio.gather for parallel shortlink generation if get_shortlink supports it
            stream_shortlink_task = get_shortlink(f"{URL}watch/{log_msg.id}/{file_name_quoted}?hash={get_hash(log_msg)}")
            download_shortlink_task = get_shortlink(f"{URL}{log_msg.id}/{file_name_quoted}?hash={get_hash(log_msg)}")
            
            stream_url, download_url = await asyncio.gather(stream_shortlink_task, download_shortlink_task)
            
        # Update log channel message with links
        log_message_text = (
            f"**•• ʟɪɴᴋ ɢᴇɴᴇʀᴀᴛᴇᴅ ꜰᴏʀ ɪᴅ** #{user_id}\n"
            f"**•• ᴜꜱᴇʀɴᴀᴍᴇ:** {username}\n"
            f"**•• ᖴᎥᒪᗴ Nᗩᗰᗴ:** {get_name(log_msg)}\n\n"
            f"**📥 Download:** [Link]({download_url})\n"
            f"**🖥️ Watch online:** [Link]({stream_url})"
        )
        await log_msg.edit_text(
            text=log_message_text,
            quote=True,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Fast Download 🚀", url=download_url), 
                 InlineKeyboardButton('🖥️ Watch online 🖥️', url=stream_url)]
            ]),
            parse_mode=enums.ParseMode.MARKDOWN
        )

        # Send links to the user
        user_msg_text = f"""
<i><u>Your Link is Ready!</u></i>\n
<b>📂 File Name:</b> <i>{get_name(log_msg)}</i>\n
<b>📦 File Size:</b> <i>{humanbytes(get_media_file_size(message))}</i>\n
<b>📥 Download:</b> <a href="{download_url}">Click Here</a>\n
<b>🖥 Watch Online:</b> <a href="{stream_url}">Click Here</a>\n
<b>⚠️ Note:</b> Links won't expire until I delete them.
"

       await processing_msg.edit_text(
            text=user_msg_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Stream 🖥", url=stream_url), 
                 InlineKeyboardButton("Download 📥", url=download_url)]
            ]),
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Error processing stream request for user {user_id}: {e}", exc_info=True)
        # Inform the user about the error
        try:
            await processing_msg.edit_text("Sorry, an error occurred while generating your links. Please try again or contact support.")
        except Exception as edit_error:
            logger.error(f"Failed to edit error message: {edit_error}")

# Example for handling callback queries (for "About Bot" button)
@Client.on_callback_query(filters.regex("about_bot"))
async def about_bot_callback(client, callback_query):
    await callback_query.answer("This is a Stream/Download Link Generator Bot!", show_alert=True)
    # Or, send a more detailed message:
    # await callback_query.message.reply_text(
    #     "🤖 **About This Bot** 🤖\n\n"
    #     "This bot helps you generate direct stream and download links for your media files.\n"
    #     "Just send me a video, document, or audio file, and I'll provide the links!\n\n"
    #     "**Developed by:** [Your Name/Channel](https://t.me/KeralaCaptain)\n"
    #     "**Version:** 1.0",
    #     parse_mode=enums.ParseMode.MARKDOWN,
    #     disable_web_page_preview=True,
    #     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_to_start")]])
    # )

# You might need to define script.py, info.py, TechVJ/util, and database/users_chats_db.py
# Make sure `get_shortlink` function in `utils.py` handles the URL shortening correctly.
