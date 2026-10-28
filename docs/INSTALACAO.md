# Instalação do Zeus

Este guia instala o Zeus a partir de um checkout Git. A instalação Python não requer root; root só é necessário se você optar pelo serviço systemd da sandbox.

## Requisitos

- Linux ou macOS com Bash, Git e Python 3.8+.
- GitHub público: o clone HTTPS não exige conta nem chave SSH.
- Go 1.20+ é opcional para compilar a sandbox. Para instalar o serviço systemd, Go é necessário: o instalador compila a sandbox a partir do snapshot do commit limpo, ignorando qualquer binário pré-compilado no checkout.
- Node.js/npm é opcional; necessário apenas para compilar a ponte WhatsApp Baileys.

## Instalação recomendada

```bash
git clone https://github.com/vps28app-web/zeus-agent.git
cd zeus-agent
./scripts/install.sh
```

O instalador roda como usuário normal e:

1. cria `.venv` no checkout e instala o pacote em modo editável, incluindo `zeus` e `zeus-gateway`;
2. cria ou reutiliza `ZEUS_HOME` (padrão `~/.zeus`) e protege o arquivo `.env` com permissão `600`;
3. gera um token aleatório da sandbox quando ele está ausente ou vazio (um token existente inválido causa erro claro);
4. grava o caminho de estado em `.zeus-home` para a configuração posterior do systemd;
5. cria launchers em `~/.local/bin`, sem sobrescrever comandos preexistentes que não foram criados pelo instalador;
6. tenta compilar a sandbox apenas em Linux amd64 quando Go está instalado.

O instalador não instala pacotes do sistema, não ativa serviços systemd e não solicita credenciais. Se `~/.local/bin` não estiver no `PATH`, inclua esse diretório ou use diretamente `.venv/bin/zeus`.

## Instalação completa com npm

Em Debian/Ubuntu amd64 com Go 1.20+ disponível nos repositórios apt, a alternativa npm automatiza os pré-requisitos de sistema, a instalação Python, a compilação e o serviço privilegiado da sandbox:

```bash
npm run install:zeus
```

Execute o comando na raiz do checkout; não é necessário rodar `npm install`. Para iniciar sem clonar manualmente:

```bash
npx --yes --package=git+https://github.com/vps28app-web/zeus-agent.git zeus-install
```

Requer Node.js 18+, npm e Git. O instalador pergunta antes de instalar `git`, Python/venv e Go via apt; depois executa o instalador normal, solicita autorização local para instalar e iniciar `zeus-sandbox.service`, verifica se o serviço ficou ativo e abre `zeus setup` para configurar o provedor. Use `-- --skip-setup` com `npm run install:zeus` para pular a configuração interativa.

Esse fluxo completo não suporta Windows nativo, macOS, Linux ARM ou distribuições fora da família Debian/Ubuntu. A sandbox atual requer Linux amd64, systemd, cgroup v2 e recursos de namespace/seccomp. Não execute o comando como root; a autorização administrativa é solicitada apenas para as etapas privilegiadas.

### Configurar o provedor

```bash
zeus setup
```

O assistente pede o provedor/modelo e as credenciais necessárias por entrada mascarada. Também é possível configurar pelo CLI com `/models` e `/config set NOME_DA_CHAVE`. Não coloque chaves reais no repositório.

Para iniciar a CLI:

```bash
zeus
# ou
python -m zeus.cli
```

Uma consulta de uma só vez:

```bash
zeus -q "explique a arquitetura do projeto"
```

## Sandbox Go (opcional)

Quando o instalador não puder compilá-la, ou se quiser recompilar manualmente:

```bash
cd sandbox
go build -o sandbox ./cmd/sandbox
```

Para iniciar manualmente, o processo do servidor deve receber o mesmo `ZEUS_SANDBOX_AUTH_TOKEN` configurado para o cliente Zeus. Consulte [SANDBOX.md](SANDBOX.md) para executar com token sem expor outras credenciais ao serviço.

### Instalação como serviço systemd

Somente em Linux amd64, depois que o instalador criou `.zeus-home` e o token; requer Go 1.20+ e compila a sandbox novamente a partir do commit limpo (não usa `sandbox/sandbox` do checkout):

```bash
sudo ./scripts/install-systemd.sh
```

O script valida o ambiente, copia o binário para `/usr/local/lib/zeus/sandbox` como `root:root`, grava somente o token em `/etc/zeus/sandbox.env` com permissão `600` e instala as units. A unit sandbox executa essa cópia root-owned, não o binário editável no checkout. As units de gateways usam o usuário dono do projeto e o `.env` de `ZEUS_HOME`.

Antes de instalar systemd:

- o checkout precisa pertencer a um usuário normal, não a `root`, e estar limpo no Git; a unit usa arquivos do commit atual;
- instale apenas um checkout/revisão que você confia: a sandbox será executada como root, embora o binário seja copiado para uma localização root-owned;
- o caminho do checkout e `ZEUS_HOME` não pode conter espaços ou caracteres especiais incompatíveis com as units;
- revise `ZEUS_HOME/.env` e configure as credenciais do gateway que pretende iniciar;
- root, cgroup v2 e os recursos de kernel descritos em [SANDBOX.md](SANDBOX.md) devem estar disponíveis.

O script instala todas as units, mas habilita e inicia somente a sandbox. Os gateways ficam desabilitados até você configurá-los. Inicie um gateway para a sessão atual com `sudo systemctl start zeus-telegram-gateway.service`; para iniciar também no boot, use `sudo systemctl enable --now zeus-telegram-gateway.service`.

## Atualizar

A instalação permanece ligada ao checkout. Para atualizar:

```bash
cd /caminho/para/zeus-agent
git pull --ff-only
./scripts/install.sh
```

A atualização preserva `.env`, `ZEUS_HOME`, o banco de dados e a memória. O instalador recusa caminhos de estado ou credenciais que sejam symlinks e não remove alterações locais do Git.

## Resolução de problemas

- **`python3 -m venv` falha:** instale o pacote de virtualenv da sua distribuição (por exemplo, `python3-venv` no Debian/Ubuntu).
- **`zeus: command not found`:** confirme que `~/.local/bin` está no `PATH` ou use `.venv/bin/zeus`.
- **Sandbox ausente:** instale Go e execute `cd sandbox && go build -o sandbox ./cmd/sandbox` em Linux amd64.
- **Sandbox recusa inicialização:** configure o token bearer e verifique root, cgroup v2, namespaces e seccomp conforme [SANDBOX.md](SANDBOX.md).
- **Não use `sudo` no instalador Python:** só `scripts/install-systemd.sh` requer elevação.
