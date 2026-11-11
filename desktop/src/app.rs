use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use chrono::Local;
use eframe::egui;

use crate::config::DesktopConfig;
use crate::data::providers::detect_provider_and_model;
use crate::process::{
    fetch_desktop_catalog, kill_active_process, sanitize_terminal_output, send_permission_response,
    spawn_zeus_command, SpawnConfig,
};
use crate::state::{
    normalize_reasoning_label, CatalogData, ChatMessage, Conversation, McpServerConfigEntry,
    MessageRole, PermissionPrompt, ProjectItem, ToolExecution, WorkerEvent, ZeusMode,
};
use crate::ui;

pub struct ZeusApp {
    // Conversas
    pub conversations: Vec<Conversation>,
    pub active_conversation_idx: usize,
    pub next_conversation_id: usize,
    pub filter_convos_by_project: bool,
    pub convo_search_query: String,
    pub renaming_convo_idx: Option<usize>,
    pub rename_convo_buf: String,

    // Entrada de texto, anexos e histórico de comandos
    pub input_text: String,
    pub prompt_history: Vec<String>,
    pub history_idx: Option<usize>,
    pub temp_input: String,
    pub attached_files: Vec<PathBuf>,

    pub is_running: bool,
    pub status_text: String,
    pub toast_message: Option<(String, Instant)>,

    // Provedor, Modelo, Modo e Raciocínio
    pub current_provider: String,
    pub selected_model: String,
    pub selected_mode: ZeusMode,
    pub selected_reasoning: String,
    pub session_context: bool,
    pub auto_scroll: bool,
    pub custom_python_path: Option<String>,
    pub export_dir: Option<PathBuf>,

    // Projetos e diretório de execução
    pub current_dir: PathBuf,
    pub projects: Vec<ProjectItem>,

    // Comunicação com worker thread
    pub event_sender: Sender<WorkerEvent>,
    pub event_receiver: Receiver<WorkerEvent>,
    pub active_child: Arc<Mutex<Option<Child>>>,
    pub active_stdin: Arc<Mutex<Option<ChildStdin>>>,
    pub pending_permission: Option<PermissionPrompt>,
    pub catalog: Option<CatalogData>,

    // Persistência com debounce
    pub dirty_state: bool,
    pub last_save_at: Instant,

    // Modais e filtros de UI
    pub show_about: bool,
    pub show_settings: bool,
    pub show_commands: bool,
    pub show_tools: bool,
    pub show_mcp: bool,
    pub show_ecosystem: bool,
    pub ecosystem_tab: usize,
    pub ecosystem_filter: String,
    pub commands_filter: String,
    pub tools_filter: String,
    pub show_add_project: bool,
    pub new_project_path: String,
    pub new_project_name: String,

    // Gestão de .env / API Keys
    pub env_entries: Vec<(String, String)>,
    pub env_loaded: bool,
    pub show_env_secrets: bool,
    pub new_env_key: String,
    pub new_env_val: String,

    // Gestão de MCP
    pub mcp_new_name: String,
    pub mcp_new_cmd_or_url: String,
    pub mcp_new_args: String,
}

impl ZeusApp {
    pub fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        let (tx, rx) = channel();

        let saved_config = DesktopConfig::load();
        let config = saved_config.unwrap_or_default();

        let mut conversations = config.conversations;
        if conversations.is_empty() {
            let mut convo = Conversation::new(1, "Nova Conversa".to_string());
            convo.project_path = Some(config.current_dir.clone());
            convo.messages.push(ChatMessage {
                role: MessageRole::System,
                content: "⚡ Bem-vindo ao Zeus Desktop (Rust Native Edition)!\nSelecione um projeto na barra lateral e digite sua instrução.".to_string(),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
                tool_calls: Vec::new(),
            });
            conversations.push(convo);
        }

        let next_id = conversations.iter().map(|c| c.id).max().unwrap_or(0) + 1;
        let active_idx = config
            .active_conversation_idx
            .min(conversations.len().saturating_sub(1));

        let (detected_prov, detected_modl) = detect_provider_and_model(&config.current_dir);
        let provider = if config.current_provider.is_empty() {
            detected_prov
        } else {
            config.current_provider
        };
        let model = if config.selected_model.is_empty() {
            detected_modl
        } else {
            config.selected_model
        };

