# JARVIS Messaging Platform Research: WhatsApp Cloud API vs Telegram Bot API

**Date:** 2026-04-08
**Goal:** Yusuf texts a number/bot, JARVIS responds. Voice notes must work. Session must be persistent.

---

## 1. WhatsApp Cloud API (Official Meta Business API)

### 1.1 What It Is

The official REST API hosted by Meta for programmatic WhatsApp messaging. You register a phone number as a WhatsApp Business number, and interact with it through Meta's servers.

### 1.2 Setup Steps (Exact)

1. Create a Meta Business Manager account at business.facebook.com
2. Create a Meta Developer account at developers.facebook.com
3. Create a new app (select "Business" type)
4. Add the "WhatsApp" product to the app
5. Connect or create a WhatsApp Business Account (WABA)
6. Register a phone number (must NOT be already on WhatsApp; can be mobile or landline; must receive SMS/call for verification)
7. Add a payment method (mandatory)
8. Generate an access token (temporary user token for testing, system token for production)
9. Create and submit message templates for review (takes minutes to hours)
10. Set up webhook endpoint (HTTPS with valid TLS certificate, no self-signed)
11. Configure webhook verification (GET endpoint returning hub.challenge)
12. Subscribe to message events

**Estimated setup time:** 2-5 hours for initial setup, plus days-to-weeks for business verification.

### 1.3 Pricing

As of July 1, 2025, WhatsApp uses **per-message pricing** (replacing conversation-based pricing).

| Message Category | US Rate (per msg) | Notes |
|---|---|---|
| **Service (replies within 24h window)** | **FREE** | Unlimited. This is key for JARVIS. |
| Utility templates | ~$0.006 | Free if sent within active 24h customer service window |
| Marketing templates | $0.03-$0.04 | Most expensive category |
| Authentication templates | ~$0.004-$0.0456 | Varies by country |

**The critical insight:** If Yusuf always messages JARVIS first (opening a 24-hour customer service window), all replies from JARVIS within that 24 hours are completely free. No per-message charge. No monthly cap. This was changed November 2024 -- previously capped at 1,000 free conversations/month.

If Yusuf hasn't messaged in 24+ hours, JARVIS would need to send a pre-approved template message to re-initiate, which costs ~$0.006 (utility) in the US.

### 1.4 Rate Limits

| Limit | Value |
|---|---|
| Throughput | 80 messages/second/phone number (default) |
| Tier 1 (new numbers) | 1,000 unique recipients/24h |
| Tier 2 | 10,000 unique recipients/24h |
| Tier 3 | 100,000 unique recipients/24h |
| Unlimited tier | Enterprise only |

For personal use (1 user = Yusuf), these limits are irrelevant. You will never hit them.

### 1.5 Voice Note Support

- **Incoming format:** OGG Opus (`audio/ogg; codecs=opus`)
- **Receiving flow:** Webhook delivers message with media ID -> call Media endpoint to get download URL -> download OGG file -> transcribe with Whisper/similar
- **Sending voice:** Upload OGG Opus file via Media endpoint, then send as audio message
- **Supported audio MIME types:** `audio/ogg; codecs=opus`, `audio/mpeg`, `audio/amr`, `audio/mp4`, `audio/aac`
- **Max audio file size:** 16 MB

### 1.6 Webhook Setup

- Must be HTTPS with valid TLS certificate (no self-signed)
- Requires public URL (use ngrok for dev, proper domain for prod)
- Verification via GET request with `hub.verify_token` challenge
- Event notifications via POST with JSON payload
- Supports message status callbacks (sent, delivered, read)

### 1.7 The Dealbreaker: Meta's AI Chatbot Ban

**Effective January 15, 2026, Meta banned general-purpose AI chatbots from WhatsApp Business Platform.**

Key facts:
- Announced October 2025 via TechCrunch
- Enforced for new users since October 15, 2025
- Full enforcement for all users from January 15, 2026
- **Banned:** Open-ended conversational AI assistants (ChatGPT, Perplexity, Copilot, and any "ask me anything" style bot)
- **Allowed:** Structured business bots (order tracking, support, bookings, notifications)
- **Reason:** General-purpose AI bots generated massive traffic without revenue for Meta
- **Consequence:** Account disabled/banned if detected

**JARVIS as a personal AI assistant that answers arbitrary questions, processes voice notes, and has open-ended conversation is EXACTLY what this policy targets.** Using WhatsApp Cloud API for JARVIS risks account termination.

### 1.8 Additional Risks

