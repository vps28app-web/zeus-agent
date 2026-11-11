use std::path::PathBuf;
use chrono::Local;
use eframe::egui;

use crate::app::ZeusApp;
use crate::data::providers::detect_provider_and_model;
use crate::state::ChatMessage;

pub fn render(app: &mut ZeusApp, ui: &mut egui::Ui) {
    egui::Panel::left("sidebar_panel")
        .resizable(true)
        .default_size(250.0)
        .min_size(190.0)
        .max_size(380.0)
        .show(ui, |ui| {
            ui.add_space(6.0);

            // Cabeçalho Projetos com botão "+" à direita
            ui.horizontal(|ui| {
                ui.heading("Projetos");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let add_btn = ui.button(egui::RichText::new("+").strong().size(16.0));
                    if add_btn.on_hover_text("Adicionar projeto").clicked() {
                        if let Some(folder) = ZeusApp::pick_folder() {
                            app.add_project(folder);
                        } else {
                            app.show_add_project = true;
                        }
                    }
                });
            });
            ui.separator();

            let mut selected_project: Option<PathBuf> = None;
            let mut remove_project_idx: Option<usize> = None;

            for (idx, project) in app.projects.iter().enumerate() {
                let is_active = app.current_dir == project.path;
                let text = if is_active {
                    format!("▶ {}", project.name)
                } else {
                    format!("  {}", project.name)
                };

                ui.horizontal(|ui| {
                    let btn = ui.selectable_label(is_active, text);
                    if btn.clicked() {
                        selected_project = Some(project.path.clone());
                    }

                    if app.projects.len() > 1 {
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui.small_button("✕").on_hover_text("Remover projeto da lista").clicked() {
                                remove_project_idx = Some(idx);
                            }
                        });
                    }
                });
            }

            if let Some(idx) = remove_project_idx {
                app.projects.remove(idx);
                if !app.projects.iter().any(|p| p.path == app.current_dir) {
                    if let Some(first) = app.projects.first() {
                        app.current_dir = first.path.clone();
                    }
                }
                app.save_state_now();
            }

            if let Some(path) = selected_project {
                app.current_dir = path.clone();
                let (prov, modl) = detect_provider_and_model(&path);
                app.current_provider = prov;
                app.selected_model = modl;
                app.save_state_now();
                app.refresh_catalog();

                if let Some(convo) = app.current_conversation_mut() {
                    convo.messages.push(ChatMessage {
                        role: crate::state::MessageRole::System,
                        content: format!("Projeto ativo: {}", path.display()),
                        timestamp: Local::now().format("%H:%M:%S").to_string(),
                        tool_calls: Vec::new(),
                    });
                }
            }

            ui.add_space(14.0);
            ui.separator();
            ui.add_space(4.0);

            // Cabeçalho Conversas com filtro por projeto, exportar e "+"
            ui.horizontal(|ui| {
                ui.heading("Conversas");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let add_btn = ui.button(egui::RichText::new("+").strong().size(16.0));
                    if add_btn.on_hover_text("Criar nova conversa").clicked() {
                        app.new_conversation();
                    }

                    if ui.small_button("📥").on_hover_text("Exportar conversa ativa para Markdown").clicked() {
                        app.export_active_conversation();
                    }
                });
            });

            ui.horizontal(|ui| {
                if ui
                    .selectable_label(app.filter_convos_by_project, "Do Projeto")
                    .on_hover_text("Mostrar apenas conversas criadas no projeto ativo")
                    .clicked()
                {
                    app.filter_convos_by_project = !app.filter_convos_by_project;
                    app.save_state_now();
                }
                ui.add(
                    egui::TextEdit::singleline(&mut app.convo_search_query)
                        .hint_text("🔍 Buscar...")
                        .desired_width(120.0),
                );
            });
            ui.add_space(4.0);

            let mut select_convo_idx: Option<usize> = None;
            let mut delete_convo_idx: Option<usize> = None;
            let mut start_rename_idx: Option<usize> = None;
            let mut commit_rename = false;

            let search_q = app.convo_search_query.trim().to_lowercase();

            egui::ScrollArea::vertical()
                .id_salt("conversations_scroll")
                .show(ui, |ui| {
                    let total = app.conversations.len();
                    for idx in (0..total).rev() {
                        let convo = &app.conversations[idx];

                        if app.filter_convos_by_project {
                            if let Some(ref p) = convo.project_path {
                                if p != &app.current_dir {
                                    continue;
                                }
                            }
                        }
                        if !search_q.is_empty()
                            && !convo.title.to_lowercase().contains(&search_q)
                            && !convo
                                .messages
                                .iter()
                                .any(|m| m.content.to_lowercase().contains(&search_q))
                        {
                            continue;
                        }

                        let is_active = idx == app.active_conversation_idx;

                        if app.renaming_convo_idx == Some(idx) {
                            ui.horizontal(|ui| {
                                let resp = ui.add(
                                    egui::TextEdit::singleline(&mut app.rename_convo_buf)
                                        .desired_width(145.0),
                                );
                                if resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                                    commit_rename = true;
                                }
                                if ui.small_button("✓").clicked() {
                                    commit_rename = true;
                                }
                            });
                            continue;
                        }

                        let title = &convo.title;
                        let label = if is_active {
                            format!("💬 ▶ {}", title)
                        } else {
                            format!("💬   {}", title)
                        };

                        ui.horizontal(|ui| {
                            let btn = ui.selectable_label(is_active, label);
                            if btn.clicked() {
                                select_convo_idx = Some(idx);
                            }

                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.small_button("🗑").on_hover_text("Excluir conversa").clicked() {
                                    delete_convo_idx = Some(idx);
                                }
                                if ui.small_button("✏").on_hover_text("Renomear conversa").clicked() {
                                    start_rename_idx = Some(idx);
                                }
                            });
                        });
                    }
                });

            if let Some(idx) = start_rename_idx {
                app.rename_convo_buf = app.conversations[idx].title.clone();
                app.renaming_convo_idx = Some(idx);
            }
            if commit_rename {
                if let Some(idx) = app.renaming_convo_idx.take() {
                    let trimmed = app.rename_convo_buf.trim().to_string();
                    if !trimmed.is_empty() {
                        if let Some(c) = app.conversations.get_mut(idx) {
                            c.title = trimmed;
                        }
                        app.save_state_now();
                    }
                }
            }
            if let Some(sel_idx) = select_convo_idx {
                app.active_conversation_idx = sel_idx;
                app.save_state_now();
            }
            if let Some(del_idx) = delete_convo_idx {
                app.delete_conversation(del_idx);
            }
        });
}