        let app = Self {
            conversations,
            active_conversation_idx: active_idx,
            next_conversation_id: next_id,
            filter_convos_by_project: config.filter_convos_by_project,
            convo_search_query: String::new(),
            renaming_convo_idx: None,
            rename_convo_buf: String::new(),
            input_text: String::new(),
            prompt_history: Vec::new(),
            history_idx: None,
            temp_input: String::new(),
            attached_files: Vec::new(),
            is_running: false,
            status_text: "Pronto".to_string(),
            toast_message: None,
            current_provider: provider,
            selected_model: model,
            selected_mode: config.selected_mode,
            selected_reasoning: normalize_reasoning_label(&config.selected_reasoning),
            session_context: config.session_context,
            auto_scroll: config.auto_scroll,
            custom_python_path: config.custom_python_path,
            export_dir: config.export_dir,
            current_dir: config.current_dir.clone(),
            projects: config.projects,
            event_sender: tx.clone(),
            event_receiver: rx,
            active_child: Arc::new(Mutex::new(None)),
            active_stdin: Arc::new(Mutex::new(None)),
            pending_permission: None,
            catalog: None,
            dirty_state: false,
            last_save_at: Instant::now(),
            show_about: false,
            show_settings: false,
            show_commands: false,
            show_tools: false,
            show_mcp: false,
            show_ecosystem: false,
            ecosystem_tab: 0,
            ecosystem_filter: String::new(),
            commands_filter: String::new(),
            tools_filter: String::new(),
            show_add_project: false,
            new_project_path: String::new(),
            new_project_name: String::new(),
            env_entries: Vec::new(),
            env_loaded: false,
            show_env_secrets: false,
            new_env_key: String::new(),
            new_env_val: String::new(),
            mcp_new_name: String::new(),
            mcp_new_cmd_or_url: String::new(),
            mcp_new_args: String::new(),
        };

