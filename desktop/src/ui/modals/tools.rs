use eframe::egui;

use crate::app::ZeusApp;
use crate::data::tools::get_all_tools;
use crate::state::DynamicTool;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_tools {
        return;
    }

    let mut tools: Vec<DynamicTool> = if let Some(cat) = &app.catalog {
        if !cat.tools.is_empty() {
            cat.tools.clone()
        } else {
            get_all_tools()
                .iter()
                .map(|t| DynamicTool {
                    name: t.name.to_string(),
                    desc: t.desc.to_string(),
                    category: t.category.to_string(),
                    tags: Vec::new(),
                })
                .collect()
        }
    } else {
        get_all_tools()
            .iter()
            .map(|t| DynamicTool {
                name: t.name.to_string(),
                desc: t.desc.to_string(),
                category: t.category.to_string(),
                tags: Vec::new(),
            })
            .collect()
    };

    tools.sort_by(|a, b| a.category.cmp(&b.category).then_with(|| a.name.cmp(&b.name)));

    egui::Window::new("🔧 Ferramentas do Zeus (Tools)")
        .collapsible(false)
        .resizable(true)
        .default_size([640.0, 520.0])
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new("🔍 Filtrar Ferramentas:").strong());
                ui.text_edit_singleline(&mut app.tools_filter);
                if !app.tools_filter.is_empty() && ui.button("✖").clicked() {
                    app.tools_filter.clear();
                }
            });

            ui.add_space(4.0);
            ui.label(
                egui::RichText::new(format!(
                    "Ferramentas registradas no harness ({} disponíveis):",
                    tools.len()
                ))
                .size(11.5)
                .color(egui::Color32::from_rgb(180, 190, 205)),
            );
            ui.separator();

            let filter = app.tools_filter.trim().to_lowercase();

            egui::ScrollArea::vertical()
                .id_salt("tools_scroll_area")
                .max_height(400.0)
                .show(ui, |ui| {
                    let mut current_cat = String::new();
                    for item in &tools {
                        if !filter.is_empty()
                            && !item.name.to_lowercase().contains(&filter)
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
                                    .color(egui::Color32::from_rgb(130, 210, 255)),
                            );
                            ui.separator();
                        }

                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new(&item.name)
                                    .strong()
                                    .color(egui::Color32::from_rgb(140, 240, 160)),
                            );
                            ui.add_space(4.0);
                            ui.label(
                                egui::RichText::new(&item.desc)
                                    .size(12.0)
                                    .color(egui::Color32::from_rgb(220, 220, 225)),
                            );
                        });
                        ui.add_space(2.0);
                    }
                });

            ui.add_space(10.0);
            ui.separator();
            if ui.button("Fechar").clicked() {
                app.show_tools = false;
            }
        });
}
