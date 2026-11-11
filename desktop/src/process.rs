use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;

use serde_json::Value;

use crate::state::{
    reasoning_label_to_env, CatalogData, PermissionPrompt, WorkerEvent, ZeusMode,
};

pub fn find_zeus_python(cwd: &Path, custom_path: Option<&str>) -> PathBuf {
    // 1. Caminho customizado configurado pelo usuário
    if let Some(custom) = custom_path {
        let p = PathBuf::from(custom.trim());
        if p.exists() {
            return p;
        }
    }

    // 2. Variável de ambiente ZEUS_PYTHON
    if let Ok(path) = std::env::var("ZEUS_PYTHON") {
        let p = PathBuf::from(path);
        if p.exists() {
            return p;
        }
    }

    // 3. Venv local do projeto atual (.venv)
    let cwd_venv = cwd.join(".venv/bin/python3");
    if cwd_venv.exists() {
        return cwd_venv;
    }

    // 4. Venv local alternativo (venv)
    let cwd_alt_venv = cwd.join("venv/bin/python3");
    if cwd_alt_venv.exists() {
        return cwd_alt_venv;
    }

    // 5. Venv padrão do Zeus no home (~/Documentos/Dev/Zeus/.venv)
    if let Ok(home) = std::env::var("HOME") {
        let home_venv = PathBuf::from(home).join("Documentos/Dev/Zeus/.venv/bin/python3");
        if home_venv.exists() {
            return home_venv;
        }
    }

    // 6. Diretório pai (.venv)
    if let Some(parent) = cwd.parent() {
        let parent_venv = parent.join(".venv/bin/python3");
        if parent_venv.exists() {
            return parent_venv;
        }
    }

    PathBuf::from("python3")
}

