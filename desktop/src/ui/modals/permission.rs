use eframe::egui;

use crate::app::ZeusApp;

pub fn render(app: &mut ZeusApp, ctx: &egui::Context) {
    let Some(prompt) = app.pending_permission.as_mut() else {
        return;
    };

    let title = match prompt.kind.as_str() {
        "file_permission" => "🔐 Permissão de Arquivo",
        "terminal_confirm" => "⚡ Confirmação de Comando",
        "plan_confirm" => "📋 Executar Plano",
        "sudo_password" => "🔑 Senha Sudo Necessária",
        "ssh_user" => "👤 Usuário SSH Necessário",
        "ssh_password" => "🔑 Senha SSH Necessária",
        _ => "🛡️ Confirmação Necessária",
    };

    let mut chosen_decision: Option<String> = None;
    let mut chosen_secret: Option<String> = None;

    egui::Window::new(title)
        .collapsible(false)
        .resizable(false)
        .default_width(460.0)
        .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
        .show(ctx, |ui| {
            ui.label(
                egui::RichText::new(&prompt.message)
                    .size(13.0)
                    .color(egui::Color32::from_rgb(235, 240, 245)),
            );

            ui.add_space(8.0);

            let needs_input =
                prompt.secret || matches!(prompt.kind.as_str(), "ssh_user" | "ssh_password" | "sudo_password");
            if needs_input {
                ui.horizontal(|ui| {
                    ui.label(if prompt.secret { "Senha:" } else { "Valor:" });
                    let resp = ui.add(
                        egui::TextEdit::singleline(&mut prompt.input_secret)
                            .password(prompt.secret)
                            .desired_width(280.0),
                    );
                    if resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                        chosen_decision = Some("once".to_string());
                        chosen_secret = Some(prompt.input_secret.clone());
                    }
                });
                ui.add_space(8.0);
            }

            ui.horizontal(|ui| {
                for opt in &prompt.options {
                    let label = match opt.as_str() {
                        "once" => "✅ Permitir uma vez",
                        "always" => "✅ Permitir nesta sessão",
                        "persist" => "💾 Permitir sempre",
                        "deny" => "❌ Negar",
                        other => other,
                    };
                    if ui.button(label).clicked() {
                        chosen_decision = Some(opt.clone());
                        if needs_input && opt != "deny" {
                            chosen_secret = Some(prompt.input_secret.clone());
                        }
                    }
                }
            });
        });

    if let Some(decision) = chosen_decision {
        app.send_permission_decision(&decision, chosen_secret);
    }
}
