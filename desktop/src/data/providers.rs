use std::path::{Path, PathBuf};

pub fn all_providers() -> &'static [(&'static str, &'static str)] {
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

pub fn provider_display_name(provider: &str) -> &'static str {
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

pub fn get_models_for_provider(provider: &str) -> Vec<(&'static str, &'static str)> {
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

pub fn detect_provider_and_model(dir: &Path) -> (String, String) {
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