- The phone number registered with the Business API can NO LONGER be used in the regular WhatsApp app
- Business verification can take up to 2 weeks
- Meta can change pricing, policies, or revoke access at any time
- Requires maintaining a Facebook/Meta developer account in good standing
- Template messages must be pre-approved (limits flexibility for JARVIS-initiated messages)

### 1.9 Relevant GitHub Projects

- **mehnoorsiddiqui/whatsapp-voice-transcriber** - WhatsApp voice transcription using Cloud API + OpenAI Whisper
- **whatsapp-webhook/whatsapp-webhook** (migrated to receevi/receevi) - Webhook receiver for Cloud API
- **EvolutionAPI/evolution-api** - Self-hosted WhatsApp integration (uses Baileys, NOT official API; connects via WhatsApp Web protocol; avoids Business API restrictions but violates WhatsApp ToS)

---

## 2. Telegram Bot API

### 2.1 What It Is

Free, official API from Telegram for building bots. Bots are special Telegram accounts that are operated by software. You create one via @BotFather, get a token, and start coding.

### 2.2 Setup Steps (Exact)

1. Open Telegram, search for @BotFather (verify blue checkmark)
2. Send `/newbot`
3. Choose a display name (e.g., "JARVIS")
4. Choose a username (must end in "bot", e.g., "yusuf_jarvis_bot")
5. Receive API token (store securely)
6. Optionally set bot description, profile picture, commands via BotFather
7. Set up webhook: `curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://your-server.com/webhook"`
8. Or use long polling (no server needed, simpler)

**Estimated setup time:** 5-15 minutes to create bot and get it responding. Under 1 hour for full webhook deployment.

### 2.3 Pricing

**Completely free.** No per-message fees. No monthly fees. No API fees. No limit on number of bots. No payment method required.

The only paid feature is "Paid Broadcasts" for bots sending to 10,000+ users at >30 msg/sec, which is irrelevant for personal use.

| Item | Cost |
|---|---|
| Bot creation | Free |
| Messages sent/received | Free |
| Voice notes sent/received | Free |
| Media upload/download | Free |
| Webhook usage | Free |
| File storage on Telegram servers | Free |

### 2.4 Rate Limits

| Limit | Value |
|---|---|
| Messages to same chat | ~1 per second (soft limit) |
| Broadcast to different users | 30 messages/second |
| Group messages | 20 messages/minute |
| Inline query results | No documented limit |

For personal use (1 user = Yusuf), sending 1 msg/sec to the same chat is more than sufficient. You will never hit any limit.

### 2.5 File Size Limits

| Operation | Standard API | Local Bot API Server |
|---|---|---|
| Upload (send) | 50 MB | 2,000 MB (2 GB) |
| Download (receive) | 20 MB | Unlimited (up to 2 GB) |
| Photo send | 10 MB | 10 MB |

Voice notes are typically 50-500 KB for a few seconds, well within all limits.

### 2.6 Voice Note Support

- **Incoming format:** OGG Opus (`.oga` extension, `audio/ogg` MIME type)
- **Voice object fields:** `file_id`, `file_unique_id`, `duration`, `mime_type`, `file_size`
- **Download flow:** `voice.get_file()` -> `file.download_to_drive("voice.ogg")` -> transcribe with Whisper
- **Sending voice:** Must be OGG with Opus codec, or MP3, or M4A. Max 50 MB.
- **Conversion needed for Whisper:** OGG Opus -> MP3/WAV via pydub + ffmpeg (trivial)

**Proven pattern:** Multiple production bots exist that do exactly this (receive voice -> Whisper transcribe -> LLM response). The article "Whisper + GPT-3.5 + Telegram Bot = J.A.R.V.I.S." on Better Programming is literally this exact use case.

### 2.7 Webhook vs Polling

| Feature | Webhook | Long Polling |
|---|---|---|
| Latency | Instant (<100ms) | ~1-2 seconds |
| Setup complexity | Need HTTPS URL + valid TLS cert | Zero setup |
| Reliability | Excellent in production | Excellent, simpler to debug |
| Resource usage | Lower (event-driven) | Slightly higher (persistent connection) |
| Supported ports | 443, 80, 88, 8443 | N/A |
| Self-signed certs | Supported (upload public key) | N/A |
| Best for | Production, >10 daily users | Dev, <10 users, behind firewalls |

**For JARVIS (1 user):** Start with polling for simplicity, switch to webhook when deploying to a server. Both work perfectly.

### 2.8 Session Persistence

