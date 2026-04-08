import makeWASocket, {
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidBroadcast,
    isJidGroup,
    downloadMediaMessage,
    getContentType,
    Browsers,
} from 'baileys'
import { Boom } from '@hapi/boom'
import pino from 'pino'
import qrcode from 'qrcode-terminal'
import { writeFileSync, existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const AUTH_DIR = join(__dirname, 'auth_info')
const MEDIA_DIR = join(__dirname, 'media')

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })
if (!existsSync(MEDIA_DIR)) mkdirSync(MEDIA_DIR, { recursive: true })

const logger = pino({ level: 'silent' })

// IPC: newline-delimited JSON over stdout (Node→Python) and stdin (Python→Node)
function sendEvent(event) {
    process.stdout.write(JSON.stringify(event) + '\n')
}

// Read commands from Python via stdin
let stdinBuffer = ''
process.stdin.setEncoding('utf-8')
process.stdin.on('data', (chunk) => {
    stdinBuffer += chunk
    const lines = stdinBuffer.split('\n')
    stdinBuffer = lines.pop()
    for (const line of lines) {
        if (line.trim()) {
            try {
                handleCommand(JSON.parse(line))
            } catch (e) {
                sendEvent({ type: 'error', error: String(e), context: 'stdin_parse' })
            }
        }
    }
})

let sock = null

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
    const { version } = await fetchLatestBaileysVersion()

    sock = makeWASocket({
        version,
        auth: state,
        logger,
        browser: Browsers.macOS('Desktop'),
        printQRInTerminal: false,
        markOnlineOnConnect: false,
        syncFullHistory: false,
        shouldIgnoreJid: (jid) => isJidBroadcast(jid),
        generateHighQualityLinkPreview: false,
    })

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update

        if (qr) {
            // Print QR to stderr (visible in terminal) AND send as event to Python
            qrcode.generate(qr, { small: true }, (qrArt) => {
                process.stderr.write('\n' + qrArt + '\n')
                process.stderr.write('Scan this QR code with WhatsApp (Settings > Linked Devices)\n\n')
            })
            sendEvent({ type: 'qr', data: qr })
        }

        if (connection === 'close') {
            const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode
            sendEvent({ type: 'connection', status: 'closed', statusCode })

            if (statusCode !== DisconnectReason.loggedOut) {
                const delay = 1000 + Math.random() * 4000
                setTimeout(connectToWhatsApp, delay)
            } else {
                sendEvent({ type: 'connection', status: 'logged_out' })
            }
        } else if (connection === 'open') {
            sendEvent({
                type: 'connection',
                status: 'open',
                user: sock.user,
            })
        }
    })

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return

        for (const msg of messages) {
            if (msg.key.fromMe) continue
            if (msg.key.remoteJid === 'status@broadcast') continue

            const contentType = getContentType(msg.message)
            const event = {
                type: 'message',
                id: msg.key.id,
                from: msg.key.remoteJid,
                pushName: msg.pushName || '',
                isGroup: isJidGroup(msg.key.remoteJid),
                timestamp: msg.messageTimestamp,
                contentType,
                messageKey: msg.key,
            }

            if (contentType === 'conversation') {
                event.text = msg.message.conversation
            } else if (contentType === 'extendedTextMessage') {
                event.text = msg.message.extendedTextMessage.text
            } else if (contentType === 'audioMessage') {
                const audio = msg.message.audioMessage
                event.isVoiceNote = audio.ptt === true
                event.duration = audio.seconds
                try {
                    const buffer = await downloadMediaMessage(msg, 'buffer', {}, {
                        logger,
                        reuploadRequest: sock.updateMediaMessage,
                    })
                    const filename = `voice_${msg.key.id}.ogg`
                    const filepath = join(MEDIA_DIR, filename)
                    writeFileSync(filepath, buffer)
                    event.mediaPath = filepath
                } catch (e) {
                    event.mediaError = String(e)
                }
            } else if (contentType === 'imageMessage') {
                event.text = msg.message.imageMessage?.caption || ''
                try {
                    const buffer = await downloadMediaMessage(msg, 'buffer', {}, {
                        logger,
                        reuploadRequest: sock.updateMediaMessage,
                    })
                    const filename = `img_${msg.key.id}.jpg`
                    const filepath = join(MEDIA_DIR, filename)
                    writeFileSync(filepath, buffer)
                    event.mediaPath = filepath
                } catch (e) {
                    event.mediaError = String(e)
                }
            } else {
                event.text = `[${contentType || 'unknown'}]`
            }

            sendEvent(event)
        }
    })

    sock.ev.on('creds.update', saveCreds)
}

async function handleCommand(cmd) {
    try {
        if (!sock) {
            sendEvent({ type: 'error', error: 'Not connected', context: cmd.action })
            return
        }
        switch (cmd.action) {
            case 'send_text':
                await sock.sendMessage(cmd.to, { text: cmd.text })
                sendEvent({ type: 'sent', action: 'send_text', to: cmd.to })
                break

            case 'send_presence':
                await sock.sendPresenceUpdate(cmd.presence, cmd.to)
                break

            case 'read_messages':
                await sock.readMessages([cmd.messageKey])
                break

            case 'get_status':
                sendEvent({
                    type: 'status',
                    connected: !!sock?.user,
                    user: sock?.user || null,
                })
                break

            default:
                sendEvent({ type: 'error', error: `Unknown action: ${cmd.action}` })
        }
    } catch (e) {
        sendEvent({ type: 'error', error: String(e), context: `cmd_${cmd.action}` })
    }
}

sendEvent({ type: 'bridge_ready' })
connectToWhatsApp()

process.on('uncaughtException', (e) => {
    sendEvent({ type: 'error', error: String(e), context: 'uncaught' })
})
process.on('unhandledRejection', (e) => {
    sendEvent({ type: 'error', error: String(e), context: 'unhandled_rejection' })
})
