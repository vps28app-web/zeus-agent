use crate::state::ToolInfo;

pub fn get_all_tools() -> &'static [ToolInfo] {
    const TOOLS: &[ToolInfo] = &[
        // Arquivos e Diretórios
        ToolInfo::new("read_file", "Lê o conteúdo e linhas de um arquivo de texto.", "Arquivos & Diretórios"),
        ToolInfo::new("write_file", "Cria ou sobrescreve arquivo em disco (cria pastas pais).", "Arquivos & Diretórios"),
        ToolInfo::new("replace_file_content", "Substitui trecho específico de arquivo com diff seguro.", "Arquivos & Diretórios"),
        ToolInfo::new("move_file", "Move ou renomeia arquivo ou diretório.", "Arquivos & Diretórios"),
        ToolInfo::new("copy_file", "Copia arquivo ou árvore inteira de diretórios.", "Arquivos & Diretórios"),
        ToolInfo::new("delete_file", "Remove um arquivo de forma definitiva.", "Arquivos & Diretórios"),
        ToolInfo::new("list_directory", "Lista arquivos e subpastas de um caminho.", "Arquivos & Diretórios"),
        ToolInfo::new("grep_search", "Busca regex em alta velocidade pelos arquivos do projeto.", "Arquivos & Diretórios"),
        ToolInfo::new("search_files", "Busca padrões e regex no conteúdo de arquivos.", "Arquivos & Diretórios"),

        // Terminal e Execução
        ToolInfo::new("run_terminal", "Executa comando shell diretamente no host local.", "Terminal & Execução"),
        ToolInfo::new("run_sandboxed", "Executa comando shell dentro de sandbox isolada segura.", "Terminal & Execução"),
        ToolInfo::new("run_background_command", "Inicia processo assíncrono em segundo plano (ex: servidores).", "Terminal & Execução"),
        ToolInfo::new("command_status", "Obtém status e saída stdout/stderr de comando em background.", "Terminal & Execução"),
        ToolInfo::new("terminate_command", "Encerra um processo em segundo plano pelo ID.", "Terminal & Execução"),
        ToolInfo::new("execute_python", "Executa código Python isolado dentro da sandbox.", "Terminal & Execução"),
        ToolInfo::new("execute_shell_script", "Executa script shell isolado na sandbox.", "Terminal & Execução"),

        // Git e Versionamento
        ToolInfo::new("git_status", "Exibe o status do repositório Git e arquivos modificados.", "Git & Versionamento"),
        ToolInfo::new("git_log", "Exibe histórico de commits do repositório.", "Git & Versionamento"),
        ToolInfo::new("git_diff", "Exibe diff das alterações em relação a HEAD.", "Git & Versionamento"),
        ToolInfo::new("git_branch", "Lista e gerencia branches locais e remotas.", "Git & Versionamento"),
        ToolInfo::new("git_checkout", "Alterna branch ou restaura arquivos no Git.", "Git & Versionamento"),
        ToolInfo::new("git_commit", "Cria commit das alterações preparadas com mensagem.", "Git & Versionamento"),
        ToolInfo::new("git_push", "Envia commits locais para o repositório remoto.", "Git & Versionamento"),
        ToolInfo::new("git_pull", "Baixa e integra alterações do repositório remoto.", "Git & Versionamento"),
        ToolInfo::new("git_clone", "Clona um repositório Git remoto para o disco.", "Git & Versionamento"),

        // Web e Navegação
        ToolInfo::new("web_search", "Pesquisa informações em tempo real na web (DuckDuckGo/Tavily/Serper).", "Web & Navegação"),
        ToolInfo::new("web_extract", "Extrai e converte conteúdo de URL em Markdown limpo para LLM.", "Web & Navegação"),
        ToolInfo::new("web_scrape_links", "Extrai todos os links e textos de uma página web.", "Web & Navegação"),
        ToolInfo::new("browser_navigate", "Navega para URL em Chrome headless (Playwright/Puppeteer).", "Web & Navegação"),
        ToolInfo::new("browser_extract", "Extrai elementos HTML ou texto de página no navegador.", "Web & Navegação"),
        ToolInfo::new("browser_click", "Clica em botões e elementos de página web interativa.", "Web & Navegação"),
        ToolInfo::new("browser_evaluate", "Executa código JavaScript na página aberta no navegador.", "Web & Navegação"),

        // Memória e Perfil
        ToolInfo::new("remember", "Salva notas e fatos na memória persistente SQLite.", "Memória & Perfil"),
        ToolInfo::new("recall", "Recupera anotações gravadas na memória por chave.", "Memória & Perfil"),
        ToolInfo::new("search_memory", "Busca em notas salvas na memória por palavra-chave.", "Memória & Perfil"),
        ToolInfo::new("list_memories", "Lista todas as chaves e contagens de notas persistidas.", "Memória & Perfil"),
        ToolInfo::new("forget_memory", "Remove notas associadas a uma chave de memória.", "Memória & Perfil"),
        ToolInfo::new("remember_user", "Salva preferências, fatos e hábitos do usuário.", "Memória & Perfil"),
        ToolInfo::new("recall_user", "Recupera perfil personalizado do usuário.", "Memória & Perfil"),

        // Aprendizado Contínuo
        ToolInfo::new("reflect_on_resolution", "Salva padrão de problema/solução aprendido para o futuro.", "Aprendizado Contínuo"),
        ToolInfo::new("search_past_learnings", "Busca aprendizados passados relevantes para a tarefa.", "Aprendizado Contínuo"),
        ToolInfo::new("rate_learning", "Avalia utilidade de aprendizado (ajusta pontuação de relevância).", "Aprendizado Contínuo"),
        ToolInfo::new("list_recent_learnings", "Lista os aprendizados mais recentes gravados.", "Aprendizado Contínuo"),

        // Configuração & Sistema
        ToolInfo::new("get_zeus_config", "Retorna configuração atual, chaves de API e status do Zeus.", "Configuração & Sistema"),
        ToolInfo::new("update_zeus_config", "Atualiza chave de API ou variável de configuração no .env.", "Configuração & Sistema"),
        ToolInfo::new("list_available_models", "Lista provedores e modelos LLM disponíveis.", "Configuração & Sistema"),
        ToolInfo::new("query_database", "Executa consultas SELECT somente leitura no banco SQLite zeus.db.", "Configuração & Sistema"),
        ToolInfo::new("manage_packages", "Gerencia pacotes de sistema e Python (apt/flatpak/pip).", "Configuração & Sistema"),
        ToolInfo::new("change_working_directory", "Altera diretório ativo e fronteira de arquivos da sessão.", "Configuração & Sistema"),

        // Agendador (Scheduler)
        ToolInfo::new("schedule_task", "Agenda tarefa recorrente via expressão cron no SQLite.", "Agendador (Scheduler)"),
        ToolInfo::new("list_scheduled", "Lista tarefas cron agendadas e próximas execuções.", "Agendador (Scheduler)"),
        ToolInfo::new("cancel_task", "Cancela e remove uma tarefa agendada pelo ID.", "Agendador (Scheduler)"),
    ];
    TOOLS
}