Telegram Bot API is stateless -- no built-in session management. But this is actually ideal for JARVIS because:
- You control the session layer entirely (SQLite, PostgreSQL, Redis, or in-memory)
- python-telegram-bot has `ConversationHandler` for state machines
- Real projects (like the Telegram-AI-Agent on GitHub) use PostgreSQL for persistent chat memory
- You can store full conversation history and retrieve context on each message

### 2.9 Ban/Restriction Risk

- **Virtually zero for personal use.** Telegram actively encourages bot development.
- No policy against AI chatbots (unlike WhatsApp)
- No policy against general-purpose bots
- Bots can only message users who have started a conversation with them first (anti-spam by design)
- No business verification required
- No phone number sacrifice (your personal Telegram account is separate from the bot)

### 2.10 Relevant GitHub Projects & Libraries

**Libraries:**
- **python-telegram-bot/python-telegram-bot** (v22.7) - The gold standard Python library. Active development, excellent docs, 27k+ stars
- **aiogram/aiogram** - Async Python library, modern design, popular alternative
- **eternnoir/pyTelegramBotAPI** - Another popular Python wrapper

**AI Assistant Projects:**
- **FlyingFathead/whisper-transcriber-telegram-bot** - Production Whisper transcription bot
- **Malith-Rukshan/whisper-transcriber-bot** - CPU-only Whisper bot, handles OGG/MP3/WAV/FLAC
- **HKUDS/nanobot** - Ultra-lightweight personal AI agent
- **AIXerum/AI-Telegram-Assistant** - Personal assistant handling emails, schedule, to-do lists via Telegram
- **OpenClaw** (171k GitHub stars) - Open-source AI assistant with Telegram as primary interface; persistent memory, scheduled check-ins, any AI model

---

## 3. Head-to-Head Comparison

| Criterion | WhatsApp Cloud API | Telegram Bot API |
|---|---|---|
| **Cost** | Free for service replies within 24h window; ~$0.006/msg for bot-initiated | **Completely free, always** |
| **Setup time** | 2-5 hours + days for verification | **5-15 minutes** |
| **Voice note support** | OGG Opus, works well | **OGG Opus, works well (identical)** |
| **Voice note transcription** | Proven (Whisper) | **Proven (Whisper, many examples)** |
| **Natural for Yusuf** | Yes, already uses WhatsApp daily | Requires opening Telegram app |
| **Ban risk for AI assistant** | **HIGH - explicitly banned since Jan 2026** | **None - encouraged** |
| **Phone number sacrifice** | Yes, number removed from personal WhatsApp | **No sacrifice** |
| **Session persistence** | You build it (same) | You build it (same) |
| **24h messaging window** | Yes, must re-engage with template after 24h | **No restriction** |
| **Template approval** | Required for bot-initiated messages | **Not required** |
| **Webhook setup** | Valid TLS required, no self-signed | **Self-signed certs OK, or use polling** |
| **Media support** | Images, docs, audio, video, location, contacts | **Images, docs, audio, video, location, contacts, stickers, polls** |
| **Business verification** | Required (can take weeks) | **Not required** |
| **Meta/corporate dependency** | High (Meta controls everything) | **Low (Telegram, open protocol)** |
| **Existing JARVIS examples** | Few | **Many (OpenClaw, nanobot, multiple tutorials)** |
| **Rate limits (personal use)** | Irrelevant (way above need) | Irrelevant (way above need) |
| **Reliability/uptime** | Good (Meta infrastructure) | Good (Telegram infrastructure) |
| **Open-source ecosystem** | Limited | **Massive (python-telegram-bot, aiogram, etc.)** |

---

## 4. The WhatsApp Ban -- This Is the Deciding Factor

This cannot be understated. As of January 15, 2026, Meta explicitly bans:

> "Standalone, general-purpose AI assistants -- bots you message for wide-ranging conversation within WhatsApp"

JARVIS is literally this. A personal AI assistant that:
- Answers arbitrary questions
- Processes voice notes and responds
- Has open-ended, persistent conversation
- Acts as a general-purpose assistant

