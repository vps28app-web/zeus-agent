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
cd /caminho/para/Zeus
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
cd /caminho/para/Zeus/gateway/whatsapp/baileys
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

## Instagram Messaging

A integração usa a API oficial de mensagens da Meta para contas Instagram Profissionais. Ela recebe DMs por webhook HTTPS e só responde a conversas iniciadas pelo usuário; as respostas estão sujeitas à janela de atendimento da Meta.

Pré-requisitos no Meta for Developers:

- Conta Instagram Profissional e app Meta publicado.
- Permissão `instagram_business_manage_messages` (ou a permissão exigida pelo fluxo de login escolhido) e assinatura do webhook `messages`.
- Instagram Account ID, access token, App Secret e um verify token definido por você.
- URL HTTPS pública apontando para `/webhook`; um reverse proxy/túnel deve encaminhá-la para a porta local 8765.

Documentação oficial: [Instagram Messaging API](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api) e [Webhooks](https://developers.facebook.com/docs/messenger-platform/instagram/features/webhook/).

Configure os dados localmente, com os segredos digitados em prompts mascarados:

```bash
zeus gateway setup instagram
zeus gateway start instagram
# ou instalar como serviço systemd do usuário:
zeus gateway start instagram --mode systemd
```

Não envie tokens ou App Secret por DM. O bot só recebe `!zeus` depois que um gateway já estiver configurado. Comandos disponíveis:

```text
!zeus
!zeus status
!zeus provider <nome> [modelo]
!zeus model <id>
!zeus setup
```

`!zeus setup` mostra como abrir `zeus setup` no terminal. Chaves nunca são configuradas por mensagem; faça isso em prompts locais mascarados.

## Setup interativo

O assistente de primeira configuração pode preparar provedor/modelo e várias integrações:

```bash
zeus setup
# selecione, por exemplo: whatsapp, instagram
```

O WhatsApp ainda exige a ponte Baileys e o pareamento do QR code; o Instagram exige a URL HTTPS pública e o app Meta configurado.

O CLI de gateway também oferece setup guiado por plataforma:

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
