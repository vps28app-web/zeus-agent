# Plano da Camada de Sandbox (Go/Rust)

## Objetivo

Isolar a execução de comandos shell e código arbitrário do host, reduzindo riscos de segurança quando o Zeus rodar de forma autônoma.

## Por que separar do Python

O harness em Python é responsável por:
- orquestração
- prompts
- tool calling
- memória
- logs

A sandbox em Go ou Rust é responsável por:
- execução de processos isolados
- controle de recursos (CPU, memória, disco, rede)
- filesystem temporário
- comunicação segura com o harness

## Opções de tecnologia

| Opção | Prós | Contras |
|--------|------|---------|
| Go | Fácil de escrever, compilação rápida, binário único | Menos controle de sandbox nativo |
| Rust | Segurança de memória, controle fino | Curva de aprendizado maior |
| Container (Docker/Podman) | Isolamento pronto | Requer daemon e permissões |
| nsjail/firejail | Isolamento Linux nativo | Dependente de Linux específico |

## Recomendação inicial

Começar com **Go** para o runtime + **Linux namespaces/cgroups** para isolamento leve, sem Docker.

## Arquitetura proposta

```
Harness Python          gRPC/HTTP            Sandbox Go
   run_terminal  -------------------->   Inicia container leve
   (comando, timeout, recursos)          Executa comando
   <--------------------------------     Retorna stdout/stderr/exit
```

## Componentes

### 1. Servidor Go (`sandbox/main.go`)

- Recebe requisições do harness.
- Cria um processo filho isolado com:
  - `CLONE_NEWNS`, `CLONE_NEWPID`, `CLONE_NEWNET` (namespaces)
  - chroot temporário ou bind mounts read-only
  - limites via cgroups v2
- Executa o comando.
- Retorna stdout, stderr, exit code.

### 2. Cliente Python (`zeus/tools/sandbox_client.py`)

- Envia comando para o servidor Go.
- Recebe e formata resposta.
- Implementa timeout e retry.

### 3. Substituição gradual

- Fase 1: `run_terminal` continua local por padrão.
- Fase 2: adicionar `run_sandboxed` como nova ferramenta.
- Fase 3: permitir alternar todas as execuções para sandbox via config.

## Restrições da sandbox

- Sem acesso à rede por padrão (exceto se explicitamente permitido).
- Sem acesso ao filesystem do host (somente diretório de trabalho temporário).
- Limite de tempo de execução.
- Limite de memória e CPU.
- Sem variáveis de ambiente sensíveis do host.

## Próximos passos

1. Criar protótipo do servidor Go com execução isolada.
2. Definir protocolo de comunicação (gRPC ou HTTP+JSON).
3. Integrar cliente Python.
4. Testar com comandos destrutivos fictícios.
5. Avaliar se mantém Go ou migra para Rust.
