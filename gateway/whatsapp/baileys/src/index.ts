import express, { Request, Response } from 'express';
import {
  makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import * as fs from 'fs';
import * as path from 'path';

const AUTH_DIR = process.env.ZEUS_WHATSAPP_AUTH_DIR || './auth_info';
const PORT = parseInt(process.env.ZEUS_WHATSAPP_PORT || '9877', 10);
const HOST = process.env.ZEUS_WHATSAPP_HOST || '127.0.0.1';

let sock: WASocket | null = null;
const messageQueue: Array<{ from: string; text: string; timestamp: number }> = [];
let connectionState = 'connecting';

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  sock = makeWASocket({
    auth: state,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      connectionState = 'qr_required';
      console.log('Scan this QR code with WhatsApp:');
      qrcode.generate(qr, { small: true });
    }
    if (connection === 'close') {
      connectionState = 'disconnected';
      const shouldReconnect =
        (lastDisconnect?.error as Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log('Connection closed. Reconnecting:', shouldReconnect);
      if (shouldReconnect) {
        connectToWhatsApp();
      }
    } else if (connection === 'open') {
      connectionState = 'connected';
      console.log('WhatsApp connection opened');
    }
  });

  sock.ev.on('messages.upsert', async (m) => {
    for (const msg of m.messages) {
      if (msg.key.fromMe) continue;
      const text =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        '';
      if (text) {
        messageQueue.push({
          from: msg.key.remoteJid!,
          text,
          timestamp: Date.now(),
        });
      }
    }
  });
}

const app = express();
app.use(express.json());

app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', connection: connectionState });
});

app.get('/messages', (_req: Request, res: Response) => {
  const messages = [...messageQueue];
  messageQueue.length = 0;
  res.json({ messages, connection: connectionState });
});

app.post('/send', async (req: Request, res: Response) => {
  const { to, text } = req.body;
  if (!to || !text) {
    res.status(400).json({ error: 'to and text are required' });
    return;
  }
  if (!sock || connectionState !== 'connected') {
    res.status(503).json({ error: 'WhatsApp not connected' });
    return;
  }
  try {
    await sock.sendMessage(to, { text });
    res.json({ sent: true });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

app.listen(PORT, HOST, () => {
  console.log(`Zeus WhatsApp gateway listening on ${HOST}:${PORT}`);
  connectToWhatsApp();
});
