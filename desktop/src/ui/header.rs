use eframe::egui;

use crate::app::ZeusApp;

pub fn render_top_bar(app: &mut ZeusApp, ui: &mut egui::Ui) {
    egui::Panel::top("top_panel").show(ui, |ui| {
        ui.add_space(4.0);
        ui.horizontal(|ui| {
            // Menu Hamburger
            ui.menu_button("☰", |ui| {
                if ui.button("⚙️ Configurações").clicked() {
                    app.show_settings = true;
                    ui.close();
                }
                if ui.button("📊 Painel Zeus (Métricas, Agenda & Memória)").clicked() {
                    app.show_ecosystem = true;
                    app.refresh_catalog();
                    ui.close();
                }
                ui.separator();
                if ui.button("📜 Comandos").clicked() {
                    app.show_commands = true;
                    ui.close();
                }
                if ui.button("🔧 Ferramentas").clicked() {
                    app.show_tools = true;
                    ui.close();
                }
                if ui.button("🔌 MCP").clicked() {
                    app.show_mcp = true;
                    ui.close();
                }
                ui.separator();
                if ui.button("ℹ️ Sobre").clicked() {
                    app.show_about = true;
                    ui.close();
                }
            });

            ui.add_space(4.0);
            ui.heading("⚡ Zeus Desktop");

            // Direita: indicador de status e badge de tokens/custo reais
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let (status_color, icon) = if app.is_running {
                    (egui::Color32::from_rgb(243, 156, 18), "⏳")
                } else {
                    (egui::Color32::from_rgb(46, 204, 113), "●")
                };

                ui.label(
                    egui::RichText::new(format!("{} {}", icon, app.status_text))
                        .color(status_color)
                        .strong(),
                );

                ui.add_space(8.0);

                let (total_tokens, is_real, in_tok, out_tok, calls, cost_usd, latency_ms) =
                    if let Some(convo) = app.current_conversation() {
                        (
                            convo.total_tokens(),
                            convo.has_real_metrics(),
                            convo.actual_input_tokens,
                            convo.actual_output_tokens,
                            convo.llm_calls,
                            convo.total_cost_usd,
                            convo.total_latency_ms,
                        )
                    } else {
                        (0, false, 0, 0, 0, 0.0, 0.0)
                    };

                let prefix = if is_real { "" } else { "~" };
                let tokens_formatted = if total_tokens >= 10_000 {
                    format!("{}{:.1}k tokens", prefix, total_tokens as f64 / 1000.0)
                } else {
                    format!("{}{} tokens", prefix, total_tokens)
                };
                let badge_text = if is_real && cost_usd > 0.0 {
                    format!("🧠 {} • ${:.4}", tokens_formatted, cost_usd)
                } else {
                    format!("🧠 {}", tokens_formatted)
                };

                let hover = if is_real {
                    format!(
                        "Métricas Reais da Sessão:\n• Entrada: {} tokens\n• Saída: {} tokens\n• Chamadas LLM: {}\n• Latência acumulada: {:.0} ms\n• Custo estimado: ${:.6}",
                        in_tok, out_tok, calls, latency_ms, cost_usd
                    )
                } else {
                    format!(
                        "Estimativa de Contexto: ~{} tokens acumulados nesta conversa.",
                        total_tokens
                    )
                };

                let tokens_label = egui::RichText::new(badge_text)
                    .color(egui::Color32::from_rgb(140, 200, 255))
                    .strong()
                    .size(11.5);

                ui.label(tokens_label).on_hover_text(hover);
            });
        });
        ui.add_space(4.0);
    });
}

pub fn render_bottom_bar(app: &mut ZeusApp, ui: &mut egui::Ui) {
    egui::Panel::bottom("bottom_status_panel").show(ui, |ui| {
        ui.horizontal(|ui| {
            let project_name = app
                .projects
                .iter()
                .find(|p| p.path == app.current_dir)
                .map(|p| p.name.clone())
                .unwrap_or_else(|| {
                    app.current_dir
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| "Projeto".to_string())
                });

            ui.label(egui::RichText::new("📂").size(11.0));
            ui.label(
                egui::RichText::new("Projeto:")
                    .size(11.0)
                    .color(egui::Color32::from_rgb(160, 170, 180)),
            );
            ui.label(
                egui::RichText::new(&project_name)
                    .strong()
                    .size(11.0)
                    .color(egui::Color32::WHITE),
            );
            ui.label(
                egui::RichText::new(" • ")
                    .size(11.0)
                    .color(egui::Color32::from_rgb(100, 110, 120)),
            );
            ui.label(
                egui::RichText::new("Pasta:")
                    .size(11.0)
                    .color(egui::Color32::from_rgb(160, 170, 180)),
            );
            ui.label(
                egui::RichText::new(app.current_dir.display().to_string())
                    .strong()
                    .size(11.0)
                    .color(egui::Color32::from_rgb(200, 215, 230)),
            );

            if let Some(toast) = app.active_toast() {
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(
                        egui::RichText::new(format!("✅ {}", toast))
                            .size(11.0)
                            .strong()
                            .color(egui::Color32::from_rgb(120, 235, 160)),
                    );
                });
            }
        });
    });
}
