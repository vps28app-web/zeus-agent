use std::path::PathBuf;
use eframe::egui;

use crate::app::ZeusApp;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_add_project {
        return;
    }

    egui::Window::new("Adicionar Projeto")
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.label("Caminho da pasta do projeto:");
            ui.horizontal(|ui| {
                ui.text_edit_singleline(&mut app.new_project_path);
                if ui.button("📂 Procurar...").clicked() {
                    if let Some(p) = ZeusApp::pick_folder() {
                        app.new_project_path = p.display().to_string();
                        if app.new_project_name.is_empty() {
                            if let Some(n) = p.file_name() {
                                app.new_project_name = n.to_string_lossy().to_string();
                            }
                        }
                    }
                }
            });

            ui.add_space(4.0);
            ui.label("Nome do projeto (opcional):");
            ui.text_edit_singleline(&mut app.new_project_name);

            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("Adicionar").clicked() {
                    let path_buf = PathBuf::from(&app.new_project_path);
                    if path_buf.exists() {
                        let mut name = app.new_project_name.trim().to_string();
                        if name.is_empty() {
                            name = path_buf
                                .file_name()
                                .map(|n| n.to_string_lossy().to_string())
                                .unwrap_or_else(|| "Projeto".to_string());
                        }
                        app.add_project(path_buf.clone());
                        if let Some(p) = app.projects.iter_mut().find(|p| p.path == path_buf) {
                            p.name = name;
                        }
                        app.save_state();

                        app.new_project_path.clear();
                        app.new_project_name.clear();
                        app.show_add_project = false;
                    }
                }
                if ui.button("Cancelar").clicked() {
                    app.new_project_path.clear();
                    app.new_project_name.clear();
                    app.show_add_project = false;
                }
            });
        });
}
