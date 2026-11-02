use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;

use chrono::Local;
use eframe::egui;

#[derive(Clone, Debug, PartialEq)]
enum MessageRole {
    User,
    Zeus,
    System,
    Error,
}

#[derive(Clone, Debug)]
struct ChatMessage {
    role: MessageRole,
    content: String,
    timestamp: String,
}

#[derive(Clone, Debug)]
struct Conversation {
    #[allow(dead_code)]
    id: usize,
    title: String,
    messages: Vec<ChatMessage>,
}

impl Conversation {
    fn total_tokens(&self) -> usize {
        let total_chars: usize = self.messages.iter().map(|m| m.content.chars().count()).sum();
        if total_chars == 0 {
            0
        } else {
            ((total_chars as f64) / 3.5).ceil() as usize
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum ZeusMode {
    Sandbox,
    Terminal,
    Auto,
    DryRun,
    ReadOnly,
}

impl ZeusMode {
    fn label(&self) -> &'static str {
        match self {
            Self::Sandbox => "🛡️ Sandbox",
            Self::Terminal => "⚡ Terminal",
            Self::Auto => "🚀 Auto",
            Self::DryRun => "👁️ Dry-Run",
            Self::ReadOnly => "🔍 Leitura",
        }
    }

    fn description(&self) -> &'static str {
        match self {
            Self::Sandbox => "Comandos isolados no sandbox",
            Self::Terminal => "Host com confirmação manual",
            Self::Auto => "Execução autônoma sem prompt",
            Self::DryRun => "Simulação sem alterar arquivos",
            Self::ReadOnly => "Apenas leitura, execuções bloqueadas",
        }
    }
}

enum WorkerEvent {
    ZeusOutput(String),
    ZeusError(String),
    Finished(bool),
}

struct ProjectItem {
    name: String,
    path: PathBuf,
}

struct ZeusApp {
    // Conversas (histórico mantido em até 5 conversas)
    conversations: Vec<Conversation>,
    active_conversation_idx: usize,
    next_conversation_id: usize,

    input_text: String,
    is_running: bool,
    status_text: String,

    // Provedor, Modelo, Contexto, Modo e Raciocínio
    current_provider: String,
    selected_model: String,
    #[allow(dead_code)]
    selected_context: String,
    selected_mode: ZeusMode,
    selected_reasoning: String,
    session_context: bool,

    // Projetos e diretório de execução
    current_dir: PathBuf,
    projects: Vec<ProjectItem>,

    // Comunicação com worker thread
    event_sender: Sender<WorkerEvent>,
    event_receiver: Receiver<WorkerEvent>,
    active_child: Arc<Mutex<Option<Child>>>,

    // Configurações e UI
    show_about: bool,
    show_settings: bool,
    show_add_project: bool,
    new_project_path: String,
    new_project_name: String,
    auto_scroll: bool,
}

impl ZeusApp {
    fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        let (tx, rx) = channel();

        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let home_path = PathBuf::from(home);

        let current_path = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        let default_name = if current_path.ends_with("desktop") {
            "Zeus Desktop".to_string()
        } else {
            current_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| "Zeus Desktop".to_string())
        };

        let mut projects = vec![
            ProjectItem {
                name: default_name,
                path: current_path.clone(),
            },
            ProjectItem {
                name: "Zeus (Core)".to_string(),
                path: home_path.join("Documentos/Dev/Zeus"),
            },
        ];

        // Manter apenas projetos existentes
        projects.retain(|p| p.path.exists());

        let initial_dir = projects
            .first()
            .map(|p| p.path.clone())
            .unwrap_or_else(|| current_path);

        let (provider, model) = Self::detect_provider_and_model(&initial_dir);

        let initial_conversation = Conversation {
            id: 1,
            title: "Nova Conversa".to_string(),
            messages: vec![ChatMessage {
                role: MessageRole::System,
                content: "⚡ Bem-vindo ao Zeus Desktop (Rust Native Edition)!\nSelecione um projeto na barra lateral e digite sua instrução.".to_string(),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
            }],
        };

