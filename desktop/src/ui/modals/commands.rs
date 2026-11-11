use eframe::egui;

use crate::app::ZeusApp;
use crate::data::commands::get_all_commands;
use crate::state::DynamicCommand;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_commands {
        return;
    }

    let mut insert_cmd = None;
    let dynamic_cmds: Vec<DynamicCommand> = if let Some(cat) = &app.catalog {
        if !cat.commands.is_empty() {
            cat.commands.clone()
        } else {
            get_all_commands()
                .iter()
                .map(|c| DynamicCommand {
                    cmd: c.cmd.to_string(),
                    desc: c.desc.to_string(),
                    category: c.category.to_string(),
                })
                .collect()
        }
    } else {
        get_all_commands()
            .iter()
            .map(|c| DynamicCommand {
                cmd: c.cmd.to_string(),
                desc: c.desc.to_string(),
                category: c.category.to_string(),
            })
            .collect()
    };

    egui::Window::new("📜 Comandos do Zeus")
        .collapsible(false)
        .resizable(true)
        .default_size([600.0, 480.0])
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new("🔍 Buscar:").strong());
                ui.text_edit_singleline(&mut app.commands_filter);
                if !app.commands_filter.is_empty() && ui.button("✖").clicked() {
                    app.commands_filter.clear();
                }
            });

            ui.add_space(6.0);
            ui.separator();

            let filter = app.commands_filter.trim().to_lowercase();

            egui::ScrollArea::vertical()
                .id_salt("commands_scroll_area")
                .max_height(380.0)
                .show(ui, |ui| {
                    let mut current_cat = String::new();
                    for item in &dynamic_cmds {
                        if !filter.is_empty()
                            && !item.cmd.to_lowercase().contains(&filter)
                            && !item.desc.to_lowercase().contains(&filter)
                            && !item.category.to_lowercase().contains(&filter)
                        {
                            continue;
                        }

                        if item.category != current_cat {
                            current_cat = item.category.clone();
                            ui.add_space(8.0);
                            ui.label(
                                egui::RichText::new(&current_cat)
                                    .strong()
                                    .color(egui::Color32::from_rgb(100, 200, 255)),
                            );
                            ui.separator();
                        }

                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new(&item.cmd)
                                    .strong()
                                    .color(egui::Color32::from_rgb(255, 215, 0)),
                            );
                            ui.add_space(6.0);
                            ui.label(&item.desc);

                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.small_button("Usar").on_hover_text("Inserir comando no campo de texto").clicked() {
                                    insert_cmd = Some(item.cmd.split_whitespace().next().unwrap_or(&item.cmd).to_string());
                                }
                            });
                        });
                        ui.add_space(2.0);
                    }
                });

            ui.add_space(10.0);
            ui.separator();
            if ui.button("Fechar").clicked() {
                app.show_commands = false;
            }
        });

    if let Some(c) = insert_cmd {
        app.input_text = format!("{} ", c);
        app.show_commands = false;
    }
}