        fetch_desktop_catalog(app.current_dir.clone(), app.custom_python_path.clone(), tx);
        app
    }

    pub fn refresh_catalog(&self) {
        fetch_desktop_catalog(
            self.current_dir.clone(),
            self.custom_python_path.clone(),
            self.event_sender.clone(),
        );
    }

    pub fn show_toast(&mut self, msg: impl Into<String>) {
        self.toast_message = Some((msg.into(), Instant::now()));
    }

    pub fn active_toast(&self) -> Option<&str> {
        if let Some((ref msg, at)) = self.toast_message {
            if at.elapsed() < Duration::from_secs(5) {
                return Some(msg.as_str());
            }
        }
        None
    }

    pub fn mark_dirty(&mut self) {
        self.dirty_state = true;
    }

    pub fn flush_state_if_needed(&mut self) {
        if self.dirty_state && self.last_save_at.elapsed() >= Duration::from_millis(1500) {
            self.save_state_now();
        }
    }

    pub fn save_state(&mut self) {
        self.save_state_now();
    }

    pub fn save_state_now(&mut self) {
        let config = DesktopConfig {
            current_dir: self.current_dir.clone(),
            projects: self.projects.clone(),
            current_provider: self.current_provider.clone(),
            selected_model: self.selected_model.clone(),
            selected_mode: self.selected_mode,
            selected_reasoning: self.selected_reasoning.clone(),
            session_context: self.session_context,
            auto_scroll: self.auto_scroll,
            custom_python_path: self.custom_python_path.clone(),
            conversations: self.conversations.clone(),
            active_conversation_idx: self.active_conversation_idx,
            filter_convos_by_project: self.filter_convos_by_project,
            export_dir: self.export_dir.clone(),
        };
        let _ = config.save();
        self.dirty_state = false;
        self.last_save_at = Instant::now();
    }

    pub fn new_conversation(&mut self) {
        let id = self.next_conversation_id;
        self.next_conversation_id += 1;

        let mut convo = Conversation::new(id, "Nova Conversa".to_string());
        convo.project_path = Some(self.current_dir.clone());
        convo.messages.push(ChatMessage {
            role: MessageRole::System,
            content: "Nova conversa iniciada.".to_string(),
            timestamp: Local::now().format("%H:%M:%S").to_string(),
            tool_calls: Vec::new(),
        });

        self.conversations.push(convo);
        self.active_conversation_idx = self.conversations.len().saturating_sub(1);
        self.save_state_now();
    }

    pub fn delete_conversation(&mut self, idx: usize) {
        if idx >= self.conversations.len() {
            return;
        }

        self.conversations.remove(idx);
        if self.renaming_convo_idx == Some(idx) {
            self.renaming_convo_idx = None;
        }
        if self.conversations.is_empty() {
            self.new_conversation();
        } else if self.active_conversation_idx >= self.conversations.len() {
            self.active_conversation_idx = self.conversations.len() - 1;
        }
        self.save_state_now();
    }

    pub fn export_active_conversation(&mut self) {
        if let Some(convo) = self.current_conversation() {
            let markdown = convo.export_markdown();
            let filename = format!("zeus_conversation_{}.md", convo.id);
            let target_dir = self
                .export_dir
                .clone()
                .unwrap_or_else(DesktopConfig::default_export_dir);
            if fs::create_dir_all(&target_dir).is_ok() {
                let path = target_dir.join(&filename);
                if fs::write(&path, markdown).is_ok() {
                    self.show_toast(format!("Exportado para: {}", path.display()));
                } else {
                    self.show_toast("Falha ao gravar arquivo Markdown.");
                }
            }
        }
    }

    pub fn current_conversation_mut(&mut self) -> Option<&mut Conversation> {
        if self.conversations.is_empty() {
            return None;
        }
        if self.active_conversation_idx >= self.conversations.len() {
            self.active_conversation_idx = self.conversations.len() - 1;
        }
        self.conversations.get_mut(self.active_conversation_idx)
    }

    pub fn current_conversation(&self) -> Option<&Conversation> {
        if self.conversations.is_empty() {
            return None;
        }
        let idx = self.active_conversation_idx.min(self.conversations.len() - 1);
        self.conversations.get(idx)
    }

    pub fn pick_folder() -> Option<PathBuf> {
        // Tenta zenity, depois kdialog, depois yad
        if let Ok(output) = Command::new("zenity")
            .args(["--file-selection", "--directory", "--title=Selecionar Pasta do Projeto"])
            .output()
        {
            if output.status.success() {
                let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let p = PathBuf::from(&path_str);
                if !path_str.is_empty() && p.exists() {
                    return Some(p);
                }
            }
        }
        if let Ok(output) = Command::new("kdialog")
            .args(["--getexistingdirectory", "."])
            .output()
        {
            if output.status.success() {
                let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let p = PathBuf::from(&path_str);
                if !path_str.is_empty() && p.exists() {
                    return Some(p);
                }
            }
        }
        if let Ok(output) = Command::new("yad")
            .args(["--file", "--directory", "--title=Selecionar Pasta do Projeto"])
            .output()
        {
            if output.status.success() {
                let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let p = PathBuf::from(&path_str);
                if !path_str.is_empty() && p.exists() {
                    return Some(p);
                }
            }
        }
        None
    }

    pub fn pick_files(initial_dir: &Path) -> Vec<PathBuf> {
        if let Ok(output) = Command::new("zenity")
            .args([
                "--file-selection",
                "--multiple",
                "--separator=\n",
                "--title=Anexar Arquivos ao Prompt",
            ])
            .current_dir(initial_dir)
            .output()
        {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .map(|l| PathBuf::from(l.trim()))
                    .filter(|p| p.exists())
                    .collect();
            }
        }
        if let Ok(output) = Command::new("kdialog")
            .args(["--getopenfilename", ".", "--multiple", "--separate-output"])
            .current_dir(initial_dir)
            .output()
        {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .map(|l| PathBuf::from(l.trim()))
                    .filter(|p| p.exists())
                    .collect();
            }
        }
        Vec::new()
    }

    pub fn add_project(&mut self, path: PathBuf) {
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
        let (prov, modl) = detect_provider_and_model(&path);
        self.current_provider = prov;
        self.selected_model = modl;
        self.save_state_now();
        self.refresh_catalog();

        if let Some(convo) = self.current_conversation_mut() {
            convo.messages.push(ChatMessage {
                role: MessageRole::System,
                content: format!("Projeto adicionado e ativado: {} ({})", name, path.display()),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
                tool_calls: Vec::new(),
            });
        }
    }

    pub fn navigate_history_up(&mut self) {
        if self.prompt_history.is_empty() {
            return;
        }

        match self.history_idx {
            None => {
                self.temp_input = self.input_text.clone();
                let last_idx = self.prompt_history.len() - 1;
                self.history_idx = Some(last_idx);
                self.input_text = self.prompt_history[last_idx].clone();
            }
            Some(idx) if idx > 0 => {
                let next_idx = idx - 1;
                self.history_idx = Some(next_idx);
                self.input_text = self.prompt_history[next_idx].clone();
            }
            _ => {}
        }
    }

    pub fn navigate_history_down(&mut self) {
        if let Some(idx) = self.history_idx {
            if idx + 1 < self.prompt_history.len() {
                let next_idx = idx + 1;
                self.history_idx = Some(next_idx);
                self.input_text = self.prompt_history[next_idx].clone();
            } else {
                self.history_idx = None;
                self.input_text = self.temp_input.clone();
            }
        }
    }

    pub fn edit_last_user_message(&mut self) {
        if self.is_running {
            return;
        }
        if let Some(convo) = self.current_conversation_mut() {
            if let Some(pos) = convo
                .messages
                .iter()
                .rposition(|m| m.role == MessageRole::User)
            {
                let msg = convo.messages.remove(pos);
                convo.messages.truncate(pos);
                self.input_text = msg.content;
                self.save_state_now();
            }
        }
    }

    pub fn send_permission_decision(&mut self, decision: &str, secret: Option<String>) {
        if let Some(prompt) = self.pending_permission.take() {
            send_permission_response(&self.active_stdin, &prompt.id, decision, secret.as_deref());
            self.status_text = if decision == "deny" {
                "Permissão negada".to_string()
            } else {
                "Processando...".to_string()
            };
        }
    }

    pub fn send_raw_command(&mut self, command_text: String) {
        if self.is_running {
            return;
        }
        self.input_text = command_text;
        self.send_message();
    }

    pub fn send_message(&mut self) {
        let raw_text = self.input_text.trim().to_string();
        if raw_text.is_empty() || self.is_running {
            return;
        }

        // Comando local /clear limpa mensagens na tela imediatamente
        if raw_text == "/clear" {
            if let Some(convo) = self.current_conversation_mut() {
                convo.messages.clear();
                convo.messages.push(ChatMessage {
                    role: MessageRole::System,
                    content: "Mensagens da tela limpas.".to_string(),
                    timestamp: Local::now().format("%H:%M:%S").to_string(),
                    tool_calls: Vec::new(),
                });
            }
            self.input_text.clear();
            self.save_state_now();
            return;
        }

        if self.prompt_history.last().map(|s| s.as_str()) != Some(&raw_text) {
            self.prompt_history.push(raw_text.clone());
        }
        self.history_idx = None;
        self.temp_input.clear();

        // Anexar contexto de arquivos selecionados, caso existam
        let mut dispatch_text = raw_text.clone();
        let mut display_text = raw_text.clone();
        if !self.attached_files.is_empty() {
            let mut attach_names = Vec::new();
            let mut attach_blocks = Vec::new();
            for path in &self.attached_files {
                attach_names.push(path.display().to_string());
                if let Ok(content) = fs::read_to_string(path) {
                    let snippet: String = content.chars().take(12_000).collect();
                    attach_blocks.push(format!(
                        "\n\n[Arquivo anexado: {}]\n```\n{}\n```",
                        path.display(),
                        snippet
                    ));
                } else {
                    attach_blocks.push(format!("\n\n[Arquivo anexado (binário ou ilegível): {}]", path.display()));
                }
            }
            display_text.push_str(&format!("\n📎 Anexos: {}", attach_names.join(", ")));
            dispatch_text.push_str(&attach_blocks.concat());
            self.attached_files.clear();
        }

        let timestamp = Local::now().format("%H:%M:%S").to_string();

        if let Some(convo) = self.current_conversation_mut() {
            if convo.title == "Nova Conversa" {
                let preview: String = raw_text.chars().take(24).collect();
                let clean = preview.trim().replace('\n', " ");
                if !clean.is_empty() {
                    convo.title = format!("{}...", clean);
                }
            }

            convo.messages.push(ChatMessage {
                role: MessageRole::User,
                content: display_text,
                timestamp,
                tool_calls: Vec::new(),
            });
        }

        let session_id = self
            .current_conversation()
            .map(|c| c.session_id.clone())
            .unwrap_or_else(|| Conversation::generate_session_id(1));

        self.input_text.clear();
        self.is_running = true;
        self.status_text = "Processando...".to_string();

        let spawn_cfg = SpawnConfig {
            text: dispatch_text,
            cwd: self.current_dir.clone(),
            provider: self.current_provider.clone(),
            model: self.selected_model.clone(),
            reasoning: self.selected_reasoning.clone(),
            mode: self.selected_mode,
            session_id,
            session_context: self.session_context,
            custom_python: self.custom_python_path.clone(),
        };

        spawn_zeus_command(
            spawn_cfg,
            self.event_sender.clone(),
            Arc::clone(&self.active_child),
            Arc::clone(&self.active_stdin),
        );
        self.save_state_now();
    }

    pub fn cancel_execution(&mut self) {
        self.pending_permission = None;
        let killed = kill_active_process(&self.active_child, &self.active_stdin);
        if killed {
            if let Some(convo) = self.current_conversation_mut() {
                convo.messages.push(ChatMessage {
                    role: MessageRole::System,
                    content: "⏹ Execução interrompida pelo usuário.".to_string(),
                    timestamp: Local::now().format("%H:%M:%S").to_string(),
                    tool_calls: Vec::new(),
                });
            }
        }

        self.is_running = false;
        self.status_text = "Cancelado".to_string();
        self.save_state_now();
    }

    pub fn ensure_env_loaded(&mut self) {
        if self.env_loaded {
            return;
        }
        let env_path = DesktopConfig::zeus_home().join(".env");
        let mut entries = Vec::new();
        if let Ok(raw) = fs::read_to_string(&env_path) {
            for line in raw.lines() {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                if let Some((k, v)) = trimmed.split_once('=') {
                    entries.push((
                        k.trim().to_string(),
                        v.trim().trim_matches('"').to_string(),
                    ));
                }
            }
        }
        self.env_entries = entries;
        self.env_loaded = true;
    }

    pub fn save_env_entries(&mut self) {
        let env_path = DesktopConfig::zeus_home().join(".env");
        if let Some(parent) = env_path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        // Atualiza ZEUS_PROVIDER / ZEUS_MODEL atuais também se presentes ou preserva os existentes
        let mut lines = Vec::new();
        for (k, v) in &self.env_entries {
            let clean_k = k.trim();
            if !clean_k.is_empty() {
                lines.push(format!("{}={}", clean_k, v.trim()));
            }
        }
        let content = if lines.is_empty() {
            String::new()
        } else {
            lines.join("\n") + "\n"
        };
        if fs::write(&env_path, content).is_ok() {
            self.show_toast(format!("Configuração salva em {}", env_path.display()));
            self.refresh_catalog();
        } else {
            self.show_toast("Erro ao salvar ~/.zeus/.env");
        }
    }

    pub fn mcp_config_path(&self) -> PathBuf {
        let local = self.current_dir.join("mcp_servers.json");
        if local.exists() {
            return local;
        }
        DesktopConfig::zeus_home().join("mcp_servers.json")
    }

    pub fn save_mcp_servers_map(&mut self, servers: &HashMap<String, McpServerConfigEntry>) {
        let path = self.mcp_config_path();
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let payload = serde_json::json!({ "mcpServers": servers });
        if let Ok(json_str) = serde_json::to_string_pretty(&payload) {
            if fs::write(&path, json_str).is_ok() {
                if let Some(cat) = self.catalog.as_mut() {
                    cat.mcp.config_path = path.display().to_string();
                    cat.mcp.servers = servers.clone();
                }
                self.show_toast("Servidores MCP atualizados.");
                self.refresh_catalog();
            }
        }
    }

    fn ensure_zeus_message_mut(convo: &mut Conversation) -> &mut ChatMessage {
        let need_new = convo
            .messages
            .last()
            .map(|m| m.role != MessageRole::Zeus)
            .unwrap_or(true);
        if need_new {
            convo.messages.push(ChatMessage {
                role: MessageRole::Zeus,
                content: String::new(),
                timestamp: Local::now().format("%H:%M:%S").to_string(),
                tool_calls: Vec::new(),
            });
        }
        convo.messages.last_mut().unwrap()
    }

    pub fn process_worker_events(&mut self, ctx: &egui::Context) {
        while let Ok(event) = self.event_receiver.try_recv() {
            ctx.request_repaint();
            match event {
                WorkerEvent::StreamChunk(chunk) => {
                    if let Some(convo) = self.current_conversation_mut() {
                        let msg = Self::ensure_zeus_message_mut(convo);
                        msg.content.push_str(&chunk);
                    }
                    self.mark_dirty();
                }
                WorkerEvent::FinalResponse { content, replace } => {
                    if let Some(convo) = self.current_conversation_mut() {
                        let msg = Self::ensure_zeus_message_mut(convo);
                        if replace || msg.content.trim().is_empty() {
                            msg.content = content;
                        } else if !msg.content.ends_with(&content) {
                            if !msg.content.is_empty() && !msg.content.ends_with('\n') {
                                msg.content.push_str("\n\n");
                            }
                            msg.content.push_str(&content);
                        }
                    }
                    self.mark_dirty();
                }
                WorkerEvent::ToolStart { name, arguments } => {
                    if let Some(convo) = self.current_conversation_mut() {
                        let msg = Self::ensure_zeus_message_mut(convo);
                        msg.tool_calls.push(ToolExecution {
                            name,
                            arguments,
                            result: None,
                            error: None,
                            output_lines: Vec::new(),
                            finished: false,
                        });
                    }
                    self.mark_dirty();
                }
                WorkerEvent::ToolOutput(chunk) => {
                    if let Some(convo) = self.current_conversation_mut() {
                        let msg = Self::ensure_zeus_message_mut(convo);
                        if let Some(tc) = msg.tool_calls.iter_mut().rev().find(|t| !t.finished) {
                            tc.output_lines.push(chunk);
                        } else {
                            if !msg.content.is_empty() && !msg.content.ends_with('\n') {
                                msg.content.push('\n');
                            }
                            msg.content.push_str(&chunk);
                        }
                    }
                    self.mark_dirty();
                }
                WorkerEvent::ToolResult {
                    name,
                    result,
                    error,
                } => {
                    if let Some(convo) = self.current_conversation_mut() {
                        let msg = Self::ensure_zeus_message_mut(convo);
                        if let Some(tc) = msg
                            .tool_calls
                            .iter_mut()
                            .rev()
                            .find(|t| !t.finished && t.name == name)
                        {
                            tc.result = Some(result);
                            tc.error = error;
                            tc.finished = true;
                        }
                    }
                    self.mark_dirty();
                }
                WorkerEvent::Status(text) => {
                    if !text.is_empty() {
                        self.status_text = text;
                    }
                }
                WorkerEvent::PermissionRequest(prompt) => {
                    self.status_text = "Aguardando confirmação...".to_string();
                    self.pending_permission = Some(prompt);
                }
                WorkerEvent::Metrics {
                    llm_calls,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    total_cost_usd,
                } => {
                    if let Some(convo) = self.current_conversation_mut() {
                        convo.llm_calls += llm_calls;
                        convo.actual_input_tokens += input_tokens;
                        convo.actual_output_tokens += output_tokens;
                        convo.total_latency_ms += latency_ms;
                        convo.total_cost_usd += total_cost_usd;
                    }
                    self.mark_dirty();
                }
                WorkerEvent::SessionCreated(sid) => {
                    if !sid.is_empty() {
                        self.new_conversation();
                        if let Some(convo) = self.current_conversation_mut() {
                            convo.session_id = sid;
                        }
                        self.save_state_now();
                    }
                }
                WorkerEvent::CatalogLoaded(cat) => {
                    self.catalog = Some(cat);
                }
                WorkerEvent::CatalogRefreshRequested => {
                    self.refresh_catalog();
                }
                WorkerEvent::ZeusOutput(line) => {
                    if let Some(cleaned) = sanitize_terminal_output(&line) {
                        if let Some(convo) = self.current_conversation_mut() {
                            if let Some(last) = convo.messages.last_mut() {
                                if last.role == MessageRole::Zeus {
                                    if cleaned == "⚡ Executando..."
                                        && (last.content.ends_with("⚡ Executando...")
                                            || last.content == "⚡ Executando...")
                                    {
                                        continue;
                                    }
                                    if !last.content.is_empty() {
                                        last.content.push('\n');
                                    }
                                    last.content.push_str(&cleaned);
                                    self.mark_dirty();
                                    continue;
                                }
                            }
                            convo.messages.push(ChatMessage {
                                role: MessageRole::Zeus,
                                content: cleaned,
                                timestamp: Local::now().format("%H:%M:%S").to_string(),
                                tool_calls: Vec::new(),
                            });
                            self.mark_dirty();
                        }
                    }
                }
                WorkerEvent::ZeusError(line) => {
                    if let Some(cleaned) = sanitize_terminal_output(&line) {
                        if let Some(convo) = self.current_conversation_mut() {
                            convo.messages.push(ChatMessage {
                                role: MessageRole::Error,
                                content: cleaned,
                                timestamp: Local::now().format("%H:%M:%S").to_string(),
                                tool_calls: Vec::new(),
                            });
                            self.mark_dirty();
                        }
                    }
                }
                WorkerEvent::Finished(success) => {
                    self.is_running = false;
                    self.pending_permission = None;
                    self.status_text = if success {
                        "Pronto".to_string()
                    } else {
                        "Concluído com avisos/erros".to_string()
                    };
                    // Preserva a preferência auto_scroll do usuário (não sobrescreve)
                    self.save_state_now();
                    self.refresh_catalog();
                }
            }
        }
        self.flush_state_if_needed();
    }
}

