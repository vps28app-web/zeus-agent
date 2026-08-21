# Gateways do Zeus

O Zeus pode receber tarefas via Telegram, WhatsApp ou Discord. O Python gateway despacha mensagens para o agent loop e envia respostas de volta.

## Telegram

### Setup

1. Crie um bot com [@BotFather](https://t.me/BotFather) e obtenha o token.
2. Adicione ao `.env`:

```bash
ZEUS_TELEGRAM_TOKEN=seu-token
ZEUS_TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

3. Inicie o gateway:

```bash
cd /home/vps28/Documentos/Dev/Zeus
source .venv/bin/activate
python -m zeus.gateway --platform telegram
```

Ou use o comando instalado:

```bash
zeus-gateway --platform telegram
```

## WhatsApp

O WhatsApp usa uma ponte Node.js com Baileys + um gateway Python que se comunica via HTTP local.

### Setup

1. Instale as dependências e construa a ponte:

```bash
cd /home/vps28/Documentos/Dev/Zeus/gateway/whatsapp/baileys
npm install
npm run build
```

2. Inicie a ponte e escaneie o QR code com o WhatsApp (Dispositivos Conectados):

```bash
node dist/index.js
```

3. Adicione ao `.env`:

```bash
ZEUS_WHATSAPP_URL=http://127.0.0.1:9877
ZEUS_WHATSAPP_ALLOWED_NUMBERS=5511999999999@s.whatsapp.net
```

4. Inicie o gateway Python:

```bash
python -m zeus.gateway --platform whatsapp
```

## Discord

### Setup

1. Crie uma aplicação e bot no [Discord Developer Portal](https://discord.com/developers/applications).
2. Habilite a permissão "Message Content Intent" nas configurações do bot.
3. Adicione ao `.env`:

```bash
ZEUS_DISCORD_TOKEN=seu-token
ZEUS_DISCORD_ALLOWED_USER_IDS=123456789
# opcional: ZEUS_DISCORD_ALLOWED_CHANNEL_IDS=987654321
```

4. Inicie o gateway:

```bash
python -m zeus.gateway --platform discord
```

## Setup interativo

O CLI de gateway também oferece setup guiado:

```bash
python -m zeus.gateway setup telegram
python -m zeus.gateway setup whatsapp
python -m zeus.gateway setup discord
```

## Systemd

Para instalar os serviços no systemd:

```bash
sudo ./scripts/install-systemd.sh
```

Serviços criados:

- `zeus-sandbox.service`
- `zeus-telegram-gateway.service`
- `zeus-whatsapp-bridge.service`
- `zeus-whatsapp-gateway.service`
- `zeus-discord-gateway.service`

Logs:

```bash
journalctl -u zeus-sandbox.service -f
journalctl -u zeus-telegram-gateway.service -f
journalctl -u zeus-whatsapp-bridge.service -f
journalctl -u zeus-whatsapp-gateway.service -f
journalctl -u zeus-discord-gateway.service -f
```

## Segurança

- Cada gateway responde apenas a usuários/números/chat IDs configurados.
- Ações de escrita em arquivo são negadas por padrão nos gateways (callback de permissão retorna `False`).
- Permissões são gerenciadas por `zeus.gateway.confirmations.ConfirmationManager`.
