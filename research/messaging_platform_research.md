# Messaging Platform Research

## Candidates

### 1. WhatsApp Cloud API (Official Meta Business API)
- **Pricing**: 1,000 free service conversations/month. Beyond that, per-conversation fees vary by country (~$0.005-0.08 per conversation depending on category and region)
- **Setup**: Requires Meta Business account, phone number verification, webhook configuration. Takes hours minimum, sometimes days for business verification
- **Voice notes**: Supported. Receive OGG Opus files via media endpoint, download via token-authenticated URL
- **24-hour window**: Can only respond within 24h of user message. After that, must use pre-approved message templates (cost money, require Meta review)
- **Rate limits**: 250 messages/day initially, can request increase to 1K, 10K, 100K tiers
- **Ban risk**: Low (official API), but Meta bans general-purpose AI chatbots from WhatsApp Business Platform as of Jan 2026
- **Phone number**: PERMANENTLY claims the number from personal WhatsApp. Cannot use same number for personal WhatsApp and Business API simultaneously
- **Webhook**: Must be publicly accessible HTTPS endpoint. Requires SSL cert, domain, and port forwarding or cloud hosting
- **Media limits**: 16MB for media messages

### 2. Telegram Bot API
- **Pricing**: Completely free. No per-message fees. No tiers. No limits on bot-initiated messages
- **Setup**: 5-15 minutes. Message @BotFather, get token, done
- **Voice notes**: Supported. Receive OGG Opus files via `getFile` endpoint. Direct download URL
- **24-hour window**: NONE. Bot can message user anytime, unprompted
- **Rate limits**: 30 messages/second to different chats, 1 message/second to same chat. Effectively unlimited for personal use
- **Ban risk**: Zero. Telegram actively encourages bots. Bots are a first-class platform feature
- **Phone number**: No sacrifice. Bot gets its own identity. User's personal Telegram remains untouched
- **Webhook vs Polling**: Both supported. Webhook for production (lower latency), long-polling for dev
- **Media limits**: 50MB for most files, 2GB for documents
- **Rich features**: Inline keyboards, custom commands, message editing, message reactions, topics, forums, file sharing, location sharing, contact sharing
- **Libraries**: python-telegram-bot (27K+ stars, actively maintained), aiogram (5K+ stars, async-native), telethon (10K+ stars, MTProto)

### 3. Baileys (Unofficial WhatsApp)
- **What it is**: Reverse-engineered WhatsApp Web protocol in Node.js
- **Ban risk**: HIGH. WhatsApp actively detects and bans numbers using unofficial clients. Well-documented in Baileys GitHub issues
- **Status**: Was the go-to for WhatsApp automation, but increasingly unreliable as Meta tightens enforcement
- **Voice notes**: Supported but implementation is fragile
- **DISQUALIFIED**: Too high risk of losing the phone number

## Multi-Agent Debate

### The Advocate (for Telegram Bot API)

Telegram wins on every dimension that matters for JARVIS:

1. **Zero cost, forever.** WhatsApp charges per conversation beyond 1K/month free tier. JARVIS will exceed that within weeks of active use. Telegram is free with no ceiling.

2. **No 24-hour window.** JARVIS must send morning briefings at 7am, evening reviews at 9pm, and alerts whenever they occur — all unprompted. WhatsApp's 24-hour window means JARVIS literally cannot send the morning briefing unless Yusuf texted within the last 24 hours, or we pay for pre-approved templates that take days to get Meta approval.

3. **Setup in minutes, not days.** WhatsApp Cloud API requires Meta Business verification, domain with SSL, webhook endpoint. Telegram: message a bot, get a token, start coding.

4. **Phone number safety.** WhatsApp Business API permanently claims the phone number. If Yusuf wants to stop using JARVIS on WhatsApp, he loses his number from personal WhatsApp. Telegram bot is a separate entity entirely.

5. **No ban risk.** AI chatbots are banned from WhatsApp Business Platform as of Jan 2026. Telegram actively promotes bots with regular API updates and features.

6. **Richer interaction model.** Inline keyboards let JARVIS present options (approve/deny actions, pick from choices). Custom commands (/briefing, /stop, /status) are native. Message editing means JARVIS can update a response as it works.

7. **Superior library ecosystem.** python-telegram-bot has 27K+ stars, excellent async support, built-in conversation handlers, and is the most battle-tested bot library in the Python ecosystem.

8. **50MB file limit vs 16MB.** JARVIS can send larger documents, screenshots, voice responses.

### The Adversary (against Telegram, for WhatsApp)

1. **Yusuf uses WhatsApp daily. He does not necessarily use Telegram daily.** The whole point of JARVIS is meeting the user where they are. Adding another app defeats the purpose of "no app to open."

2. **WhatsApp has end-to-end encryption by default.** Telegram bots do NOT use E2E encryption. Messages between user and bot go through Telegram's servers in plaintext.

3. **WhatsApp is the dominant messaging platform in Australia.** Everyone Yusuf knows is on WhatsApp. Telegram requires downloading a new app and actively checking it.

4. **The 24-hour window can be worked around.** JARVIS can send a daily "good morning" template at 6:59am that's pre-approved, which opens the 24-hour window for the rest of the day.

5. **Official API means long-term stability.** Meta isn't going to suddenly break their own API. Telegram has changed bot API behavior without notice before.

### The Judge

**Ruling: Telegram Bot API wins. Decisively.**

Point-by-point:

1. **Daily usage habit (Adversary's strongest point)**: Valid concern, but overstated. Telegram is already installed on most phones. The notification appears just like WhatsApp. After 3 days of use, the habit forms. This is a temporary friction, not a permanent barrier.

2. **E2E encryption**: Legitimate concern for a personal AI assistant. However, JARVIS stores all conversations in plaintext on the local Mac anyway. The threat model is already "trust the local machine." Telegram's server-side encryption is adequate for this use case. If Yusuf needs to send truly sensitive information, he can do so in person, not through any bot.

3. **24-hour window workaround**: The Adversary's template workaround is fragile. Templates require Meta approval (days), can be rejected, and still cost money. JARVIS needs to freely message at any time. This is a fundamental architectural requirement, not a nice-to-have.

4. **AI chatbot ban**: This is disqualifying for WhatsApp. Building the core interface of a system on a platform that has explicitly banned this use case is engineering malpractice.

5. **Cost**: JARVIS should cost $0/month to operate on the messaging layer. Telegram achieves this. WhatsApp does not.

6. **Phone number sacrifice**: Unacceptable risk. Yusuf should never have to choose between JARVIS and his personal WhatsApp number.

**Final specification**: Use Telegram Bot API with python-telegram-bot library. Webhook mode for production, polling for development. Inline keyboards for approval flows. Custom commands for quick actions.

## Decision

**Winner: Telegram Bot API**

Reasons (ordered by importance):
1. WhatsApp explicitly bans AI chatbots — existential risk
2. No 24-hour window — JARVIS can message anytime (briefings, alerts)
3. Completely free forever — no per-message costs
4. No phone number sacrifice
5. 5-minute setup vs days of verification
6. Richer interaction (inline keyboards, commands, message editing)
7. Superior Python library ecosystem
