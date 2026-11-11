use std::path::PathBuf;
use eframe::egui;

use crate::app::ZeusApp;
use crate::config::DesktopConfig;
use crate::data::providers::{all_providers, get_models_for_provider, provider_display_name};
use crate::state::ZeusMode;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_settings {
        return;
    }

    app.ensure_env_loaded();
    let mut trigger_auth_google = false;
    let mut save_env_clicked = false;

    egui::Window::new("⚙️ Configurações")
        .collapsible(false)
        .resizable(true)
        .default_size([560.0, 580.0])
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            egui::ScrollArea::vertical()
                .id_salt("settings_main_scroll")
                .max_height(500.0)
                .show(ui, |ui| {
                    ui.heading("Preferências do Zeus");
                    ui.add_space(6.0);

                    // Seção 1: Provedor e Modelo
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("🌐 Provedor de IA e Modelo").strong());
                        ui.add_space(4.0);

                        let dynamic_providers: Vec<(String, String)> = if let Some(cat) = &app.catalog {
                            if !cat.providers.is_empty() {
                                cat.providers.iter().map(|p| (p.id.clone(), p.name.clone())).collect()
                            } else {
                                all_providers().iter().map(|(id, name)| (id.to_string(), name.to_string())).collect()
                            }
                        } else {
                            all_providers().iter().map(|(id, name)| (id.to_string(), name.to_string())).collect()
                        };

                        let dynamic_models: Vec<(String, String)> = if let Some(cat) = &app.catalog {
                            if let Some(p) = cat.providers.iter().find(|p| p.id == app.current_provider) {
                                p.models.iter().map(|m| (m.id.clone(), m.label.clone())).collect()
                            } else {
                                get_models_for_provider(&app.current_provider)
                                    .into_iter()
                                    .map(|(id, lbl)| (id.to_string(), lbl.to_string()))
                                    .collect()
                            }
                        } else {
                            get_models_for_provider(&app.current_provider)
                                .into_iter()
                                .map(|(id, lbl)| (id.to_string(), lbl.to_string()))
                                .collect()
                        };

                        let active_provider_name = dynamic_providers
                            .iter()
                            .find(|(id, _)| id == &app.current_provider)
                            .map(|(_, n)| n.as_str())
                            .unwrap_or_else(|| provider_display_name(&app.current_provider));

                        egui::Grid::new("settings_grid_provider")
                            .num_columns(2)
                            .spacing([12.0, 8.0])
                            .show(ui, |ui| {
                                ui.label("Provedor:");
                                egui::ComboBox::from_id_salt("settings_provider_combo")
                                    .selected_text(active_provider_name)
                                    .width(280.0)
                                    .show_ui(ui, |ui| {
                                        for (p_id, p_name) in &dynamic_providers {
                                            if ui.selectable_label(&app.current_provider == p_id, p_name).clicked() {
                                                app.current_provider = p_id.clone();
                                                if let Some(cat) = &app.catalog {
                                                    if let Some(p) = cat.providers.iter().find(|p| &p.id == p_id) {
                                                        if let Some(first_m) = p.models.first() {
                                                            app.selected_model = first_m.id.clone();
                                                        }
                                                    }
                                                } else if let Some((first_m, _)) = get_models_for_provider(p_id).first() {
                                                    app.selected_model = first_m.to_string();
                                                }
                                                app.mark_dirty();
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Modelo ativo:");
                                egui::ComboBox::from_id_salt("settings_model_combo")
                                    .selected_text(&app.selected_model)
                                    .width(280.0)
                                    .show_ui(ui, |ui| {
                                        for (m_id, m_label) in &dynamic_models {
                                            let text = format!("{} ({})", m_id, m_label);
                                            if ui.selectable_label(&app.selected_model == m_id, text).clicked() {
                                                app.selected_model = m_id.clone();
                                                app.mark_dirty();
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Modelo customizado:");
                                if ui.text_edit_singleline(&mut app.selected_model).changed() {
                                    app.mark_dirty();
                                }
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
                                    .selected_text(app.selected_mode.label())
                                    .width(280.0)
                                    .show_ui(ui, |ui| {
                                        let all_modes = [
                                            ZeusMode::Sandbox,
                                            ZeusMode::Terminal,
                                            ZeusMode::Auto,
                                            ZeusMode::DryRun,
                                            ZeusMode::ReadOnly,
                                        ];
                                        for m in all_modes {
                                            if ui.selectable_label(app.selected_mode == m, m.label()).clicked() {
                                                app.selected_mode = m;
                                                app.mark_dirty();
                                            }
                                        }
                                    });
                                ui.end_row();

                                ui.label("Esforço de Raciocínio:");
                                egui::ComboBox::from_id_salt("settings_reasoning_combo")
                                    .selected_text(&app.selected_reasoning)
                                    .width(280.0)
                                    .show_ui(ui, |ui| {
                                        for opt in ["Mínimo", "Baixo", "Médio", "Alto"] {
                                            if ui.selectable_label(app.selected_reasoning == opt, opt).clicked() {
                                                app.selected_reasoning = opt.to_string();
                                                app.mark_dirty();
                                            }
                                        }
                                    });
                                ui.end_row();
                            });
                    });

                    ui.add_space(6.0);

                    // Seção 3: Comportamento e Exportação
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("⚡ Comportamento e Exportação").strong());
                        ui.add_space(4.0);
                        if ui.checkbox(&mut app.session_context, "Manter histórico de contexto entre comandos na sessão").changed() {
                            app.mark_dirty();
                        }
                        if ui.checkbox(&mut app.auto_scroll, "Rolar automaticamente para novas mensagens").changed() {
                            app.mark_dirty();
                        }

                        let mut export_str = app
                            .export_dir
                            .clone()
                            .unwrap_or_else(DesktopConfig::default_export_dir)
                            .display()
                            .to_string();
                        ui.horizontal(|ui| {
                            ui.label("Pasta de exportação:");
                            if ui.text_edit_singleline(&mut export_str).changed() {
                                app.export_dir = if export_str.trim().is_empty() {
                                    None
                                } else {
                                    Some(PathBuf::from(export_str.trim()))
                                };
                                app.mark_dirty();
                            }
                            if ui.button("📂").on_hover_text("Escolher pasta").clicked() {
                                if let Some(p) = ZeusApp::pick_folder() {
                                    app.export_dir = Some(p);
                                    app.mark_dirty();
                                }
                            }
                        });
                    });

                    ui.add_space(6.0);

                    // Seção 4: Ambiente e Python
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("🐍 Ambiente e Interpretador").strong());
                        ui.add_space(4.0);

                        let mut custom_py = app.custom_python_path.clone().unwrap_or_default();
                        ui.horizontal(|ui| {
                            ui.label("Python custom:");
                            if ui.text_edit_singleline(&mut custom_py).changed() {
                                app.custom_python_path = if custom_py.trim().is_empty() {
                                    None
                                } else {
                                    Some(custom_py.trim().to_string())
                                };
                                app.mark_dirty();
                            }
                        });

                        ui.label(
                            egui::RichText::new(format!("Pasta ativa: {}", app.current_dir.display()))
                                .size(11.0)
                                .color(egui::Color32::from_rgb(180, 190, 205)),
                        );
                    });

                    ui.add_space(6.0);

                    // Seção 5: Chaves de API e ~/.zeus/.env
                    ui.group(|ui| {
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("🔑 Chaves de API (~/.zeus/.env)").strong());
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                let eye = if app.show_env_secrets { "🙈 Ocultar" } else { "👁 Mostrar" };
                                if ui.small_button(eye).clicked() {
                                    app.show_env_secrets = !app.show_env_secrets;
                                }
                                if ui.small_button("🔐 Auth Google").on_hover_text("Executar /auth google").clicked() {
                                    trigger_auth_google = true;
                                }
                            });
                        });
                        ui.add_space(4.0);

                        let mut remove_idx: Option<usize> = None;
                        for (idx, (k, v)) in app.env_entries.iter_mut().enumerate() {
                            ui.horizontal(|ui| {
                                ui.add(egui::TextEdit::singleline(k).desired_width(180.0));
                                let is_secret = !app.show_env_secrets
                                    && (k.contains("KEY") || k.contains("TOKEN") || k.contains("SECRET"));
                                ui.add(
                                    egui::TextEdit::singleline(v)
                                        .password(is_secret)
                                        .desired_width(230.0),
                                );
                                if ui.small_button("🗑").clicked() {
                                    remove_idx = Some(idx);
                                }
                            });
                        }
                        if let Some(idx) = remove_idx {
                            app.env_entries.remove(idx);
                        }

                        ui.add_space(4.0);
                        ui.horizontal(|ui| {
                            ui.add(
                                egui::TextEdit::singleline(&mut app.new_env_key)
                                    .hint_text("NOME_DA_CHAVE (ex: OPENAI_API_KEY)")
                                    .desired_width(200.0),
                            );
                            ui.add(
                                egui::TextEdit::singleline(&mut app.new_env_val)
                                    .password(!app.show_env_secrets)
                                    .hint_text("valor")
                                    .desired_width(190.0),
                            );
                            if ui.button("➕ Adicionar").clicked() {
                                let k = app.new_env_key.trim().to_string();
                                let v = app.new_env_val.trim().to_string();
                                if !k.is_empty() {
                                    if let Some(existing) = app.env_entries.iter_mut().find(|(ek, _)| ek == &k) {
                                        existing.1 = v;
                                    } else {
                                        app.env_entries.push((k, v));
                                    }
                                    app.new_env_key.clear();
                                    app.new_env_val.clear();
                                }
                            }
                        });

                        ui.add_space(4.0);
                        if ui.button("💾 Salvar ~/.zeus/.env").clicked() {
                            save_env_clicked = true;
                        }
                    });
                });

            ui.add_space(8.0);
            ui.separator();
            ui.horizontal(|ui| {
                if ui.button("OK / Concluir").clicked() {
                    app.show_settings = false;
                    app.save_state_now();
                }
            });
        });

    if save_env_clicked {
        app.save_env_entries();
    }
    if trigger_auth_google {
        app.show_settings = false;
        app.send_raw_command("/auth google".to_string());
    }
}