        Self {
            conversations: vec![initial_conversation],
            active_conversation_idx: 0,
            next_conversation_id: 2,
            input_text: String::new(),
            is_running: false,
            status_text: "Pronto".to_string(),
            current_provider: provider,
            selected_model: model,
            selected_context: "Projeto Atual".to_string(),
            selected_mode: ZeusMode::Sandbox,
            selected_reasoning: "Medium".to_string(),
            session_context: true,
            current_dir: initial_dir,
            projects,
            event_sender: tx,
            event_receiver: rx,
            active_child: Arc::new(Mutex::new(None)),
            show_about: false,
            show_settings: false,
            show_add_project: false,
            new_project_path: String::new(),
            new_project_name: String::new(),
            auto_scroll: true,
        }
    }

    fn detect_provider_and_model(dir: &Path) -> (String, String) {
        let candidates = [
            dir.join(".env"),
            dir.join("../.env"),
            PathBuf::from(std::env::var("HOME").unwrap_or_default()).join("Documentos/Dev/Zeus/.env"),
            PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(".zeus/.env"),
        ];

        let mut provider = "opencode_go".to_string();
        let mut model = "deepseek-v4-pro".to_string();

        for path in &candidates {
            if path.exists() {
                if let Ok(content) = std::fs::read_to_string(path) {
                    for line in content.lines() {
                        let trimmed = line.trim();
                        if trimmed.starts_with("ZEUS_PROVIDER=") {
                            let val = trimmed.trim_start_matches("ZEUS_PROVIDER=").trim().trim_matches('"');
                            if !val.is_empty() {
                                provider = val.to_string();
                            }
                        } else if trimmed.starts_with("ZEUS_MODEL=") {
                            let val = trimmed.trim_start_matches("ZEUS_MODEL=").trim().trim_matches('"');
                            if !val.is_empty() {
                                model = val.to_string();
                            }
                        }
                    }
                    break;
                }
            }
        }

        (provider, model)
    }

    fn all_providers() -> &'static [(&'static str, &'static str)] {
        &[
            ("opencode_go", "OpenCode Go"),
            ("google_api", "Google Gemini"),
            ("openrouter", "OpenRouter"),
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic Claude"),
            ("deepseek", "DeepSeek"),
            ("mistral", "Mistral AI"),
            ("ollama", "Ollama (Local)"),
            ("groq", "Groq"),
            ("xai", "xAI (Grok)"),
            ("together", "Together AI"),
            ("fireworks", "Fireworks AI"),
            ("cohere", "Cohere"),
        ]
    }

    fn provider_display_name(provider: &str) -> &'static str {
        match provider {
            "opencode_go" | "opencode" => "OpenCode Go",
            "google_api" | "google_auth" | "google" => "Google Gemini",
            "openrouter" => "OpenRouter",
            "openai" => "OpenAI",
            "anthropic" => "Anthropic Claude",
            "deepseek" => "DeepSeek",
            "mistral" => "Mistral AI",
            "ollama" => "Ollama (Local)",
            "groq" => "Groq",
            "xai" => "xAI (Grok)",
            "together" => "Together AI",
            "fireworks" => "Fireworks AI",
            "cohere" => "Cohere",
            _ => "Provedor Atual",
        }
    }

    fn get_models_for_provider(provider: &str) -> Vec<(&'static str, &'static str)> {
        match provider {
            "opencode_go" | "opencode" => vec![
                ("deepseek-v4-pro", "DeepSeek V4 Pro (padrão)"),
                ("kimi-k2.7-code", "Kimi K2.5 Code"),
                ("deepseek-v4.1-flash-free", "DeepSeek V4.1 Flash (Free)"),
                ("glm-5.3-flash-free", "GLM 5.3 Flash (Free)"),
                ("mimo-v2.6-flash-free", "Mimo V2.6 Flash (Free)"),
                ("flint-40b-free", "Flint 40B (Free)"),
                ("nemotron-3-ultra-free", "Nemotron 3 Ultra (Free)"),
                ("nemotron-3.5-lightning-free", "Nemotron 3.5 Lightning (Free)"),
                ("nemotron-3.5-super-vl-free", "Nemotron 3.5 Super VL (Free)"),
                ("beam-free", "Beam (Free)"),
                ("big-pickle", "Big Pickle"),
                ("deepseek-chat", "DeepSeek Chat (V3)"),
                ("deepseek-reasoner", "DeepSeek Reasoner (R1)"),
                ("claude-3-5-sonnet", "Claude 3.5 Sonnet"),
                ("claude-3-7-sonnet", "Claude 3.7 Sonnet"),
                ("gpt-4o", "GPT-4o"),
                ("gpt-4o-mini", "GPT-4o Mini"),
                ("o3-mini", "OpenAI o3-mini"),
                ("qwen-2.5-coder", "Qwen 2.5 Coder"),
                ("glm-4", "GLM 4"),
                ("minimax-01", "MiniMax 01"),
            ],
            "openrouter" => vec![
                ("openrouter/auto", "Auto (escolha automática)"),
                ("anthropic/claude-sonnet-4", "Claude Sonnet 4"),
                ("openai/gpt-4o", "GPT-4o"),
                ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
                ("deepseek/deepseek-chat", "DeepSeek Chat"),
                ("mistralai/mistral-large", "Mistral Large"),
            ],
            "openai" => vec![
                ("gpt-4o", "GPT-4o"),
                ("gpt-4o-mini", "GPT-4o Mini"),
                ("o3-mini", "o3 Mini"),
            ],
            "anthropic" => vec![
                ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
                ("claude-opus-4-20250514", "Claude Opus 4"),
                ("claude-haiku-3-5-20241022", "Claude Haiku 3.5"),
            ],
            "google_api" | "google_auth" | "google" => vec![
                ("gemini-2.5-pro", "Gemini 2.5 Pro"),
                ("gemini-2.5-flash", "Gemini 2.5 Flash"),
                ("gemini-2.0-flash", "Gemini 2.0 Flash"),
                ("gemini-2.0-flash-thinking-exp", "Gemini 2.0 Flash Thinking"),
                ("gemini-1.5-pro", "Gemini 1.5 Pro"),
                ("gemini-1.5-flash", "Gemini 1.5 Flash"),
            ],
            "deepseek" => vec![
                ("deepseek-chat", "DeepSeek Chat"),
                ("deepseek-reasoner", "DeepSeek Reasoner"),
            ],
            "mistral" => vec![
                ("mistral-large-latest", "Mistral Large"),
                ("mistral-small-latest", "Mistral Small"),
            ],
            "ollama" => vec![
                ("llama3.1", "Llama 3.1"),
                ("qwen2.5-coder", "Qwen 2.5 Coder"),
                ("phi4", "Phi-4"),
            ],
            "groq" => vec![
                ("llama-3.3-70b-versatile", "Llama 3.3 70B"),
                ("openai/gpt-oss-120b", "GPT-OSS 120B"),
            ],
            _ => vec![
                ("deepseek-v4-pro", "DeepSeek V4 Pro"),
                ("kimi-k2.7-code", "Kimi K2.5 Code"),
                ("gpt-4o", "GPT-4o"),
                ("claude-sonnet-4", "Claude Sonnet 4"),
            ],
        }
    }

    fn new_conversation(&mut self) {
        // Manter no máximo as 5 últimas conversas
        if self.conversations.len() >= 5 {
            self.conversations.remove(0);
        }

        let id = self.next_conversation_id;
        self.next_conversation_id += 1;

        self.conversations.push(Conversation {
            id,
            title: "Nova Conversa".to_string(),
            messages: vec![ChatMessage {
                role: MessageRole::System,
                content: "Nova conversa iniciada.".to_string(),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
            }],
        });

        self.active_conversation_idx = self.conversations.len().saturating_sub(1);
        self.auto_scroll = true;
    }

    fn current_conversation_mut(&mut self) -> Option<&mut Conversation> {
        if self.conversations.is_empty() {
            return None;
        }
        if self.active_conversation_idx >= self.conversations.len() {
            self.active_conversation_idx = self.conversations.len() - 1;
        }
        self.conversations.get_mut(self.active_conversation_idx)
    }

    fn current_conversation(&self) -> Option<&Conversation> {
        if self.conversations.is_empty() {
            return None;
        }
        let idx = self.active_conversation_idx.min(self.conversations.len() - 1);
        self.conversations.get(idx)
    }

    fn pick_folder() -> Option<PathBuf> {
        let output = Command::new("zenity")
            .args(["--file-selection", "--directory", "--title=Selecionar Pasta do Projeto"])
            .output()
            .ok()?;
        if output.status.success() {
            let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path_str.is_empty() {
                let p = PathBuf::from(path_str);
                if p.exists() {
                    return Some(p);
                }
            }
        }
        None
    }

    fn add_project(&mut self, path: PathBuf) {
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "Projeto".to_string());

        if !self.projects.iter().any(|p| p.path == path) {
            self.projects.push(ProjectItem {
                name: name.clone(),
                path: path.clone(),
            });
        }

        self.current_dir = path.clone();
        let (prov, modl) = Self::detect_provider_and_model(&path);
        self.current_provider = prov;
        self.selected_model = modl;

        if let Some(convo) = self.current_conversation_mut() {
            convo.messages.push(ChatMessage {
                role: MessageRole::System,
                content: format!("Projeto adicionado e ativado: {} ({})", name, path.display()),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
            });
        }
    }

    fn send_message(&mut self) {
        let text = self.input_text.trim().to_string();
        if text.is_empty() || self.is_running {
            return;
        }

        let timestamp = Local::now().format("%H:%M:%S").to_string();

        if let Some(convo) = self.current_conversation_mut() {
            // Renomeia o título da conversa com o início da primeira mensagem do usuário
            if convo.title == "Nova Conversa" {
                let preview: String = text.chars().take(22).collect();
                let clean = preview.trim().replace('\n', " ");
                if !clean.is_empty() {
                    convo.title = format!("{}...", clean);
                }
            }

            convo.messages.push(ChatMessage {
                role: MessageRole::User,
                content: text.clone(),
                timestamp,
            });
        }

        self.input_text.clear();
        self.is_running = true;
        self.status_text = "Processando...".to_string();
        self.auto_scroll = true;

        let tx = self.event_sender.clone();
        let child_arc = Arc::clone(&self.active_child);
        let cwd = self.current_dir.clone();

        // Parâmetros selecionados
        let provider = self.current_provider.clone();
        let model = self.selected_model.clone();
        let reasoning = self.selected_reasoning.clone();
        let mode = self.selected_mode;
        let convo_id = self.conversations.get(self.active_conversation_idx).map(|c| c.id).unwrap_or(1);
        let session_context = self.session_context;

        thread::spawn(move || {
            let python_bin = Self::find_zeus_python(&cwd);
            let zeus_dir = Self::find_zeus_dir(&cwd);

            let mut cmd = Command::new(&python_bin);
            // Usando --no-color para saída limpa
            cmd.args(["-m", "zeus.cli", "--no-color", "-q", &text]);
            if session_context {
                cmd.args(["--session", &format!("convo_{}", convo_id)]);
            }
            cmd.current_dir(&cwd)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());

            // Provedor, modelo e esforço de raciocínio
            cmd.env("ZEUS_PROVIDER", &provider);
            cmd.env("ZEUS_MODEL", &model);
            cmd.env("ZEUS_REASONING_EFFORT", reasoning.to_lowercase());

            // Configuração exata do Modo do Zeus
            match mode {
                ZeusMode::Sandbox => {
                    cmd.env("ZEUS_EXECUTION_PERMISSION", "sandbox_only");
                    cmd.env("ZEUS_EXECUTION_MODE", "terminal");
                    cmd.env("ZEUS_DRY_RUN", "0");
                    cmd.env("ZEUS_READ_ONLY", "0");
                }
                ZeusMode::Terminal => {
                    cmd.env("ZEUS_EXECUTION_PERMISSION", "allow");
                    cmd.env("ZEUS_EXECUTION_MODE", "terminal");
                    cmd.env("ZEUS_DRY_RUN", "0");
                    cmd.env("ZEUS_READ_ONLY", "0");
                }
                ZeusMode::Auto => {
                    cmd.env("ZEUS_EXECUTION_PERMISSION", "allow");
                    cmd.env("ZEUS_EXECUTION_MODE", "auto");
                    cmd.env("ZEUS_DRY_RUN", "0");
                    cmd.env("ZEUS_READ_ONLY", "0");
                }
                ZeusMode::DryRun => {
                    cmd.env("ZEUS_EXECUTION_PERMISSION", "allow");
                    cmd.env("ZEUS_EXECUTION_MODE", "terminal");
                    cmd.env("ZEUS_DRY_RUN", "1");
                    cmd.env("ZEUS_READ_ONLY", "0");
                }
                ZeusMode::ReadOnly => {
                    cmd.env("ZEUS_EXECUTION_PERMISSION", "deny");
                    cmd.env("ZEUS_EXECUTION_MODE", "terminal");
                    cmd.env("ZEUS_DRY_RUN", "0");
                    cmd.env("ZEUS_READ_ONLY", "1");
                }
            }

            if let Some(dir) = zeus_dir {
                let current_pythonpath = std::env::var("PYTHONPATH").unwrap_or_default();
                let new_pythonpath = if current_pythonpath.is_empty() {
                    dir.to_string_lossy().to_string()
                } else {
                    format!("{}:{}", dir.to_string_lossy(), current_pythonpath)
                };
                cmd.env("PYTHONPATH", new_pythonpath);
            }

            match cmd.spawn() {
                Ok(mut child) => {
                    let stdout = child.stdout.take();
                    let stderr = child.stderr.take();

                    {
                        let mut lock = child_arc.lock().unwrap();
                        *lock = Some(child);
                    }

                    let tx_out = tx.clone();
                    let out_handle = thread::spawn(move || {
                        if let Some(out) = stdout {
                            let reader = BufReader::new(out);
                            for line in reader.lines().flatten() {
                                let _ = tx_out.send(WorkerEvent::ZeusOutput(line));
                            }
                        }
                    });

                    let tx_err = tx.clone();
                    let err_handle = thread::spawn(move || {
                        if let Some(err) = stderr {
                            let reader = BufReader::new(err);
                            for line in reader.lines().flatten() {
                                let _ = tx_err.send(WorkerEvent::ZeusError(line));
                            }
                        }
                    });

                    let _ = out_handle.join();
                    let _ = err_handle.join();

                    let success = {
                        let mut lock = child_arc.lock().unwrap();
                        if let Some(mut child) = lock.take() {
                            match child.wait() {
                                Ok(status) => status.success(),
                                Err(_) => false,
                            }
                        } else {
                            false
                        }
                    };

                    let _ = tx.send(WorkerEvent::Finished(success));
                }
                Err(e) => {
                    let _ = tx.send(WorkerEvent::ZeusError(format!(
                        "Falha ao executar o Zeus usando '{}': {}",
                        python_bin.display(),
                        e
                    )));
                    let _ = tx.send(WorkerEvent::Finished(false));
                }
            }
        });
    }

    fn cancel_execution(&mut self) {
        let mut killed = false;
        if let Ok(mut lock) = self.active_child.lock() {
            if let Some(mut child) = lock.take() {
                let _ = child.kill();
                killed = true;
            }
        }

        if killed {
            if let Some(convo) = self.current_conversation_mut() {
                convo.messages.push(ChatMessage {
                    role: MessageRole::System,
                    content: "⏹ Execução interrompida pelo usuário.".to_string(),
                    timestamp: Local::now().format("%H:%M:%S").to_string(),
                });
            }
        }

        self.is_running = false;
        self.status_text = "Cancelado".to_string();
    }

    fn find_zeus_python(cwd: &Path) -> PathBuf {
        if let Ok(path) = std::env::var("ZEUS_PYTHON") {
            let p = PathBuf::from(path);
            if p.exists() {
                return p;
            }
        }

        // Venv local do projeto atual
        let cwd_venv = cwd.join(".venv/bin/python3");
        if cwd_venv.exists() {
            return cwd_venv;
        }

        // Venv de Zeus no home
        if let Ok(home) = std::env::var("HOME") {
            let home_venv = PathBuf::from(home).join("Documentos/Dev/Zeus/.venv/bin/python3");
            if home_venv.exists() {
                return home_venv;
            }
        }

        // Diretório pai
        if let Some(parent) = cwd.parent() {
            let parent_venv = parent.join(".venv/bin/python3");
            if parent_venv.exists() {
                return parent_venv;
            }
        }

        PathBuf::from("python3")
    }

    fn find_zeus_dir(cwd: &Path) -> Option<PathBuf> {
        if let Ok(dir) = std::env::var("ZEUS_DIR") {
            let p = PathBuf::from(dir);
            if p.join("zeus/__init__.py").exists() {
                return Some(p);
            }
        }

        if cwd.join("zeus/__init__.py").exists() {
            return Some(cwd.to_path_buf());
        }

        if let Some(parent) = cwd.parent() {
            if parent.join("zeus/__init__.py").exists() {
                return Some(parent.to_path_buf());
            }
        }

        if let Ok(home) = std::env::var("HOME") {
            let default = PathBuf::from(home).join("Documentos/Dev/Zeus");
            if default.join("zeus/__init__.py").exists() {
                return Some(default);
            }
        }

        None
    }

    fn sanitize_terminal_output(line: &str) -> Option<String> {
        // 1. Remover sequências de escape ANSI com byte ESC (\x1b)
        let mut cleaned = String::with_capacity(line.len());
        let mut chars = line.chars().peekable();

        while let Some(c) = chars.next() {
            if c == '\x1b' {
                if chars.peek() == Some(&'[') {
                    chars.next();
                    for next in chars.by_ref() {
                        if next.is_ascii_alphabetic() {
                            break;
                        }
                    }
                    continue;
                }
            }
            cleaned.push(c);
        }

        // 2. Remover resíduos como "[1;33m" ou "[0m" caso o byte ESC não tenha sido transmitido
        let mut without_codes = String::with_capacity(cleaned.len());
        let mut s = cleaned.as_str();
        while let Some(open) = s.find('[') {
            without_codes.push_str(&s[..open]);
            let rest = &s[open + 1..];
            if let Some(close) = rest.find('m') {
                let inside = &rest[..close];
                if !inside.is_empty() && inside.chars().all(|ch| ch.is_ascii_digit() || ch == ';') {
                    s = &rest[close + 1..];
                    continue;
                }
            }
            without_codes.push('[');
            s = rest;
        }
        without_codes.push_str(s);

        let trimmed = without_codes.trim();

        // 3. Ignorar linhas de moldura/card da CLI do Zeus (bordas superior e inferior)
        if trimmed.starts_with("╭──") || trimmed.starts_with("╰──") || trimmed.chars().all(|c| c == '─') {
            return None;
        }

        // 4. Remover caractere de borda lateral "│"
        let final_text = if let Some(rest) = trimmed.strip_prefix('│') {
            rest.strip_prefix(' ').unwrap_or(rest).to_string()
        } else {
            trimmed.to_string()
        };

        if final_text.is_empty() {
            None
        } else {
            Some(final_text)
        }
    }

    fn process_worker_events(&mut self, ctx: &egui::Context) {
        while let Ok(event) = self.event_receiver.try_recv() {
            ctx.request_repaint();
            match event {
                WorkerEvent::ZeusOutput(line) => {
                    if let Some(cleaned) = Self::sanitize_terminal_output(&line) {
                        if let Some(convo) = self.current_conversation_mut() {
                            if let Some(last) = convo.messages.last_mut() {
                                if last.role == MessageRole::Zeus {
                                    // Evitar duplicar linhas idênticas de "⚡ Executando..."
                                    if cleaned == "⚡ Executando..."
                                        && (last.content.ends_with("⚡ Executando...")
                                            || last.content == "⚡ Executando...")
                                    {
                                        continue;
                                    }
                                    last.content.push('\n');
                                    last.content.push_str(&cleaned);
                                    continue;
                                }
                            }
                            convo.messages.push(ChatMessage {
                                role: MessageRole::Zeus,
                                content: cleaned,
                                timestamp: Local::now().format("%H:%M:%S").to_string(),
                            });
                        }
                    }
                }
                WorkerEvent::ZeusError(line) => {
                    if let Some(cleaned) = Self::sanitize_terminal_output(&line) {
                        if let Some(convo) = self.current_conversation_mut() {
                            convo.messages.push(ChatMessage {
                                role: MessageRole::Error,
                                content: cleaned,
                                timestamp: Local::now().format("%H:%M:%S").to_string(),
                            });
                        }
                    }
                }
                WorkerEvent::Finished(success) => {
                    self.is_running = false;
                    self.status_text = if success {
                        "Pronto".to_string()
                    } else {
                        "Concluído com avisos/erros".to_string()
                    };
                    self.auto_scroll = true;
                }
            }
        }
    }
}