impl eframe::App for ZeusApp {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.process_worker_events(&ctx);

        // Barra Superior (Header)
        ui::header::render_top_bar(self, ui);

        // Barra Inferior (Status Bar)
        ui::header::render_bottom_bar(self, ui);

        // Barra Lateral Esquerda (Projetos e Conversas)
        ui::sidebar::render(self, ui);

        // Área Central (Chat e Controles)
        ui::chat::render(self, ui);

        // Modais / Janelas Flutuantes
        ui::modals::settings::render(self, &ctx);
        ui::modals::commands::render(self, &ctx);
        ui::modals::tools::render(self, &ctx);
        ui::modals::mcp::render(self, &ctx);
        ui::modals::ecosystem::render(self, &ctx);
        ui::modals::permission::render(self, &ctx);
        ui::modals::about::render(self, &ctx);
        ui::modals::add_project::render(self, &ctx);
    }

    fn on_exit(&mut self) {
        self.save_state_now();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_history_navigation() {
        let (tx, rx) = channel();
        let mut app = ZeusApp {
            conversations: vec![Conversation::new(1, "Teste".to_string())],
            active_conversation_idx: 0,
            next_conversation_id: 2,
            filter_convos_by_project: false,
            convo_search_query: String::new(),
            renaming_convo_idx: None,
            rename_convo_buf: String::new(),
            input_text: "rascunho".to_string(),
            prompt_history: vec!["primeiro".to_string(), "segundo".to_string()],
            history_idx: None,
            temp_input: String::new(),
            attached_files: Vec::new(),
            is_running: false,
            status_text: "Pronto".to_string(),
            toast_message: None,
            current_provider: "opencode_go".to_string(),
            selected_model: "deepseek-v4-pro".to_string(),
            selected_mode: ZeusMode::Sandbox,
            selected_reasoning: "Médio".to_string(),
            session_context: true,
            auto_scroll: false,
            custom_python_path: None,
            export_dir: None,
            current_dir: PathBuf::from("."),
            projects: Vec::new(),
            event_sender: tx,
            event_receiver: rx,
            active_child: Arc::new(Mutex::new(None)),
            active_stdin: Arc::new(Mutex::new(None)),
            pending_permission: None,
            catalog: None,
            dirty_state: false,
            last_save_at: Instant::now(),
            show_about: false,
            show_settings: false,
            show_commands: false,
            show_tools: false,
            show_mcp: false,
            show_ecosystem: false,
            ecosystem_tab: 0,
            ecosystem_filter: String::new(),
            commands_filter: String::new(),
            tools_filter: String::new(),
            show_add_project: false,
            new_project_path: String::new(),
            new_project_name: String::new(),
            env_entries: Vec::new(),
            env_loaded: false,
            show_env_secrets: false,
            new_env_key: String::new(),
            new_env_val: String::new(),
            mcp_new_name: String::new(),
            mcp_new_cmd_or_url: String::new(),
            mcp_new_args: String::new(),
        };

        app.navigate_history_up();
        assert_eq!(app.input_text, "segundo");
        app.navigate_history_up();
        assert_eq!(app.input_text, "primeiro");
        app.navigate_history_down();
        assert_eq!(app.input_text, "segundo");
        app.navigate_history_down();
        assert_eq!(app.input_text, "rascunho");

        // Simular Finished não deve sobrescrever auto_scroll = false
        let _ = app.event_sender.send(WorkerEvent::Finished(true));
        let ctx = egui::Context::default();
        app.process_worker_events(&ctx);
        assert!(!app.auto_scroll);
        assert!(!app.is_running);
    }

    #[test]
    fn test_worker_events_streaming_tools_and_edit_last() {
        let (tx, rx) = channel();
        let mut app = ZeusApp {
            conversations: vec![Conversation::new(1, "Teste".to_string())],
            active_conversation_idx: 0,
            next_conversation_id: 2,
            filter_convos_by_project: false,
            convo_search_query: String::new(),
            renaming_convo_idx: None,
            rename_convo_buf: String::new(),
            input_text: String::new(),
            prompt_history: Vec::new(),
            history_idx: None,
            temp_input: String::new(),
            attached_files: Vec::new(),
            is_running: true,
            status_text: "Processando...".to_string(),
            toast_message: None,
            current_provider: "opencode_go".to_string(),
            selected_model: "deepseek-v4-pro".to_string(),
            selected_mode: ZeusMode::Sandbox,
            selected_reasoning: "Médio".to_string(),
            session_context: true,
            auto_scroll: true,
            custom_python_path: None,
            export_dir: None,
            current_dir: PathBuf::from("."),
            projects: Vec::new(),
            event_sender: tx,
            event_receiver: rx,
            active_child: Arc::new(Mutex::new(None)),
            active_stdin: Arc::new(Mutex::new(None)),
            pending_permission: None,
            catalog: None,
            dirty_state: false,
            last_save_at: Instant::now(),
            show_about: false,
            show_settings: false,
            show_commands: false,
            show_tools: false,
            show_mcp: false,
            show_ecosystem: false,
            ecosystem_tab: 0,
            ecosystem_filter: String::new(),
            commands_filter: String::new(),
            tools_filter: String::new(),
            show_add_project: false,
            new_project_path: String::new(),
            new_project_name: String::new(),
            env_entries: Vec::new(),
            env_loaded: false,
            show_env_secrets: false,
            new_env_key: String::new(),
            new_env_val: String::new(),
            mcp_new_name: String::new(),
            mcp_new_cmd_or_url: String::new(),
            mcp_new_args: String::new(),
        };

        app.conversations[0].messages.push(ChatMessage {
            role: MessageRole::User,
            content: "Leia main.rs".to_string(),
            timestamp: "10:00:00".to_string(),
            tool_calls: Vec::new(),
        });

        let _ = app.event_sender.send(WorkerEvent::ToolStart {
            name: "read_file".to_string(),
            arguments: "{\"path\":\"main.rs\"}".to_string(),
        });
        let _ = app.event_sender.send(WorkerEvent::ToolOutput("lendo...".to_string()));
        let _ = app.event_sender.send(WorkerEvent::ToolResult {
            name: "read_file".to_string(),
            result: "fn main() {}".to_string(),
            error: None,
        });
        let _ = app.event_sender.send(WorkerEvent::StreamChunk("Aqui ".to_string()));
        let _ = app.event_sender.send(WorkerEvent::StreamChunk("está.".to_string()));
        let _ = app.event_sender.send(WorkerEvent::Metrics {
            llm_calls: 2,
            input_tokens: 150,
            output_tokens: 45,
            latency_ms: 420.0,
            total_cost_usd: 0.0025,
        });
        let _ = app.event_sender.send(WorkerEvent::Finished(true));

        let ctx = egui::Context::default();
        app.process_worker_events(&ctx);

        let convo = app.current_conversation().unwrap();
        assert_eq!(convo.messages.len(), 2);
        let zeus_msg = &convo.messages[1];
        assert_eq!(zeus_msg.content, "Aqui está.");
        assert_eq!(zeus_msg.tool_calls.len(), 1);
        assert!(zeus_msg.tool_calls[0].finished);
        assert_eq!(convo.actual_input_tokens, 150);
        assert_eq!(convo.actual_output_tokens, 45);
        assert_eq!(convo.total_latency_ms, 420.0);

        app.edit_last_user_message();
        assert_eq!(app.input_text, "Leia main.rs");
        assert!(app.current_conversation().unwrap().messages.is_empty());
    }
}
