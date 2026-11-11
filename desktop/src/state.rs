use std::collections::HashMap;
use std::path::PathBuf;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum MessageRole {
    User,
    Zeus,
    System,
    Error,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ToolExecution {
    pub name: String,
    pub arguments: String,
    pub result: Option<String>,
    pub error: Option<String>,
    #[serde(default)]
    pub output_lines: Vec<String>,
    #[serde(default)]
    pub finished: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: MessageRole,
    pub content: String,
    pub timestamp: String,
    #[serde(default)]
    pub tool_calls: Vec<ToolExecution>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Conversation {
    pub id: usize,
    #[serde(default)]
    pub session_id: String,
    pub title: String,
    #[serde(default)]
    pub project_path: Option<PathBuf>,
    pub messages: Vec<ChatMessage>,
    #[serde(default)]
    pub actual_input_tokens: usize,
    #[serde(default)]
    pub actual_output_tokens: usize,
    #[serde(default)]
    pub llm_calls: usize,
    #[serde(default)]
    pub total_cost_usd: f64,
    #[serde(default)]
    pub total_latency_ms: f64,
}

impl Conversation {
    pub fn generate_session_id(id: usize) -> String {
        let millis = chrono::Utc::now().timestamp_millis();
        format!("desktop_{}_{}", millis, id)
    }

    pub fn new(id: usize, title: String) -> Self {
        Self {
            id,
            session_id: Self::generate_session_id(id),
            title,
            project_path: None,
            messages: Vec::new(),
            actual_input_tokens: 0,
            actual_output_tokens: 0,
            llm_calls: 0,
            total_cost_usd: 0.0,
            total_latency_ms: 0.0,
        }
    }

    pub fn has_real_metrics(&self) -> bool {
        self.actual_input_tokens > 0 || self.actual_output_tokens > 0 || self.llm_calls > 0
    }

    pub fn total_tokens(&self) -> usize {
        if self.actual_input_tokens > 0 || self.actual_output_tokens > 0 {
            return self.actual_input_tokens + self.actual_output_tokens;
        }
        let total_chars: usize = self.messages.iter().map(|m| m.content.chars().count()).sum();
        if total_chars == 0 {
            0
        } else {
            ((total_chars as f64) / 3.5).ceil() as usize
        }
    }

    pub fn export_markdown(&self) -> String {
        let mut md = String::new();
        md.push_str(&format!("# {}\n\n", self.title));
        let token_label = if self.has_real_metrics() {
            format!(
                "Tokens reais: {} (entrada: {}, saída: {}) | Custo: ${:.6}",
                self.total_tokens(),
                self.actual_input_tokens,
                self.actual_output_tokens,
                self.total_cost_usd
            )
        } else {
            format!("Total estimado: {} tokens", self.total_tokens())
        };
        md.push_str(&format!("*Exportado do Zeus Desktop — {}*\n\n---\n\n", token_label));

        for msg in &self.messages {
            let role_header = match msg.role {
                MessageRole::User => format!("### 👤 Você ({})\n\n", msg.timestamp),
                MessageRole::Zeus => format!("### ⚡ Zeus ({})\n\n", msg.timestamp),
                MessageRole::System => format!("> **Sistema ({})**: ", msg.timestamp),
                MessageRole::Error => format!("### ❌ Erro ({})\n\n", msg.timestamp),
            };

            md.push_str(&role_header);
            if !msg.tool_calls.is_empty() {
                for tc in &msg.tool_calls {
                    md.push_str(&format!("- 🔧 `{}` (`{}`)\n", tc.name, tc.arguments));
                }
                md.push('\n');
            }
            md.push_str(&msg.content);
            md.push_str("\n\n---\n\n");
        }

        md
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum ZeusMode {
    Sandbox,
    Terminal,
    Auto,
    DryRun,
    ReadOnly,
}

impl ZeusMode {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Sandbox => "🛡️ Sandbox",
            Self::Terminal => "⚡ Terminal",
            Self::Auto => "🚀 Auto",
            Self::DryRun => "👁️ Dry-Run",
            Self::ReadOnly => "🔍 Leitura",
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            Self::Sandbox => "Comandos isolados no sandbox",
            Self::Terminal => "Host com confirmação manual",
            Self::Auto => "Execução autônoma sem prompt",
            Self::DryRun => "Simulação sem alterar arquivos",
            Self::ReadOnly => "Apenas leitura, execuções bloqueadas",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ProjectItem {
    pub name: String,
    pub path: PathBuf,
}

#[derive(Clone, Copy)]
pub struct CommandInfo {
    pub cmd: &'static str,
    pub desc: &'static str,
    pub category: &'static str,
}

impl CommandInfo {
    pub const fn new(cmd: &'static str, desc: &'static str, category: &'static str) -> Self {
        Self { cmd, desc, category }
    }
}

#[derive(Clone, Copy)]
pub struct ToolInfo {
    pub name: &'static str,
    pub desc: &'static str,
    pub category: &'static str,
}

impl ToolInfo {
    pub const fn new(name: &'static str, desc: &'static str, category: &'static str) -> Self {
        Self { name, desc, category }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DynamicModel {
    pub id: String,
    pub label: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DynamicProvider {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub models: Vec<DynamicModel>,
    #[serde(default)]
    pub env_vars: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DynamicCommand {
    pub cmd: String,
    pub desc: String,
    pub category: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DynamicTool {
    pub name: String,
    pub desc: String,
    pub category: String,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct McpServerConfigEntry {
    #[serde(default)]
    pub command: Option<String>,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub url: Option<String>,
    #[serde(default)]
    pub disabled: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct McpCatalogInfo {
    #[serde(default)]
    pub config_path: String,
    #[serde(default)]
    pub servers: HashMap<String, McpServerConfigEntry>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct EnvCatalogInfo {
    #[serde(default)]
    pub env_file: String,
    #[serde(default)]
    pub provider: String,
    #[serde(default)]
    pub model: String,
    #[serde(default)]
    pub configured_keys: HashMap<String, bool>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct MemoryEntry {
    pub key: String,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ScheduledTaskEntry {
    pub task_id: String,
    #[serde(default)]
    pub session_id: String,
    pub command: String,
    pub schedule: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub next_run: Option<String>,
    #[serde(default)]
    pub enabled: i64,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct SessionSummaryEntry {
    pub session_id: String,
    #[serde(default)]
    pub input_tokens: usize,
    #[serde(default)]
    pub output_tokens: usize,
    #[serde(default)]
    pub records: usize,
    #[serde(default)]
    pub created_at: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct EcosystemCatalogInfo {
    #[serde(default)]
    pub memories: Vec<MemoryEntry>,
    #[serde(default)]
    pub scheduled_tasks: Vec<ScheduledTaskEntry>,
    #[serde(default)]
    pub recent_sessions: Vec<SessionSummaryEntry>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct CatalogData {
    #[serde(default)]
    pub providers: Vec<DynamicProvider>,
    #[serde(default)]
    pub commands: Vec<DynamicCommand>,
    #[serde(default)]
    pub tools: Vec<DynamicTool>,
    #[serde(default)]
    pub mcp: McpCatalogInfo,
    #[serde(default)]
    pub env: EnvCatalogInfo,
    #[serde(default)]
    pub ecosystem: EcosystemCatalogInfo,
}

#[derive(Clone, Debug)]
pub struct PermissionPrompt {
    pub id: String,
    pub kind: String,
    pub message: String,
    pub options: Vec<String>,
    pub secret: bool,
    pub input_secret: String,
}

pub enum WorkerEvent {
    StreamChunk(String),
    FinalResponse {
        content: String,
        replace: bool,
    },
    ToolStart {
        name: String,
        arguments: String,
    },
    ToolOutput(String),
    ToolResult {
        name: String,
        result: String,
        error: Option<String>,
    },
    Status(String),
    PermissionRequest(PermissionPrompt),
    Metrics {
        llm_calls: usize,
        input_tokens: usize,
        output_tokens: usize,
        latency_ms: f64,
        total_cost_usd: f64,
    },
    SessionCreated(String),
    CatalogLoaded(CatalogData),
    CatalogRefreshRequested,
    ZeusOutput(String),
    ZeusError(String),
    Finished(bool),
}

pub fn normalize_reasoning_label(value: &str) -> String {
    match value.trim().to_lowercase().as_str() {
        "mínimo" | "minimo" | "minimal" => "Mínimo".to_string(),
        "baixo" | "low" => "Baixo".to_string(),
        "médio" | "medio" | "medium" => "Médio".to_string(),
        "alto" | "high" => "Alto".to_string(),
        _ => "Médio".to_string(),
    }
}

pub fn reasoning_label_to_env(value: &str) -> &'static str {
    match value.trim().to_lowercase().as_str() {
        "mínimo" | "minimo" | "minimal" => "minimal",
        "baixo" | "low" => "low",
        "alto" | "high" => "high",
        _ => "medium",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_conversation_tokens() {
        let mut convo = Conversation::new(1, "Teste".to_string());
        assert_eq!(convo.total_tokens(), 0);

        convo.messages.push(ChatMessage {
            role: MessageRole::User,
            content: "Olá mundo, como vai você?".to_string(),
            timestamp: "12:00:00".to_string(),
            tool_calls: Vec::new(),
        });
        assert!(convo.total_tokens() > 0);

        convo.actual_input_tokens = 120;
        convo.actual_output_tokens = 80;
        assert_eq!(convo.total_tokens(), 200);
        assert!(convo.has_real_metrics());
    }

    #[test]
    fn test_conversation_export_markdown() {
        let mut convo = Conversation::new(1, "Conversa de Teste".to_string());
        convo.messages.push(ChatMessage {
            role: MessageRole::User,
            content: "Qual a capital do Brasil?".to_string(),
            timestamp: "10:00:00".to_string(),
            tool_calls: Vec::new(),
        });
        convo.messages.push(ChatMessage {
            role: MessageRole::Zeus,
            content: "A capital do Brasil é Brasília.".to_string(),
            timestamp: "10:00:01".to_string(),
            tool_calls: Vec::new(),
        });

        let md = convo.export_markdown();
        assert!(md.contains("# Conversa de Teste"));
        assert!(md.contains("Qual a capital do Brasil?"));
        assert!(md.contains("Brasília."));
    }

    #[test]
    fn test_reasoning_normalization() {
        assert_eq!(normalize_reasoning_label("Medium"), "Médio");
        assert_eq!(normalize_reasoning_label("mínimo"), "Mínimo");
        assert_eq!(reasoning_label_to_env("Alto"), "high");
        assert_eq!(reasoning_label_to_env("Baixo"), "low");
    }
}
