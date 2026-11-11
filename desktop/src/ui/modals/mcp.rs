use std::collections::HashMap;
use eframe::egui;

use crate::app::ZeusApp;
use crate::state::McpServerConfigEntry;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_mcp {
        return;
    }

    let mut servers: HashMap<String, McpServerConfigEntry> = app
        .catalog
        .as_ref()
        .map(|c| c.mcp.servers.clone())
        .unwrap_or_default();

    let mut changed = false;
    let mut trigger_cmd: Option<String> = None;

    egui::Window::new("🔌 Model Context Protocol (MCP)")
        .collapsible(false)
        .resizable(true)
        .default_size([640.0, 560.0])
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.heading("Gerenciador de Servidores MCP");
            ui.label(format!("Arquivo: {}", app.mcp_config_path().display()));
            ui.add_space(6.0);

            egui::ScrollArea::vertical()
                .id_salt("mcp_servers_scroll")
                .max_height(220.0)
                .show(ui, |ui| {
                    ui.group(|ui| {
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("Servidores Configurados").strong());
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.small_button("⚡ Testar (/mcp list)").clicked() {
                                    trigger_cmd = Some("/mcp list".to_string());
                                }
                                if ui.small_button("🔄 Recarregar").clicked() {
                                    trigger_cmd = Some("/mcp reload".to_string());
                                }
                            });
                        });
                        ui.add_space(4.0);

                        if servers.is_empty() {
                            ui.label("Nenhum servidor MCP configurado ainda.");
                        } else {
                            let mut names: Vec<String> = servers.keys().cloned().collect();
                            names.sort();
                            for name in names {
                                let mut remove_this = false;
                                if let Some(srv) = servers.get_mut(&name) {
                                    ui.horizontal(|ui| {
                                        let mut enabled = !srv.disabled;
                                        if ui.checkbox(&mut enabled, "").changed() {
                                            srv.disabled = !enabled;
                                            changed = true;
                                        }
                                        ui.label(
                                            egui::RichText::new(&name)
                                                .strong()
                                                .color(if srv.disabled {
                                                    egui::Color32::GRAY
                                                } else {
                                                    egui::Color32::from_rgb(130, 210, 255)
                                                }),
                                        );
                                        let summary = if let Some(url) = &srv.url {
                                            format!("SSE: {}", url)
                                        } else {
                                            format!(
                                                "{} {}",
                                                srv.command.as_deref().unwrap_or(""),
                                                srv.args.join(" ")
                                            )
                                        };
                                        ui.label(
                                            egui::RichText::new(summary)
                                                .monospace()
                                                .size(11.0)
                                                .color(egui::Color32::from_rgb(190, 200, 210)),
                                        );
                                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                            if ui.small_button("🗑").on_hover_text("Remover servidor").clicked() {
                                                remove_this = true;
                                            }
                                        });
                                    });
                                }
                                if remove_this {
                                    servers.remove(&name);
                                    changed = true;
                                }
                            }
                        }
                    });
                });

            ui.add_space(6.0);

            ui.group(|ui| {
                ui.label(egui::RichText::new("➕ Adicionar Novo Servidor MCP").strong());
                ui.add_space(4.0);

                egui::Grid::new("mcp_add_grid")
                    .num_columns(2)
                    .spacing([10.0, 6.0])
                    .show(ui, |ui| {
                        ui.label("Nome:");
                        ui.add(
                            egui::TextEdit::singleline(&mut app.mcp_new_name)
                                .hint_text("ex: filesystem, github")
                                .desired_width(340.0),
                        );
                        ui.end_row();

                        ui.label("Comando ou URL:");
                        ui.add(
                            egui::TextEdit::singleline(&mut app.mcp_new_cmd_or_url)
                                .hint_text("npx ou http://localhost:3000/sse")
                                .desired_width(340.0),
                        );
                        ui.end_row();

                        ui.label("Argumentos:");
                        ui.add(
                            egui::TextEdit::singleline(&mut app.mcp_new_args)
                                .hint_text("-y @modelcontextprotocol/server-filesystem .")
                                .desired_width(340.0),
                        );
                        ui.end_row();
                    });

                ui.add_space(4.0);
                if ui.button("💾 Salvar Servidor").clicked() {
                    let name = app.mcp_new_name.trim().to_string();
                    let cmd_or_url = app.mcp_new_cmd_or_url.trim().to_string();
                    if !name.is_empty() && !cmd_or_url.is_empty() {
                        let entry = if cmd_or_url.starts_with("http://") || cmd_or_url.starts_with("https://") {
                            McpServerConfigEntry {
                                url: Some(cmd_or_url),
                                ..Default::default()
                            }
                        } else {
                            let args: Vec<String> = app
                                .mcp_new_args
                                .split_whitespace()
                                .map(|s| s.to_string())
                                .collect();
                            McpServerConfigEntry {
                                command: Some(cmd_or_url),
                                args,
                                ..Default::default()
                            }
                        };
                        servers.insert(name, entry);
                        app.mcp_new_name.clear();
                        app.mcp_new_cmd_or_url.clear();
                        app.mcp_new_args.clear();
                        changed = true;
                    }
                }
            });

            ui.add_space(6.0);

            ui.group(|ui| {
                ui.label(egui::RichText::new("📦 Presets Rápidos (1 clique)").strong());
                ui.add_space(4.0);

                let presets = [
                    ("filesystem", "npx", vec!["-y", "@modelcontextprotocol/server-filesystem", "."], "Arquivos locais"),
                    ("memory", "npx", vec!["-y", "@modelcontextprotocol/server-memory"], "Memória em grafo"),
                    ("github", "npx", vec!["-y", "@modelcontextprotocol/server-github"], "Repositórios GitHub"),
                    ("sqlite", "npx", vec!["-y", "@modelcontextprotocol/server-sqlite"], "Consultas SQLite"),
                    ("brave-search", "npx", vec!["-y", "@modelcontextprotocol/server-brave-search"], "Busca Brave"),
                ];

                for (name, cmd, args, desc) in presets {
                    ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new(format!("• {}", name))
                                .strong()
                                .color(egui::Color32::from_rgb(130, 210, 255)),
                        );
                        ui.label(
                            egui::RichText::new(desc)
                                .size(11.5)
                                .color(egui::Color32::from_rgb(180, 190, 200)),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            let exists = servers.contains_key(name);
                            let btn_lbl = if exists { "Reinstalar" } else { "Adicionar" };
                            if ui.small_button(btn_lbl).clicked() {
                                servers.insert(
                                    name.to_string(),
                                    McpServerConfigEntry {
                                        command: Some(cmd.to_string()),
                                        args: args.iter().map(|s| s.to_string()).collect(),
                                        ..Default::default()
                                    },
                                );
                                changed = true;
                            }
                        });
                    });
                }
            });

            ui.add_space(8.0);
            ui.separator();
            if ui.button("Fechar").clicked() {
                app.show_mcp = false;
            }
        });

    if changed {
        app.save_mcp_servers_map(&servers);
    }
    if let Some(cmd) = trigger_cmd {
        app.show_mcp = false;
        app.send_raw_command(cmd);
    }
}