impl eframe::App for ZeusApp {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.process_worker_events(&ctx);

        // Top Header
        egui::Panel::top("top_panel").show(ui, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                // Menu Hamburger antes do título
                ui.menu_button("☰", |ui| {
                    if ui.button("⚙️ Configurações").clicked() {
                        self.show_settings = true;
                        ui.close();
                    }
                    ui.separator();
                    if ui.button("ℹ️ Sobre").clicked() {
                        self.show_about = true;
                        ui.close();
                    }
                });

                ui.add_space(4.0);
                // Título limpo (sem versão)
                ui.heading("⚡ Zeus Desktop");

                // Direita: indicador de status e toggle de contexto da sessão
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let (status_color, icon) = if self.is_running {
                        (egui::Color32::from_rgb(243, 156, 18), "⏳")
                    } else {
                        (egui::Color32::from_rgb(46, 204, 113), "●")
                    };

                    // 1. Status (à extrema direita)
                    ui.label(
                        egui::RichText::new(format!("{} {}", icon, self.status_text))
                            .color(status_color)
                            .strong(),
                    );

                    ui.add_space(8.0);

                    // 2. Label mostrando a quantidade de tokens (a palavra "Contexto da Sessão" só aparece no hover)
                    let total_tokens = self.current_conversation().map(|c| c.total_tokens()).unwrap_or(0);
                    let tokens_formatted = if total_tokens >= 10_000 {
                        format!("{:.1}k tokens", total_tokens as f64 / 1000.0)
                    } else {
                        format!("{} tokens", total_tokens)
                    };

                    let tokens_label = egui::RichText::new(format!("🧠 {}", tokens_formatted))
                        .color(egui::Color32::from_rgb(140, 200, 255))
                        .strong()
                        .size(11.5);

                    ui.label(tokens_label).on_hover_text(format!(
                        "Contexto da Sessão: {} tokens acumulados nesta conversa.",
                        total_tokens
                    ));
                });
            });
            ui.add_space(4.0);
        });

        // Bottom Status Bar: apenas pasta atual e projeto em negrito
        egui::Panel::bottom("bottom_status_panel").show(ui, |ui| {
            ui.horizontal(|ui| {
                let project_name = self
                    .projects
                    .iter()
                    .find(|p| p.path == self.current_dir)
                    .map(|p| p.name.clone())
                    .unwrap_or_else(|| {
                        self.current_dir
                            .file_name()
                            .map(|n| n.to_string_lossy().to_string())
                            .unwrap_or_else(|| "Projeto".to_string())
                    });

                ui.label(egui::RichText::new("📂").size(11.0));
                ui.label(
                    egui::RichText::new("Projeto:")
                        .size(11.0)
                        .color(egui::Color32::from_rgb(160, 170, 180)),
                );
                ui.label(
                    egui::RichText::new(&project_name)
                        .strong()
                        .size(11.0)
                        .color(egui::Color32::WHITE),
                );
                ui.label(
                    egui::RichText::new(" • ")
                        .size(11.0)
                        .color(egui::Color32::from_rgb(100, 110, 120)),
                );
                ui.label(
                    egui::RichText::new("Pasta:")
                        .size(11.0)
                        .color(egui::Color32::from_rgb(160, 170, 180)),
                );
                ui.label(
                    egui::RichText::new(self.current_dir.display().to_string())
                        .strong()
                        .size(11.0)
                        .color(egui::Color32::from_rgb(200, 215, 230)),
                );
            });
        });

        // Left Sidebar: Projetos e Conversas
        egui::Panel::left("sidebar_panel")
            .resizable(true)
            .default_size(240.0)
            .min_size(180.0)
            .max_size(360.0)
            .show(ui, |ui| {
                ui.add_space(6.0);

                // Cabeçalho Projetos com botão "+" à direita
                ui.horizontal(|ui| {
                    ui.heading("Projetos");
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let add_btn = ui.button(egui::RichText::new("+").strong().size(16.0));
                        if add_btn.on_hover_text("Adicionar projeto").clicked() {
                            if let Some(folder) = Self::pick_folder() {
                                self.add_project(folder);
                            } else {
                                self.show_add_project = true;
                            }
                        }
                    });
                });
                ui.separator();

                let mut selected_project: Option<PathBuf> = None;
                for project in &self.projects {
                    let is_active = self.current_dir == project.path;
                    let text = if is_active {
                        format!("▶ {}", project.name)
                    } else {
                        format!("  {}", project.name)
                    };

                    let btn = ui.selectable_label(is_active, text);
                    if btn.clicked() {
                        selected_project = Some(project.path.clone());
                    }
                }

                if let Some(path) = selected_project {
                    self.current_dir = path.clone();
                    let (prov, modl) = Self::detect_provider_and_model(&path);
                    self.current_provider = prov;
                    self.selected_model = modl;

                    if let Some(convo) = self.current_conversation_mut() {
                        convo.messages.push(ChatMessage {
                            role: MessageRole::System,
                            content: format!("Projeto ativo: {}", path.display()),
                            timestamp: Local::now().format("%H:%M:%S").to_string(),
                        });
                    }
                }

                ui.add_space(16.0);
                ui.separator();
                ui.add_space(4.0);

                // Cabeçalho Conversas com botão "+" à direita
                ui.horizontal(|ui| {
                    ui.heading("Conversas");
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let add_btn = ui.button(egui::RichText::new("+").strong().size(16.0));
                        if add_btn.on_hover_text("Criar nova conversa").clicked() {
                            self.new_conversation();
                        }
                    });
                });
                ui.add_space(4.0);

                // Lista do histórico de conversas em ordem decrescente (mais recente no topo)
                egui::ScrollArea::vertical()
                    .id_salt("conversations_scroll")
                    .show(ui, |ui| {
                        for (idx, convo) in self.conversations.iter().enumerate().rev() {
                            let is_active = idx == self.active_conversation_idx;
                            let label = if is_active {
                                format!("💬 ▶ {}", convo.title)
                            } else {
                                format!("💬   {}", convo.title)
                            };

                            let btn = ui.selectable_label(is_active, label);
                            if btn.clicked() {
                                self.active_conversation_idx = idx;
                                self.auto_scroll = true;
                            }
                        }
                    });
            });

        // Central Area: Chat e Card da Conversa Ativa
        egui::CentralPanel::default().show(ui, |ui| {
            let available_height = ui.available_height();
            let bottom_bar_height = 92.0;
            let chat_height = (available_height - bottom_bar_height).max(80.0);

            // Mensagens da conversa atual
            egui::ScrollArea::vertical()
                .id_salt("messages_scroll")
                .max_height(chat_height)
                .stick_to_bottom(self.auto_scroll)
                .show(ui, |ui| {
                    if let Some(convo) = self.current_conversation() {
                        for msg in &convo.messages {
                            ui.add_space(6.0);
                            match msg.role {
                                MessageRole::User => {
                                    // Cinza escuro, um pouco mais claro que o background da tela
                                    let panel_bg = ui.visuals().panel_fill;
                                    let user_card_bg = egui::Color32::from_rgb(
                                        panel_bg.r().saturating_add(15),
                                        panel_bg.g().saturating_add(15),
                                        panel_bg.b().saturating_add(18),
                                    );

                                    egui::Frame::new()
                                        .fill(user_card_bg)
                                        .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(52, 54, 62)))
                                        .corner_radius(8u8)
                                        .inner_margin(10i8)
                                        .show(ui, |ui| {
                                            ui.horizontal(|ui| {
                                                ui.label(
                                                    egui::RichText::new("👤 Você")
                                                        .strong()
                                                        .color(egui::Color32::from_rgb(78, 204, 163)),
                                                );
                                                ui.label(
                                                    egui::RichText::new(&msg.timestamp)
                                                        .size(10.0)
                                                        .color(egui::Color32::from_rgb(140, 150, 160)),
                                                );
                                            });
                                            ui.add_space(3.0);
                                            ui.label(
                                                egui::RichText::new(&msg.content)
                                                    .strong()
                                                    .color(egui::Color32::from_rgb(235, 240, 245)),
                                            );
                                        });
                                }
                                MessageRole::Zeus => {
                                    egui::Frame::new()
                                        .fill(egui::Color32::BLACK)
                                        .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(45, 45, 55)))
                                        .corner_radius(8u8)
                                        .inner_margin(10i8)
                                        .show(ui, |ui| {
                                            ui.horizontal(|ui| {
                                                ui.label(
                                                    egui::RichText::new("⚡ Zeus")
                                                        .strong()
                                                        .color(egui::Color32::from_rgb(100, 180, 255)),
                                                );
                                                ui.label(
                                                    egui::RichText::new(&msg.timestamp)
                                                        .size(10.0)
                                                        .color(egui::Color32::GRAY),
                                                );
                                                ui.with_layout(
                                                    egui::Layout::right_to_left(egui::Align::Center),
                                                    |ui| {
                                                        if ui.small_button("📋 Copiar").clicked() {
                                                            ui.ctx().copy_text(msg.content.clone());
                                                        }
                                                    },
                                                );
                                            });
                                            ui.add_space(3.0);
                                            ui.label(
                                                egui::RichText::new(&msg.content)
                                                    .strong()
                                                    .color(egui::Color32::WHITE),
                                            );
                                        });
                                }
                                MessageRole::System => {
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(format!("ℹ️ {}", msg.content))
                                                .italics()
                                                .size(12.0)
                                                .color(egui::Color32::from_rgb(140, 160, 180)),
                                        );
                                    });
                                }
                                MessageRole::Error => {
                                    egui::Frame::new()
                                        .fill(egui::Color32::from_rgb(60, 25, 25))
                                        .corner_radius(8u8)
                                        .inner_margin(8i8)
                                        .show(ui, |ui| {
                                            ui.horizontal(|ui| {
                                                ui.label(
                                                    egui::RichText::new("❌ Erro")
                                                        .strong()
                                                        .color(egui::Color32::from_rgb(235, 87, 87)),
                                                );
                                                ui.label(
                                                    egui::RichText::new(&msg.timestamp)
                                                        .size(10.0)
                                                        .color(egui::Color32::GRAY),
                                                );
                                            });
                                            ui.add_space(2.0);
                                            ui.label(
                                                egui::RichText::new(&msg.content)
                                                    .color(egui::Color32::from_rgb(255, 120, 120)),
                                            );
                                        });
                                }
                            }
                        }
                    }
                });

            ui.separator();

            // Linha 1: Input de Mensagem e Botão Enviar / Parar
            ui.horizontal(|ui| {
                let input_response = ui.add_sized(
                    [ui.available_width() - 110.0, 36.0],
                    egui::TextEdit::singleline(&mut self.input_text)
                        .hint_text("Digite sua instrução para o Zeus e pressione Enter...")
                        .lock_focus(true),
                );

                if input_response.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                    self.send_message();
                }

                if self.is_running {
                    if ui
                        .add_sized([100.0, 36.0], egui::Button::new("⏹ Parar"))
                        .clicked()
                    {
                        self.cancel_execution();
                    }
                } else {
                    if ui
                        .add_sized([100.0, 36.0], egui::Button::new("Enviar"))
                        .clicked()
                    {
                        self.send_message();
                    }
                }
            });

            ui.add_space(6.0);

            // Linha 2: Barra inferior - Ordem: Modelo, Raciocínio (à esquerda) e Modo (à direita)
            // Cor do background para os botões não aparecerem e sem bordas
            ui.scope(|ui| {
                let bg = ui.visuals().panel_fill;
                let visuals = ui.visuals_mut();

                // Botões com a cor do background para não aparecerem (sem caixa) e sem bordas
                visuals.widgets.inactive.weak_bg_fill = bg;
                visuals.widgets.inactive.bg_fill = bg;
                visuals.widgets.inactive.bg_stroke = egui::Stroke::NONE;

                visuals.widgets.hovered.weak_bg_fill = bg;
                visuals.widgets.hovered.bg_fill = bg;
                visuals.widgets.hovered.bg_stroke = egui::Stroke::NONE;

                visuals.widgets.active.weak_bg_fill = bg;
                visuals.widgets.active.bg_fill = bg;
                visuals.widgets.active.bg_stroke = egui::Stroke::NONE;

                ui.horizontal(|ui| {
                    // 1. MODELO (à esquerda)
                    let model_label = egui::RichText::new(format!("{} ▾", self.selected_model))
                        .color(egui::Color32::from_rgb(210, 220, 235))
                        .size(12.0);
                    ui.menu_button(model_label, |ui| {
                        ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                        ui.set_min_width(320.0);
                        let provider_display = Self::provider_display_name(&self.current_provider);
                        ui.label(
                            egui::RichText::new(format!("🌐 Modelos {}", provider_display))
                                .strong()
                                .color(egui::Color32::from_rgb(100, 200, 255)),
                        );
                        ui.separator();

                        let available_models = Self::get_models_for_provider(&self.current_provider);
                        egui::ScrollArea::vertical()
                            .id_salt("models_menu_scroll")
                            .max_height(320.0)
                            .show(ui, |ui| {
                                for (mod_id, mod_label) in available_models {
                                    let is_sel = self.selected_model == mod_id;
                                    let item_text = format!("{} — {}", mod_id, mod_label);
                                    if ui.selectable_label(is_sel, item_text).clicked() {
                                        self.selected_model = mod_id.to_string();
                                        ui.close();
                                    }
                                }
                            });
                    });

                    ui.add_space(8.0);

                    // 2. RACIOCÍNIO (ao lado do modelo)
                    let reasoning_label = egui::RichText::new(format!("{} ▾", self.selected_reasoning))
                        .color(egui::Color32::from_rgb(210, 220, 235))
                        .size(12.0);
                    ui.menu_button(reasoning_label, |ui| {
                        ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                        ui.set_min_width(180.0);
                        ui.label(
                            egui::RichText::new("⚡ Esforço de Raciocínio")
                                .strong()
                                .color(egui::Color32::from_rgb(230, 190, 120)),
                        );
                        ui.separator();
                        for opt in ["Mínimo", "Medium", "Alto"] {
                            if ui.selectable_label(self.selected_reasoning == opt, opt).clicked() {
                                self.selected_reasoning = opt.to_string();
                                ui.close();
                            }
                        }
                    });

                    // 3. MODO (Último botão alinhado à direita)
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let mode_label = egui::RichText::new(format!("{} ▾", self.selected_mode.label()))
                            .color(egui::Color32::from_rgb(210, 220, 235))
                            .size(12.0);
                        ui.menu_button(mode_label, |ui| {
                            ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                            ui.set_min_width(320.0);
                            ui.label(
                                egui::RichText::new("🛡️ Modos do Zeus")
                                    .strong()
                                    .color(egui::Color32::from_rgb(255, 200, 100)),
                            );
                            ui.separator();

                            let all_modes = [
                                ZeusMode::Sandbox,
                                ZeusMode::Terminal,
                                ZeusMode::Auto,
                                ZeusMode::DryRun,
                                ZeusMode::ReadOnly,
                            ];

                            for m in all_modes {
                                let is_active = self.selected_mode == m;
                                ui.horizontal(|ui| {
                                    if ui.selectable_label(is_active, m.label()).clicked() {
                                        self.selected_mode = m;
                                        ui.close();
                                    }
                                    ui.label(
                                        egui::RichText::new(m.description())
                                            .size(11.0)
                                            .color(egui::Color32::from_rgb(160, 170, 180)),
                                    );
                                });
                            }
                        });
                    });
                });
            });
        });

        // Janela Configurações
        if self.show_settings {
            egui::Window::new("⚙️ Configurações")
                .collapsible(false)
                .resizable(true)
                .default_width(460.0)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .show(&ctx, |ui| {
                    ui.heading("Preferências do Zeus");
                    ui.add_space(8.0);

                    // Seção 1: Provedor e Modelo
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("🌐 Provedor de IA e Modelo").strong());
                        ui.add_space(4.0);

                        egui::Grid::new("settings_grid_provider")
                            .num_columns(2)
                            .spacing([12.0, 8.0])
                            .show(ui, |ui| {
                                ui.label("Provedor:");
                                egui::ComboBox::from_id_salt("settings_provider_combo")
                                    .selected_text(Self::provider_display_name(&self.current_provider))
                                    .width(260.0)
                                    .show_ui(ui, |ui| {
                                        for (p_id, p_name) in Self::all_providers() {
                                            if ui.selectable_label(self.current_provider == *p_id, *p_name).clicked() {
                                                self.current_provider = p_id.to_string();
                                                let models = Self::get_models_for_provider(p_id);
                                                if let Some((first_m, _)) = models.first() {
                                                    self.selected_model = first_m.to_string();
                                                }
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Modelo ativo:");
                                egui::ComboBox::from_id_salt("settings_model_combo")
                                    .selected_text(&self.selected_model)
                                    .width(260.0)
                                    .show_ui(ui, |ui| {
                                        let available_models = Self::get_models_for_provider(&self.current_provider);
                                        for (m_id, m_label) in available_models {
                                            let text = format!("{} ({})", m_id, m_label);
                                            if ui.selectable_label(self.selected_model == m_id, text).clicked() {
                                                self.selected_model = m_id.to_string();
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Modelo customizado:");
                                ui.text_edit_singleline(&mut self.selected_model);
                                ui.end_row();
                            });
                    });

                    ui.add_space(6.0);

                    // Seção 2: Modo e Raciocínio
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("🛡️ Execução e Raciocínio").strong());
                        ui.add_space(4.0);

                        egui::Grid::new("settings_grid_execution")
                            .num_columns(2)
                            .spacing([12.0, 8.0])
                            .show(ui, |ui| {
                                ui.label("Modo Padrão:");
                                egui::ComboBox::from_id_salt("settings_mode_combo")
                                    .selected_text(self.selected_mode.label())
                                    .width(260.0)
                                    .show_ui(ui, |ui| {
                                        let all_modes = [
                                            ZeusMode::Sandbox,
                                            ZeusMode::Terminal,
                                            ZeusMode::Auto,
                                            ZeusMode::DryRun,
                                            ZeusMode::ReadOnly,
                                        ];
                                        for m in all_modes {
                                            if ui.selectable_label(self.selected_mode == m, m.label()).clicked() {
                                                self.selected_mode = m;
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Raciocínio:");
                                egui::ComboBox::from_id_salt("settings_reasoning_combo")
                                    .selected_text(&self.selected_reasoning)
                                    .width(260.0)
                                    .show_ui(ui, |ui| {
                                        for opt in ["Mínimo", "Medium", "Alto"] {
                                            if ui.selectable_label(self.selected_reasoning == opt, opt).clicked() {
                                                self.selected_reasoning = opt.to_string();
                                            }
                                        }
                                    });
                                ui.end_row();
                            });
                    });

                    ui.add_space(6.0);

                    // Seção 3: Comportamento da Sessão
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("⚡ Comportamento").strong());
                        ui.add_space(4.0);
                        ui.checkbox(&mut self.session_context, "Manter histórico de contexto entre comandos na sessão");
                        ui.checkbox(&mut self.auto_scroll, "Rolar automaticamente para novas mensagens");
                    });

                    ui.add_space(6.0);

                    // Seção 4: Ambiente
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("📂 Ambiente").strong());
                        ui.add_space(4.0);
                        ui.label(
                            egui::RichText::new(format!("Pasta atual: {}", self.current_dir.display()))
                                .size(11.0)
                                .color(egui::Color32::from_rgb(180, 190, 205)),
                        );
                    });

                    ui.add_space(10.0);
                    ui.horizontal(|ui| {
                        if ui.button("OK / Concluir").clicked() {
                            self.show_settings = false;
                        }
                    });
                });
        }

        // Janela Sobre
        if self.show_about {
            egui::Window::new("Sobre o Zeus Desktop")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .show(&ctx, |ui| {
                    ui.heading("⚡ Zeus Desktop");
                    ui.label("Interface nativa desenvolvida em Rust com egui/eframe.");
                    ui.add_space(6.0);
                    ui.label("Autor: Valdeir Pereira da Silva");
                    ui.label("Versão: 0.1.0");
                    ui.add_space(10.0);
                    if ui.button("Fechar").clicked() {
                        self.show_about = false;
                    }
                });
        }

        // Janela Adicionar Projeto
        if self.show_add_project {
            egui::Window::new("Adicionar Projeto")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .show(&ctx, |ui| {
                    ui.label("Caminho da pasta do projeto:");
                    ui.horizontal(|ui| {
                        ui.text_edit_singleline(&mut self.new_project_path);
                        if ui.button("📂 Procurar...").clicked() {
                            if let Some(p) = Self::pick_folder() {
                                self.new_project_path = p.display().to_string();
                                if self.new_project_name.is_empty() {
                                    if let Some(n) = p.file_name() {
                                        self.new_project_name = n.to_string_lossy().to_string();
                                    }
                                }
                            }
                        }
                    });

                    ui.add_space(4.0);
                    ui.label("Nome do projeto (opcional):");
                    ui.text_edit_singleline(&mut self.new_project_name);

                    ui.add_space(8.0);
                    ui.horizontal(|ui| {
                        if ui.button("Adicionar").clicked() {
                            let path_buf = PathBuf::from(&self.new_project_path);
                            if path_buf.exists() {
                                let mut name = self.new_project_name.trim().to_string();
                                if name.is_empty() {
                                    name = path_buf
                                        .file_name()
                                        .map(|n| n.to_string_lossy().to_string())
                                        .unwrap_or_else(|| "Projeto".to_string());
                                }
                                self.add_project(path_buf);
                                if let Some(p) = self.projects.iter_mut().find(|p| p.path == self.current_dir) {
                                    p.name = name;
                                }

                                self.new_project_path.clear();
                                self.new_project_name.clear();
                                self.show_add_project = false;
                            }
                        }
                        if ui.button("Cancelar").clicked() {
                            self.new_project_path.clear();
                            self.new_project_name.clear();
                            self.show_add_project = false;
                        }
                    });
                });
        }
    }
}

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([960.0, 640.0])
            .with_min_inner_size([640.0, 480.0])
            .with_title("Zeus Desktop"),
        ..Default::default()
    };

    eframe::run_native(
        "Zeus Desktop",
        native_options,
        Box::new(|cc| Ok(Box::new(ZeusApp::new(cc)))),
    )
}
