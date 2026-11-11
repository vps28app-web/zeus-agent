use eframe::egui;

use crate::app::ZeusApp;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_ecosystem {
        return;
    }

    let mut trigger_cmd: Option<String> = None;
    let mut refresh = false;

    egui::Window::new("📊 Painel do Ecossistema Zeus")
        .collapsible(false)
        .resizable(true)
        .default_size([680.0, 520.0])
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.selectable_value(&mut app.ecosystem_tab, 0, "📈 Métricas & Sessões");
                ui.selectable_value(&mut app.ecosystem_tab, 1, "⏰ Tarefas Agendadas");
                ui.selectable_value(&mut app.ecosystem_tab, 2, "🧠 Memória Persistente");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("🔄 Atualizar").clicked() {
                        refresh = true;
                    }
                });
            });

            ui.separator();

            ui.horizontal(|ui| {
                ui.label("🔍 Filtrar:");
                ui.text_edit_singleline(&mut app.ecosystem_filter);
                if !app.ecosystem_filter.is_empty() && ui.button("✖").clicked() {
                    app.ecosystem_filter.clear();
                }
            });

            ui.add_space(6.0);
            let filter = app.ecosystem_filter.trim().to_lowercase();

            egui::ScrollArea::vertical()
                .id_salt("ecosystem_scroll")
                .max_height(380.0)
                .show(ui, |ui| {
                    let Some(cat) = app.catalog.as_ref() else {
                        ui.label("Carregando dados do ecossistema Zeus...");
                        return;
                    };

                    match app.ecosystem_tab {
                        0 => {
                            if let Some(convo) = app.current_conversation() {
                                ui.group(|ui| {
                                    ui.label(egui::RichText::new("Conversa Ativa").strong());
                                    ui.label(format!(
                                        "Session ID: {} | Chamadas LLM: {} | Entrada: {} | Saída: {} | Custo: ${:.6}",
                                        convo.session_id,
                                        convo.llm_calls,
                                        convo.actual_input_tokens,
                                        convo.actual_output_tokens,
                                        convo.total_cost_usd
                                    ));
                                });
                                ui.add_space(8.0);
                            }

                            ui.label(egui::RichText::new("Sessões Recentes (zeus.db)").strong());
                            ui.add_space(4.0);
                            if cat.ecosystem.recent_sessions.is_empty() {
                                ui.label("Nenhuma sessão registrada no banco ainda.");
                            } else {
                                for s in &cat.ecosystem.recent_sessions {
                                    if !filter.is_empty()
                                        && !s.session_id.to_lowercase().contains(&filter)
                                    {
                                        continue;
                                    }
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(&s.session_id)
                                                .monospace()
                                                .strong()
                                                .color(egui::Color32::from_rgb(130, 200, 255)),
                                        );
                                        ui.label(format!(
                                            "In: {} | Out: {} | Regs: {}",
                                            s.input_tokens, s.output_tokens, s.records
                                        ));
                                    });
                                }
                            }
                        }
                        1 => {
                            ui.label(egui::RichText::new("Tarefas Cron Agendadas").strong());
                            ui.add_space(4.0);
                            if cat.ecosystem.scheduled_tasks.is_empty() {
                                ui.label("Nenhuma tarefa agendada no momento.");
                            } else {
                                for task in &cat.ecosystem.scheduled_tasks {
                                    if !filter.is_empty()
                                        && !task.command.to_lowercase().contains(&filter)
                                        && !task.task_id.to_lowercase().contains(&filter)
                                    {
                                        continue;
                                    }
                                    ui.group(|ui| {
                                        ui.horizontal(|ui| {
                                            let badge = if task.enabled != 0 { "🟢" } else { "⏸️" };
                                            ui.label(egui::RichText::new(format!("{} {}", badge, task.task_id)).strong());
                                            ui.label(egui::RichText::new(&task.schedule).monospace());
                                        });
                                        ui.label(format!("Comando: {}", task.command));
                                        if let Some(desc) = &task.description {
                                            ui.label(
                                                egui::RichText::new(desc)
                                                    .size(11.5)
                                                    .color(egui::Color32::GRAY),
                                            );
                                        }
                                        if let Some(next_run) = &task.next_run {
                                            ui.label(
                                                egui::RichText::new(format!("Próxima execução: {}", next_run))
                                                    .size(11.0),
                                            );
                                        }
                                    });
                                    ui.add_space(4.0);
                                }
                            }
                        }
                        _ => {
                            ui.horizontal(|ui| {
                                ui.label(egui::RichText::new("Chaves de Memória Persistente").strong());
                                if ui.small_button("🧠 Ver /brain").clicked() {
                                    trigger_cmd = Some("/brain".to_string());
                                }
                            });
                            ui.add_space(4.0);
                            if cat.ecosystem.memories.is_empty() {
                                ui.label("Nenhuma memória persistida encontrada.");
                            } else {
                                for mem in &cat.ecosystem.memories {
                                    if !filter.is_empty()
                                        && !mem.key.to_lowercase().contains(&filter)
                                        && !mem.notes.iter().any(|n| n.to_lowercase().contains(&filter))
                                    {
                                        continue;
                                    }
                                    ui.group(|ui| {
                                        ui.label(
                                            egui::RichText::new(&mem.key)
                                                .strong()
                                                .color(egui::Color32::from_rgb(140, 240, 160)),
                                        );
                                        for note in &mem.notes {
                                            ui.label(format!("• {}", note));
                                        }
                                    });
                                    ui.add_space(4.0);
                                }
                            }
                        }
                    }
                });

            ui.add_space(8.0);
            ui.separator();
            if ui.button("Fechar").clicked() {
                app.show_ecosystem = false;
            }
        });

    if refresh {
        app.refresh_catalog();
    }
    if let Some(cmd) = trigger_cmd {
        app.show_ecosystem = false;
        app.send_raw_command(cmd);
    }
}