pub fn find_zeus_dir(cwd: &Path) -> Option<PathBuf> {
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

pub fn sanitize_terminal_output(line: &str) -> Option<String> {
    // 1. Remover sequências de escape ANSI com byte ESC (\x1b)
    let mut cleaned = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();

    while let Some(c) = chars.next() {
        if c == '\x1b' && chars.peek() == Some(&'[') {
            chars.next();
            for next in chars.by_ref() {
                if next.is_ascii_alphabetic() {
                    break;
                }
            }
            continue;
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

    // Preservar indentação à esquerda (ex.: código/YAML/listas), removendo apenas espaços finais
    let end_trimmed = without_codes.trim_end_matches(&['\r', '\n', ' '][..]);
    let trimmed_check = end_trimmed.trim();

    // 3. Ignorar linhas de moldura/card da CLI do Zeus (bordas superior e inferior)
    if trimmed_check.starts_with("╭──")
        || trimmed_check.starts_with("╰──")
        || (!trimmed_check.is_empty() && trimmed_check.chars().all(|c| c == '─'))
    {
        return None;
    }

    // 4. Remover caractere de borda lateral "│" caso a linha seja uma moldura de CLI
    let final_text = if let Some(rest) = end_trimmed.trim_start().strip_prefix('│') {
        rest.strip_prefix(' ').unwrap_or(rest).to_string()
    } else {
        end_trimmed.to_string()
    };

    if final_text.trim().is_empty() {
        None
    } else {
        Some(final_text)
    }
}

pub fn parse_desktop_json_line(line: &str) -> Option<WorkerEvent> {
    let trimmed = line.trim();
    if !trimmed.starts_with('{') {
        return None;
    }
    let val: Value = serde_json::from_str(trimmed).ok()?;
    let ev_type = val.get("type")?.as_str()?;

    match ev_type {
        "stream_chunk" => {
            let content = val.get("content")?.as_str()?.to_string();
            Some(WorkerEvent::StreamChunk(content))
        }
        "final_response" => {
            let content = val.get("content")?.as_str()?.to_string();
            let replace = val.get("replace").and_then(|v| v.as_bool()).unwrap_or(false);
            Some(WorkerEvent::FinalResponse { content, replace })
        }
        "tool_start" => {
            let name = val.get("name").and_then(|v| v.as_str()).unwrap_or("tool").to_string();
            let arguments = val
                .get("arguments")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            Some(WorkerEvent::ToolStart { name, arguments })
        }
        "tool_output" => {
            let chunk = val.get("chunk").and_then(|v| v.as_str()).unwrap_or("").to_string();
            Some(WorkerEvent::ToolOutput(chunk))
        }
        "tool_result" => {
            let name = val.get("name").and_then(|v| v.as_str()).unwrap_or("tool").to_string();
            let result = val
                .get("result")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let error = val
                .get("error")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            Some(WorkerEvent::ToolResult {
                name,
                result,
                error,
            })
        }
        "status" => {
            let text = val.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string();
            Some(WorkerEvent::Status(text))
        }
        "permission_request" => {
            let id = val.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let kind = val
                .get("kind")
                .and_then(|v| v.as_str())
                .unwrap_or("terminal_confirm")
                .to_string();
            let message = val
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let options = val
                .get("options")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|x| x.as_str().map(|s| s.to_string()))
                        .collect()
                })
                .unwrap_or_else(|| vec!["once".to_string(), "deny".to_string()]);
            let secret = val.get("secret").and_then(|v| v.as_bool()).unwrap_or(false);
            Some(WorkerEvent::PermissionRequest(PermissionPrompt {
                id,
                kind,
                message,
                options,
                secret,
                input_secret: String::new(),
            }))
        }
        "metrics" => Some(WorkerEvent::Metrics {
            llm_calls: val.get("llm_calls").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
            input_tokens: val.get("input_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
            output_tokens: val.get("output_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
            latency_ms: val.get("latency_ms").and_then(|v| v.as_f64()).unwrap_or(0.0),
            total_cost_usd: val
                .get("total_cost_usd")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0),
        }),
        "session_created" => {
            let sid = val
                .get("session_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            Some(WorkerEvent::SessionCreated(sid))
        }
        "catalog_refresh" => Some(WorkerEvent::CatalogRefreshRequested),
        "error" => {
            let msg = val
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("Erro desconhecido")
                .to_string();
            Some(WorkerEvent::ZeusError(msg))
        }
        "done" => {
            let success = val.get("success").and_then(|v| v.as_bool()).unwrap_or(true);
            Some(WorkerEvent::Finished(success))
        }
        _ => None,
    }
}

pub fn send_permission_response(
    stdin_arc: &Arc<Mutex<Option<ChildStdin>>>,
    id: &str,
    decision: &str,
    secret: Option<&str>,
) -> bool {
    if let Ok(mut lock) = stdin_arc.lock() {
        if let Some(stdin) = lock.as_mut() {
            let payload = serde_json::json!({
                "type": "permission_response",
                "id": id,
                "decision": decision,
                "secret": secret,
            });
            if writeln!(stdin, "{}", payload).is_ok() {
                let _ = stdin.flush();
                return true;
            }
        }
    }
    false
}

pub struct SpawnConfig {
    pub text: String,
    pub cwd: PathBuf,
    pub provider: String,
    pub model: String,
    pub reasoning: String,
    pub mode: ZeusMode,
    pub session_id: String,
    pub session_context: bool,
    pub custom_python: Option<String>,
}

fn apply_zeus_env(cmd: &mut Command, cwd: &Path, zeus_dir: Option<&PathBuf>) {
    cmd.current_dir(cwd);
    if let Some(dir) = zeus_dir {
        let current_pythonpath = std::env::var("PYTHONPATH").unwrap_or_default();
        let new_pythonpath = if current_pythonpath.is_empty() {
            dir.to_string_lossy().to_string()
        } else {
            format!("{}:{}", dir.to_string_lossy(), current_pythonpath)
        };
        cmd.env("PYTHONPATH", new_pythonpath);
    }
}

pub fn spawn_zeus_command(
    config: SpawnConfig,
    tx: Sender<WorkerEvent>,
    child_arc: Arc<Mutex<Option<Child>>>,
    stdin_arc: Arc<Mutex<Option<ChildStdin>>>,
) {
    thread::spawn(move || {
        let python_bin = find_zeus_python(&config.cwd, config.custom_python.as_deref());
        let zeus_dir = find_zeus_dir(&config.cwd);

        let mut cmd = Command::new(&python_bin);
        cmd.args(["-m", "zeus.cli", "--desktop-json", "--no-color", "-q", &config.text]);
        if config.session_context && !config.session_id.is_empty() {
            cmd.args(["--session", &config.session_id]);
        }
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            cmd.process_group(0);
        }

        cmd.env("ZEUS_PROVIDER", &config.provider);
        cmd.env("ZEUS_MODEL", &config.model);
        cmd.env("ZEUS_REASONING_EFFORT", reasoning_label_to_env(&config.reasoning));
        cmd.env("ZEUS_PROJECT_DIR", config.cwd.to_string_lossy().to_string());

        match config.mode {
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

        apply_zeus_env(&mut cmd, &config.cwd, zeus_dir.as_ref());

        match cmd.spawn() {
            Ok(mut child) => {
                let stdin = child.stdin.take();
                let stdout = child.stdout.take();
                let stderr = child.stderr.take();

                if let Ok(mut lock) = stdin_arc.lock() {
                    *lock = stdin;
                }
                if let Ok(mut lock) = child_arc.lock() {
                    *lock = Some(child);
                }

                let tx_out = tx.clone();
                let out_handle = thread::spawn(move || {
                    let mut saw_done = false;
                    if let Some(out) = stdout {
                        let reader = BufReader::new(out);
                        for line in reader.lines().flatten() {
                            if let Some(ev) = parse_desktop_json_line(&line) {
                                if matches!(ev, WorkerEvent::Finished(_)) {
                                    saw_done = true;
                                }
                                let _ = tx_out.send(ev);
                            } else {
                                let _ = tx_out.send(WorkerEvent::ZeusOutput(line));
                            }
                        }
                    }
                    saw_done
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

                let saw_done = out_handle.join().unwrap_or(false);
                let _ = err_handle.join();

                if let Ok(mut lock) = stdin_arc.lock() {
                    *lock = None;
                }

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

                if !saw_done {
                    let _ = tx.send(WorkerEvent::Finished(success));
                }
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

pub fn fetch_desktop_catalog(
    cwd: PathBuf,
    custom_python: Option<String>,
    tx: Sender<WorkerEvent>,
) {
    thread::spawn(move || {
        let python_bin = find_zeus_python(&cwd, custom_python.as_deref());
        let zeus_dir = find_zeus_dir(&cwd);

        let mut cmd = Command::new(&python_bin);
        cmd.args(["-m", "zeus.cli", "--desktop-catalog"]);
        apply_zeus_env(&mut cmd, &cwd, zeus_dir.as_ref());

        if let Ok(output) = cmd.output() {
            if output.status.success() {
                let raw = String::from_utf8_lossy(&output.stdout);
                if let Ok(catalog) = serde_json::from_str::<CatalogData>(raw.trim()) {
                    let _ = tx.send(WorkerEvent::CatalogLoaded(catalog));
                }
            }
        }
    });
}

pub fn kill_active_process(
    child_arc: &Arc<Mutex<Option<Child>>>,
    stdin_arc: &Arc<Mutex<Option<ChildStdin>>>,
) -> bool {
    if let Ok(mut lock) = stdin_arc.lock() {
        *lock = None;
    }
    let mut killed = false;
    if let Ok(mut lock) = child_arc.lock() {
        if let Some(mut child) = lock.take() {
            #[cfg(unix)]
            {
                let pid = child.id() as libc::pid_t;
                unsafe {
                    libc::kill(-pid, libc::SIGTERM);
                }
            }
            let _ = child.kill();
            killed = true;
        }
    }
    killed
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_terminal_output() {
        assert_eq!(sanitize_terminal_output("╭────────────────────────────"), None);
        assert_eq!(sanitize_terminal_output("╰────────────────────────────"), None);
        assert_eq!(sanitize_terminal_output("─────────────────────────────"), None);

        assert_eq!(
            sanitize_terminal_output("│ Olá do Zeus!"),
            Some("Olá do Zeus!".to_string())
        );

        let ansi_string = "\x1b[1;32mTexto Verde\x1b[0m";
        assert_eq!(
            sanitize_terminal_output(ansi_string),
            Some("Texto Verde".to_string())
        );

        // Deve preservar indentação à esquerda em código/listas
        assert_eq!(
            sanitize_terminal_output("    def hello():"),
            Some("    def hello():".to_string())
        );
    }

    #[test]
    fn test_parse_desktop_json_line() {
        let chunk = r#"{"type":"stream_chunk","content":"Olá "}"#;
        assert!(matches!(
            parse_desktop_json_line(chunk),
            Some(WorkerEvent::StreamChunk(s)) if s == "Olá "
        ));

        let tool = r#"{"type":"tool_start","name":"read_file","arguments":"{\"path\":\"a.py\"}"}"#;
        assert!(matches!(
            parse_desktop_json_line(tool),
            Some(WorkerEvent::ToolStart { name, .. }) if name == "read_file"
        ));

        let perm = r#"{"type":"permission_request","id":"abc","kind":"terminal_confirm","message":"Executar ls?","options":["once","deny"],"secret":false}"#;
        assert!(matches!(
            parse_desktop_json_line(perm),
            Some(WorkerEvent::PermissionRequest(p)) if p.id == "abc" && p.kind == "terminal_confirm"
        ));

        let metrics = r#"{"type":"metrics","llm_calls":2,"input_tokens":100,"output_tokens":50,"latency_ms":300.5,"total_cost_usd":0.001}"#;
        assert!(matches!(
            parse_desktop_json_line(metrics),
            Some(WorkerEvent::Metrics { input_tokens: 100, output_tokens: 50, .. })
        ));

        assert!(parse_desktop_json_line("texto normal sem json").is_none());
    }
}
