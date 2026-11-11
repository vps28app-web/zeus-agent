use crate::state::CommandInfo;

pub fn get_all_commands() -> &'static [CommandInfo] {
    const COMMANDS: &[CommandInfo] = &[
        // Sessão & Sistema
        CommandInfo::new("/new", "Cria uma nova sessão de conversa com novo ID.", "Sessão & Sistema"),
        CommandInfo::new("/reset", "Reseta a sessão atual mantendo o ID e zera métricas.", "Sessão & Sistema"),
        CommandInfo::new("/clear", "Limpa as mensagens visíveis da tela.", "Sessão & Sistema"),
        CommandInfo::new("/summary", "Mostra resumo da sessão e consumo de tokens/custo.", "Sessão & Sistema"),
        CommandInfo::new("/help", "Exibe menu de ajuda com a lista de comandos do Zeus.", "Sessão & Sistema"),
        CommandInfo::new("/exit", "Encerra o Zeus.", "Sessão & Sistema"),

        // Configuração & Modelos
        CommandInfo::new("/config", "Gerencia configurações do Zeus (get/set/list).", "Configuração & IA"),
        CommandInfo::new("/models", "Lista ou altera o provedor e modelo de IA ativo.", "Configuração & IA"),
        CommandInfo::new("/auth", "Autentica Google Gemini via navegador (google_auth).", "Configuração & IA"),
        CommandInfo::new("/skills", "Seleciona skill set ou persona para filtrar ferramentas.", "Configuração & IA"),

        // Segurança & Modos
        CommandInfo::new("/mode <sandbox|terminal|auto|dryrun|readonly>", "Alterna modo de execução de código e segurança.", "Segurança & Modos"),
        CommandInfo::new("/mode file <read_only|project_only|unrestricted>", "Define a fronteira de permissão de escrita/leitura em disco.", "Segurança & Modos"),
        CommandInfo::new("/mode status", "Exibe modo atual e status de segurança do agente.", "Segurança & Modos"),

        // Planejamento & Multi-Agente
        CommandInfo::new("/plan <tarefa>", "Cria e executa um plano estruturado passo a passo.", "Planejamento & Equipe"),
        CommandInfo::new("/plan bmad <ideia>", "Análise BMAD de modelo de negócio para uma ideia.", "Planejamento & Equipe"),
        CommandInfo::new("/team <tarefa>", "Executa uma tarefa delegando para equipe multi-agente.", "Planejamento & Equipe"),

        // Memória & Aprendizado
        CommandInfo::new("/learn", "Gerencia aprendizados persistentes (list/search/add/stats/forget).", "Memória & Aprendizado"),
        CommandInfo::new("/brain", "Dashboard de inteligência e aprendizado contínuo.", "Memória & Aprendizado"),
        CommandInfo::new("/mcp", "Gerencia servidores Model Context Protocol (list/add/remove/reload).", "Protocolo MCP"),
    ];
    COMMANDS
}
