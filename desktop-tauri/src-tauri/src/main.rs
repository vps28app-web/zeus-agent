use std::process::Command;
use std::path::PathBuf;

#[tauri::command]
async fn run_zeus(command: String, cwd: String) -> Result<String, String> {
    let zeus_python = find_zeus_python(&cwd)?;
    let zeus_dir = find_zeus_dir(&cwd);

    let mut cmd = Command::new(&zeus_python);
    cmd.args(["-m", "zeus.cli", "-q", &command])
        .current_dir(&cwd);

    if let Some(dir) = zeus_dir {
        let pythonpath = std::env::var("PYTHONPATH").unwrap_or_default();
        let new_path = if pythonpath.is_empty() {
            dir
        } else {
            format!("{}:{}", dir, pythonpath)
        };
        cmd.env("PYTHONPATH", new_path);
    }

    let output = cmd.output()
        .map_err(|e| format!("Falha ao executar Zeus: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn find_zeus_python(cwd: &str) -> Result<String, String> {
    // 1. Variável de ambiente
    if let Ok(python) = std::env::var("ZEUS_PYTHON") {
        return Ok(python);
    }

    // 2. Venv do Zeus no diretório pai do desktop
    let desktop_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let zeus_venv = desktop_dir.join("../.venv/bin/python3");
    if zeus_venv.exists() {
        return Ok(zeus_venv.to_string_lossy().to_string());
    }

    // 3. Venv do Zeus no home
    if let Ok(home) = std::env::var("HOME") {
        let home_venv = PathBuf::from(home).join("Documentos/Dev/Zeus/.venv/bin/python3");
        if home_venv.exists() {
            return Ok(home_venv.to_string_lossy().to_string());
        }
    }

    // 4. Venv do projeto atual
    let cwd_venv = PathBuf::from(cwd).join(".venv/bin/python3");
    if cwd_venv.exists() {
        return Ok(cwd_venv.to_string_lossy().to_string());
    }

    // 5. Fallback
    Ok("python3".to_string())
}

fn find_zeus_dir(cwd: &str) -> Option<String> {
    // 1. Variável de ambiente
    if let Ok(dir) = std::env::var("ZEUS_DIR") {
        return Some(dir);
    }

    // 2. Diretório atual tem zeus/
    let cwd_path = PathBuf::from(cwd);
    if cwd_path.join("zeus/__init__.py").exists() {
        return Some(cwd.to_string());
    }

    // 3. Diretório pai tem zeus/
    if let Some(parent) = cwd_path.parent() {
        if parent.join("zeus/__init__.py").exists() {
            return Some(parent.to_string_lossy().to_string());
        }
    }

    // 4. Caminho padrão
    if let Ok(home) = std::env::var("HOME") {
        let default = PathBuf::from(home).join("Documentos/Dev/Zeus");
        if default.join("zeus/__init__.py").exists() {
            return Some(default.to_string_lossy().to_string());
        }
    }

    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![run_zeus])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
