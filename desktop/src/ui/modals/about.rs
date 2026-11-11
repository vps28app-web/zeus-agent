use eframe::egui;

use crate::app::ZeusApp;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    if !app.show_about {
        return;
    }

    egui::Window::new("Sobre o Zeus Desktop")
        .collapsible(false)
        .resizable(false)
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.heading("⚡ Zeus Desktop");
            ui.label("Interface nativa desenvolvida em Rust com egui/eframe.");
            ui.add_space(6.0);
            ui.label("Autor: Valdeir Pereira da Silva");
            ui.label("Versão: 0.1.0");
            ui.add_space(10.0);
            if ui.button("Fechar").clicked() {
                app.show_about = false;
            }
        });
}
