"""
Communications Agent — Telegram Bot Interface.

Handles all messaging between the user and JARVIS.
Supports: text messages, voice notes, inline keyboard approvals,
slash commands, media (photos, documents).

Uses python-telegram-bot v22+ (async-native).
"""
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Optional, Callable, Awaitable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("agents.comms")

# Voice note transcription
VOICE_DIR = Path(__file__).parent.parent.parent / "data" / "logs" / "voice_notes"
VOICE_DIR.mkdir(parents=True, exist_ok=True)


class TelegramBot:
    """Telegram bot interface for JARVIS."""

    def __init__(self):
        self.app: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self.owner_chat_id: Optional[int] = None
        self._message_handler: Optional[Callable] = None
        self._whisper_model = None
        self._context_messages: list = []  # Last 20 messages for context
        self._pending_approvals: dict = {}  # approval_id -> callback

    async def initialize(self, message_handler: Callable) -> bool:
        """Initialize the Telegram bot.

        Args:
            message_handler: async function(message, source, metadata) -> response
        """
        secrets = load_secrets()
        token = secrets.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = secrets.get("TELEGRAM_OWNER_CHAT_ID", "")

        if not token:
            log.error("TELEGRAM_BOT_TOKEN not set in config/secrets.env")
            return False

        self.owner_chat_id = int(owner_id) if owner_id else None
        self._message_handler = message_handler

        # Build the application
        self.app = Application.builder().token(token).build()
        self.bot = self.app.bot

        # Register handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("active", self._cmd_mode))
        self.app.add_handler(CommandHandler("focus", self._cmd_mode))
        self.app.add_handler(CommandHandler("sleep", self._cmd_mode))
        self.app.add_handler(CommandHandler("memory", self._cmd_memory))
        self.app.add_handler(CommandHandler("briefing", self._cmd_briefing))
        self.app.add_handler(CommandHandler("review", self._cmd_review))
        self.app.add_handler(CommandHandler("stats", self._cmd_stats))

        # Voice notes
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice))

        # Text messages (catch-all, must be last)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

        # Inline keyboard callbacks (for approvals)
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        log.info("Telegram bot initialized")
        return True

    async def start(self):
        """Start the bot (polling mode for development)."""
        log.info("Starting Telegram bot (polling mode)...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot running")

    async def stop(self):
        """Stop the bot."""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            log.info("Telegram bot stopped")

    def _is_owner(self, update: Update) -> bool:
        """Check if message is from the owner."""
        if self.owner_chat_id is None:
            return True  # No owner set — accept all (first-run mode)
        return update.effective_chat.id == self.owner_chat_id

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        if not self._is_owner(update):
            await update.message.reply_text("Unauthorised.")
            return

        message = update.message.text
        log.info(f"Text received: {message[:80]}")

        # Track context
        self._add_context("user", message)

        # Route to orchestrator
        response = await self._message_handler(
            message=message,
            source="telegram",
            metadata={
                "chat_id": update.effective_chat.id,
                "message_id": update.message.message_id,
            },
        )

        if response:
            self._add_context("JARVIS", response)
            # Split long messages (Telegram limit: 4096 chars)
            for chunk in self._split_message(response):
                await update.message.reply_text(chunk)

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice notes — download, transcribe, process as text."""
        if not self._is_owner(update):
            return

        voice = update.message.voice or update.message.audio
        if not voice:
            return

        log.info(f"Voice note received: {voice.duration}s")
        await update.message.reply_text("Transcribing...")

        try:
            # Download voice file
            file = await context.bot.get_file(voice.file_id)
            ogg_path = VOICE_DIR / f"{voice.file_unique_id}.ogg"
            await file.download_to_drive(str(ogg_path))

            # Transcribe
            transcript = await self._transcribe_voice(ogg_path)

            if not transcript:
                await update.message.reply_text("Couldn't transcribe that. Try again?")
                return

            log.info(f"Transcription: {transcript[:80]}")
            await update.message.reply_text(f"Heard: {transcript[:200]}")

            # Process transcription as text message
            self._add_context("user (voice)", transcript)
            response = await self._message_handler(
                message=transcript,
                source="telegram",
                metadata={
                    "chat_id": update.effective_chat.id,
                    "is_voice": True,
                    "voice_duration": voice.duration,
                },
            )

            if response:
                self._add_context("JARVIS", response)
                for chunk in self._split_message(response):
                    await update.message.reply_text(chunk)

        except Exception as e:
            log.error(f"Voice processing error: {e}")
            await update.message.reply_text(f"Voice processing failed: {str(e)[:200]}")

    async def _transcribe_voice(self, ogg_path: Path) -> str:
        """Transcribe a voice note using faster-whisper."""
        try:
            if self._whisper_model is None:
                from faster_whisper import WhisperModel
                # Use tiny model for speed on M2
                self._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
                log.info("Whisper model loaded (tiny/int8)")

            segments, info = self._whisper_model.transcribe(
                str(ogg_path),
                language="en",
                beam_size=5,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            return text.strip()

        except Exception as e:
            log.error(f"Transcription error: {e}")
            return ""

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        chat_id = update.effective_chat.id
        if self.owner_chat_id is None:
            # First run — register owner
            self.owner_chat_id = chat_id
            log.info(f"Owner registered: chat_id={chat_id}")
            await update.message.reply_text(
                f"JARVIS online. Owner registered (chat_id: {chat_id}).\n"
                f"Save this in config/secrets.env: TELEGRAM_OWNER_CHAT_ID={chat_id}\n\n"
                f"Commands: /status /active /focus /sleep /memory /briefing /review /stats"
            )
        elif self._is_owner(update):
            await update.message.reply_text("JARVIS is running. What do you need?")
        else:
            await update.message.reply_text("Unauthorised.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        response = await self._message_handler("/status", "telegram", {})
        await update.message.reply_text(response or "No status available")

    async def _cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        cmd = update.message.text  # e.g., "/active"
        response = await self._message_handler(cmd, "telegram", {})
        await update.message.reply_text(response or "Mode changed")

    async def _cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        text = update.message.text  # e.g., "/memory IVV"
        response = await self._message_handler(text, "telegram", {})
        await update.message.reply_text(response or "No results")

    async def _cmd_briefing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        await update.message.reply_text("Generating briefing...")
        response = await self._message_handler("/briefing", "telegram", {})
        for chunk in self._split_message(response or "No briefing available"):
            await update.message.reply_text(chunk)

    async def _cmd_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        response = await self._message_handler("/review", "telegram", {})
        for chunk in self._split_message(response or "No review available"):
            await update.message.reply_text(chunk)

    async def _cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        response = await self._message_handler("/stats", "telegram", {})
        await update.message.reply_text(response or "No stats")

    # --- Approval system ---

    async def send_message(self, text: str):
        """Send a message to the owner (for proactive messages like briefings)."""
        if not self.bot or not self.owner_chat_id:
            log.warning("Cannot send message — bot or owner not configured")
            return
        for chunk in self._split_message(text):
            await self.bot.send_message(chat_id=self.owner_chat_id, text=chunk)

    async def request_approval(
        self,
        description: str,
        approval_id: str,
        callback: Callable,
    ):
        """Send an approval request with YES/NO buttons."""
        if not self.bot or not self.owner_chat_id:
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("YES", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton("NO", callback_data=f"deny:{approval_id}"),
            ]
        ])
        self._pending_approvals[approval_id] = callback
        await self.bot.send_message(
            chat_id=self.owner_chat_id,
            text=f"Approval needed:\n{description}",
            reply_markup=keyboard,
        )

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks (approval responses)."""
        query = update.callback_query
        await query.answer()

        data = query.data  # e.g., "approve:email_123"
        action, approval_id = data.split(":", 1)

        callback = self._pending_approvals.pop(approval_id, None)
        if callback:
            approved = action == "approve"
            await callback(approved)
            await query.edit_message_text(
                f"{'Approved' if approved else 'Denied'}: {approval_id}"
            )
        else:
            await query.edit_message_text("Approval expired or already handled.")

    # --- Utilities ---

    def _add_context(self, sender: str, message: str):
        """Track recent messages for context window."""
        self._context_messages.append({"sender": sender, "text": message[:500]})
        if len(self._context_messages) > 20:
            self._context_messages.pop(0)

    def get_context(self) -> str:
        """Get recent conversation context."""
        return "\n".join(
            f"{m['sender']}: {m['text']}" for m in self._context_messages
        )

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list:
        """Split a long message into Telegram-safe chunks."""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Try to break at newline
            break_at = text.rfind("\n", 0, max_len)
            if break_at == -1:
                break_at = max_len
            chunks.append(text[:break_at])
            text = text[break_at:].lstrip("\n")
        return chunks
