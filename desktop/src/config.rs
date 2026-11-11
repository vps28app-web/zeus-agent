use std::fs;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};

use crate::state::{normalize_reasoning_label, Conversation, ProjectItem, ZeusMode};

fn default_true() -> bool {
    true
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DesktopConfig {
    pub current_dir: PathBuf,
    pub projects: Vec<ProjectItem>,
    pub current_provider: String,
    pub selected_model: String,
    pub selected_mode: ZeusMode,
    pub selected_reasoning: String,
    #[serde(default = "default_true")]
    pub session_context: bool,
    #[serde(default = "default_true")]
    pub auto_scroll: bool,
    #[serde(default)]
    pub custom_python_path: Option<String>,
    #[serde(default)]
    pub conversations: Vec<Conversation>,
    #[serde(default)]
    pub active_conversation_idx: usize,
    #[serde(default)]
    pub filter_convos_by_project: bool,
    #[serde(default)]
    pub export_dir: Option<PathBuf>,
}

impl Default for DesktopConfig {
    fn default() -> Self {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let home_path = PathBuf::from(&home);
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
        projects.retain(|p| p.path.exists());

        let initial_dir = projects
            .iter()
            .find(|p| p.name == "Zeus (Core)")
            .or_else(|| projects.first())
            .map(|p| p.path.clone())
            .unwrap_or(current_path);

        Self {
            current_dir: initial_dir,
            projects,
            current_provider: "opencode_go".to_string(),
            selected_model: "deepseek-v4-pro".to_string(),
            selected_mode: ZeusMode::Sandbox,
            selected_reasoning: "Médio".to_string(),
            session_context: true,
            auto_scroll: true,
            custom_python_path: None,
            conversations: Vec::new(),
            active_conversation_idx: 0,
            filter_convos_by_project: false,
            export_dir: None,
        }
    }
}

impl DesktopConfig {
    pub fn zeus_home() -> PathBuf {
        if let Ok(zh) = std::env::var("ZEUS_HOME") {
            let trimmed = zh.trim();
            if !trimmed.is_empty() {
                return PathBuf::from(trimmed);
            }
        }
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".zeus")
    }

    pub fn config_path() -> PathBuf {
        Self::zeus_home().join("desktop_state.json")
    }

    pub fn default_export_dir() -> PathBuf {
        Self::zeus_home().join("exports")
    }

    pub fn load() -> Option<Self> {
        Self::load_from_path(&Self::config_path())
    }

    pub fn load_from_path(path: &Path) -> Option<Self> {
        if !path.exists() {
            return None;
        }

        let content = fs::read_to_string(path).ok()?;
        let mut config: DesktopConfig = serde_json::from_str(&content).ok()?;

        // Filtrar projetos que não existem mais no disco
        config.projects.retain(|p| p.path.exists());

        // Se current_dir não existir mais, volta para o primeiro projeto existente
        if !config.current_dir.exists() {
            if let Some(first) = config.projects.first() {
                config.current_dir = first.path.clone();
            }
        }

        config.selected_reasoning = normalize_reasoning_label(&config.selected_reasoning);

        // Garantir session_id único para conversas antigas sem esse campo
        for convo in &mut config.conversations {
            if convo.session_id.trim().is_empty() {
                convo.session_id = Conversation::generate_session_id(convo.id);
            }
        }

        Some(config)
    }

    pub fn save(&self) -> Result<(), Box<dyn std::error::Error>> {
        self.save_to_path(&Self::config_path())
    }

    pub fn save_to_path(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let json = serde_json::to_string_pretty(self)?;
        fs::write(path, json)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_save_and_load_backfills_session_id() {
        let dir = std::env::temp_dir().join("zeus_desktop_cfg_test");
        let _ = fs::create_dir_all(&dir);
        let cfg_path = dir.join("state.json");

        let mut cfg = DesktopConfig::default();
        cfg.selected_reasoning = "Medium".to_string();
        let mut convo = Conversation::new(7, "Teste".to_string());
        convo.session_id.clear();
        cfg.conversations.push(convo);

        cfg.save_to_path(&cfg_path).unwrap();
        let loaded = DesktopConfig::load_from_path(&cfg_path).unwrap();

        assert_eq!(loaded.selected_reasoning, "Médio");
        assert_eq!(loaded.conversations.len(), 1);
        assert!(!loaded.conversations[0].session_id.is_empty());

        let _ = fs::remove_dir_all(&dir);
    }
}