Sources:
- [TechCrunch: WhatsApp changes its terms to bar general-purpose chatbots](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/)
- [respond.io: Not All Chatbots Are Banned -- WhatsApp's 2026 AI Policy Explained](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)
- [chatboq.com: Meta Blocks Third-Party AI Chatbots on WhatsApp in 2026](https://chatboq.com/blogs/third-party-ai-chatbots-ban)

Even if enforcement is slow, building JARVIS on a platform that has explicitly banned your use case is a fundamental architectural risk.

---

## 5. Recommendation

### Use Telegram Bot API. It is the clear winner.

**Reasoning:**

1. **No ban risk.** WhatsApp has explicitly banned general-purpose AI assistants as of January 2026. Telegram has no such restriction and actively encourages bot development. This alone is decisive.

2. **Zero cost, forever.** No per-message fees, no payment method required, no pricing tiers to worry about. WhatsApp's "free within 24h window" has caveats and could change.

3. **5-minute setup vs. days.** BotFather gives you a token in seconds. WhatsApp requires Meta Business accounts, Facebook apps, business verification (weeks), phone number sacrifice, payment methods, and template approvals.

4. **No phone number sacrifice.** WhatsApp Cloud API permanently claims the phone number -- it can never be used in the normal WhatsApp app again. Telegram keeps your personal account completely separate.

5. **No 24-hour window.** WhatsApp restricts bot-initiated messages after 24 hours of inactivity, requiring pre-approved templates. Telegram has no such restriction -- JARVIS can proactively message Yusuf anytime.

6. **Proven ecosystem.** Multiple production AI assistants (OpenClaw with 171k stars, nanobot, etc.) use Telegram as their messaging layer. The exact pattern (voice note -> Whisper -> LLM -> reply) has been built and documented many times.

7. **Voice notes work identically.** Both platforms use OGG Opus. The transcription pipeline is the same. Telegram just has better library support for handling it.

8. **The only downside is friction.** Yusuf would need to open Telegram instead of WhatsApp. This is a real cost -- but it's a one-time habit change vs. a permanent architectural risk.

### Mitigation for the "I use WhatsApp daily" concern:

- Pin the JARVIS bot chat to the top of Telegram
- Enable Telegram notifications for the bot
- Telegram is lightweight (smaller than WhatsApp) and starts instantly
- Many people already use both apps
- The Telegram desktop and web apps make it accessible everywhere
- Consider: would you rather change one habit, or build on a platform that has banned your use case?

### Recommended Stack:

```
Telegram Bot API
  + python-telegram-bot (v22.x)
  + Webhook mode (for production) or Polling (for development)
  + OpenAI Whisper API (for voice transcription)
  + Your LLM of choice (Claude, GPT, local)
  + SQLite or PostgreSQL (for persistent session/memory)
  + ffmpeg + pydub (for audio format conversion)
```

---

## Sources

- [WhatsApp Business Platform Pricing](https://business.whatsapp.com/products/platform-pricing)
- [WhatsApp Cloud API Get Started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
- [WhatsApp Messaging Limits](https://developers.facebook.com/docs/whatsapp/messaging-limits/)
- [WhatsApp Webhook Setup](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks/)
- [WhatsApp Audio Messages](https://developers.facebook.com/docs/whatsapp/cloud-api/messages/audio-messages/)
- [TechCrunch: WhatsApp bans general-purpose chatbots](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/)
- [respond.io: WhatsApp 2026 AI Policy](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)
- [Telegram Bot API Official Docs](https://core.telegram.org/bots/api)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)
- [python-telegram-bot Docs](https://docs.python-telegram-bot.org/en/stable/)
- [python-telegram-bot Webhooks Wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks)
- [Telegram Rate Limits](https://limits.tginfo.me/en)
- [Telegram Local Bot API Server](https://github.com/tdlib/telegram-bot-api)
- [Whisper + Telegram = JARVIS (Better Programming)](https://betterprogramming.pub/whisper-gpt3-5-telegram-bot-j-a-r-v-i-s-794e19da6ee3)
- [WhatsApp Voice Transcriber (GitHub)](https://github.com/mehnoorsiddiqui/whatsapp-voice-transcriber)
- [EvolutionAPI (GitHub)](https://github.com/EvolutionAPI/evolution-api)
- [FlyingFathead Whisper Telegram Bot (GitHub)](https://github.com/FlyingFathead/whisper-transcriber-telegram-bot)
- [OpenClaw Telegram Setup (DigitalOcean)](https://www.digitalocean.com/resources/articles/what-is-openclaw)
- [WhatsApp API Rate Limits (WATI)](https://www.wati.io/en/blog/whatsapp-business-api/whatsapp-api-rate-limits/)
- [WhatsApp API Pricing 2026 (Chatarmin)](https://chatarmin.com/en/blog/whats-app-api-pricing)
- [Telegram Webhook vs Polling (grammY)](https://grammy.dev/guide/deployment-types)
