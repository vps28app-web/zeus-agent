use eframe::egui;

use crate::app::ZeusApp;
use crate::data::providers::{get_models_for_provider, provider_display_name};
use crate::state::{MessageRole, ZeusMode};

#[derive(Debug, PartialEq)]
enum ContentSegment {
    MarkdownBlock(String),
    CodeBlock { lang: String, code: String, closed: bool },
}

fn parse_content_segments(content: &str) -> Vec<ContentSegment> {
    let mut segments = Vec::new();
    let mut remainder = content;

    while let Some(start_idx) = remainder.find("```") {
        let (before, code_and_rest) = remainder.split_at(start_idx);
        if !before.trim().is_empty() {
            segments.push(ContentSegment::MarkdownBlock(before.to_string()));
        }
        let code_part = &code_and_rest[3..];
        if let Some(end_idx) = code_part.find("```") {
            let (code_with_header, after) = code_part.split_at(end_idx);
            let first_newline = code_with_header.find('\n');
            let (lang, code) = if let Some(nl_pos) = first_newline {
                let first_line = code_with_header[..nl_pos].trim();
                let actual_code = &code_with_header[nl_pos + 1..];
                let lang_str = if first_line.is_empty() || first_line.contains(' ') {
                    "código".to_string()
                } else {
                    first_line.to_string()
                };
                (lang_str, actual_code.trim_end_matches('\n').to_string())
            } else {
                ("código".to_string(), code_with_header.to_string())
            };

            segments.push(ContentSegment::CodeBlock {
                lang,
                code,
                closed: true,
            });
            remainder = &after[3..];
        } else {
            // Bloco de código ainda aberto durante streaming!
            let first_newline = code_part.find('\n');
            let (lang, code) = if let Some(nl_pos) = first_newline {
                let first_line = code_part[..nl_pos].trim();
                let actual_code = &code_part[nl_pos + 1..];
                let lang_str = if first_line.is_empty() || first_line.contains(' ') {
                    "código".to_string()
                } else {
                    first_line.to_string()
                };
                (lang_str, actual_code.to_string())
            } else {
                ("código".to_string(), code_part.to_string())
            };
            segments.push(ContentSegment::CodeBlock {
                lang,
                code,
                closed: false,
            });
            remainder = "";
            break;
        }
    }

    if !remainder.trim().is_empty() {
        segments.push(ContentSegment::MarkdownBlock(remainder.to_string()));
    }

    segments
}

fn render_inline_markdown(ui: &mut egui::Ui, line: &str, base_color: egui::Color32, base_size: f32) {
    ui.horizontal_wrapped(|ui| {
        ui.spacing_mut().item_spacing.x = 0.0;
        let mut s = line;
        while !s.is_empty() {
            // Links [text](url)
            if s.starts_with('[') {
                if let Some(close_bracket) = s.find("](") {
                    let after_bracket = &s[close_bracket + 2..];
                    if let Some(close_paren) = after_bracket.find(')') {
                        let label = &s[1..close_bracket];
                        let url = &after_bracket[..close_paren];
                        if !label.is_empty() && (url.starts_with("http://") || url.starts_with("https://") || url.starts_with("file://")) {
                            ui.hyperlink_to(
                                egui::RichText::new(label)
                                    .size(base_size)
                                    .color(egui::Color32::from_rgb(110, 190, 255)),
                                url,
                            );
                            s = &after_bracket[close_paren + 1..];
                            continue;
                        }
                    }
                }
            }
            // Inline code `...`
            if s.starts_with('`') {
                if let Some(end) = s[1..].find('`') {
                    let code = &s[1..1 + end];
                    ui.label(
                        egui::RichText::new(code)
                            .monospace()
                            .size(base_size - 0.5)
                            .background_color(egui::Color32::from_rgb(28, 34, 46))
                            .color(egui::Color32::from_rgb(160, 225, 255)),
                    );
                    s = &s[2 + end..];
                    continue;
                }
            }
            // Negrito **...**
            if s.starts_with("**") {
                if let Some(end) = s[2..].find("**") {
                    let bold = &s[2..2 + end];
                    ui.label(
                        egui::RichText::new(bold)
                            .strong()
                            .size(base_size)
                            .color(base_color),
                    );
                    s = &s[4 + end..];
                    continue;
                }
            }
            // Itálico *...*
            if s.starts_with('*') && !s.starts_with("**") {
                if let Some(end) = s[1..].find('*') {
                    if end > 0 {
                        let italic = &s[1..1 + end];
                        ui.label(
                            egui::RichText::new(italic)
                                .italics()
                                .size(base_size)
                                .color(base_color),
                        );
                        s = &s[2 + end..];
                        continue;
                    }
                }
            }

            // Avança até o próximo marcador especial
            let next_special = s[1..]
                .find(['`', '*', '['])
                .map(|p| p + 1)
                .unwrap_or(s.len());
            let chunk = &s[..next_special];
            ui.label(egui::RichText::new(chunk).size(base_size).color(base_color));
            s = &s[next_special..];
        }
    });
}

fn render_markdown_block(ui: &mut egui::Ui, md: &str) {
    for raw_line in md.lines() {
        let trimmed_start = raw_line.trim_start();
        if trimmed_start.is_empty() {
            ui.add_space(4.0);
            continue;
        }
        if let Some(h3) = trimmed_start.strip_prefix("### ") {
            ui.add_space(2.0);
            render_inline_markdown(ui, h3, egui::Color32::from_rgb(160, 215, 255), 14.5);
        } else if let Some(h2) = trimmed_start.strip_prefix("## ") {
            ui.add_space(3.0);
            render_inline_markdown(ui, h2, egui::Color32::from_rgb(130, 200, 255), 16.0);
        } else if let Some(h1) = trimmed_start.strip_prefix("# ") {
            ui.add_space(4.0);
            render_inline_markdown(ui, h1, egui::Color32::from_rgb(110, 190, 255), 17.5);
        } else if let Some(quote) = trimmed_start.strip_prefix("> ") {
            egui::Frame::new()
                .fill(egui::Color32::from_rgb(20, 25, 34))
                .inner_margin(6i8)
                .show(ui, |ui| {
                    render_inline_markdown(ui, quote, egui::Color32::from_rgb(190, 205, 220), 12.5);
                });
        } else if let Some(item) = trimmed_start.strip_prefix("- ").or_else(|| trimmed_start.strip_prefix("* ")) {
            ui.horizontal(|ui| {
                ui.add_space(6.0);
                ui.label(egui::RichText::new("•").color(egui::Color32::from_rgb(120, 200, 255)));
                render_inline_markdown(ui, item, egui::Color32::WHITE, 13.0);
            });
        } else {
            render_inline_markdown(ui, raw_line, egui::Color32::WHITE, 13.0);
        }
    }
}

pub fn render(app: &mut ZeusApp, ui: &mut egui::Ui) {
    let mut trigger_edit_last = false;
    let mut copy_toast: Option<String> = None;

    egui::CentralPanel::default().show(ui, |ui| {
        let available_height = ui.available_height();
        let attach_extra = if app.attached_files.is_empty() { 0.0 } else { 26.0 };
        let bottom_bar_height = 114.0 + attach_extra;
        let chat_height = (available_height - bottom_bar_height).max(80.0);

        egui::ScrollArea::vertical()
            .id_salt("messages_scroll")
            .max_height(chat_height)
            .stick_to_bottom(app.auto_scroll)
            .show(ui, |ui| {
                if let Some(convo) = app.current_conversation() {
                    let last_user_idx = convo
                        .messages
                        .iter()
                        .rposition(|m| m.role == MessageRole::User);

                    for (msg_idx, msg) in convo.messages.iter().enumerate() {
                        ui.add_space(6.0);
                        match msg.role {
                            MessageRole::User => {
                                let panel_bg = ui.visuals().panel_fill;
                                let user_card_bg = egui::Color32::from_rgb(
                                    panel_bg.r().saturating_add(15),
                                    panel_bg.g().saturating_add(15),
                                    panel_bg.b().saturating_add(18),
                                );

                                egui::Frame::new()
                                    .fill(user_card_bg)
                                    .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(52, 54, 62)))
                                    .corner_radius(8u8)
                                    .inner_margin(10i8)
                                    .show(ui, |ui| {
                                        ui.horizontal(|ui| {
                                            ui.label(
                                                egui::RichText::new("👤 Você")
                                                    .strong()
                                                    .color(egui::Color32::from_rgb(78, 204, 163)),
                                            );
                                            ui.label(
                                                egui::RichText::new(&msg.timestamp)
                                                    .size(10.0)
                                                    .color(egui::Color32::from_rgb(140, 150, 160)),
                                            );
                                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                if ui.small_button("📋").on_hover_text("Copiar mensagem").clicked() {
                                                    ui.ctx().copy_text(msg.content.clone());
                                                    copy_toast = Some("Mensagem copiada.".to_string());
                                                }
                                                if !app.is_running && Some(msg_idx) == last_user_idx {
                                                    if ui
                                                        .small_button("✏️ Editar")
                                                        .on_hover_text("Editar e reenviar esta instrução")
                                                        .clicked()
                                                    {
                                                        trigger_edit_last = true;
                                                    }
                                                }
                                            });
                                        });
                                        ui.add_space(4.0);
                                        ui.label(
                                            egui::RichText::new(&msg.content)
                                                .color(egui::Color32::from_rgb(235, 240, 245)),
                                        );
                                    });
                            }
                            MessageRole::Zeus => {
                                egui::Frame::new()
                                    .fill(egui::Color32::from_rgb(12, 14, 18))
                                    .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(45, 48, 58)))
                                    .corner_radius(8u8)
                                    .inner_margin(10i8)
                                    .show(ui, |ui| {
                                        ui.horizontal(|ui| {
                                            ui.label(
                                                egui::RichText::new("⚡ Zeus")
                                                    .strong()
                                                    .color(egui::Color32::from_rgb(100, 180, 255)),
                                            );
                                            ui.label(
                                                egui::RichText::new(&msg.timestamp)
                                                    .size(10.0)
                                                    .color(egui::Color32::GRAY),
                                            );
                                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                if ui.small_button("📋 Copiar Tudo").on_hover_text("Copiar resposta completa").clicked() {
                                                    ui.ctx().copy_text(msg.content.clone());
                                                    copy_toast = Some("Resposta copiada.".to_string());
                                                }
                                            });
                                        });

                                        if !msg.tool_calls.is_empty() {
                                            ui.add_space(4.0);
                                            for (tc_idx, tc) in msg.tool_calls.iter().enumerate() {
                                                let badge = if !tc.finished {
                                                    "⏳"
                                                } else if tc.error.is_some() {
                                                    "❌"
                                                } else {
                                                    "✅"
                                                };
                                                let header = format!("{} 🔧 {}", badge, tc.name);
                                                egui::CollapsingHeader::new(
                                                    egui::RichText::new(header)
                                                        .monospace()
                                                        .size(11.5)
                                                        .color(egui::Color32::from_rgb(235, 200, 120)),
                                                )
                                                .id_salt(("tool_card", msg_idx, tc_idx))
                                                .default_open(!tc.finished || tc.error.is_some())
                                                .show(ui, |ui| {
                                                    if !tc.arguments.is_empty() {
                                                        ui.label(
                                                            egui::RichText::new(format!("Args: {}", tc.arguments))
                                                                .monospace()
                                                                .size(11.0)
                                                                .color(egui::Color32::from_rgb(175, 190, 210)),
                                                        );
                                                    }
                                                    if !tc.output_lines.is_empty() {
                                                        ui.label(
                                                            egui::RichText::new(tc.output_lines.join("\n"))
                                                                .monospace()
                                                                .size(11.0)
                                                                .color(egui::Color32::from_rgb(200, 220, 200)),
                                                        );
                                                    }
                                                    if let Some(err) = &tc.error {
                                                        ui.label(
                                                            egui::RichText::new(format!("Erro: {}", err))
                                                                .size(11.0)
                                                                .color(egui::Color32::from_rgb(255, 130, 130)),
                                                        );
                                                    } else if let Some(res) = &tc.result {
                                                        ui.label(
                                                            egui::RichText::new(format!("Resultado: {}", res))
                                                                .monospace()
                                                                .size(11.0)
                                                                .color(egui::Color32::from_rgb(160, 225, 180)),
                                                        );
                                                    }
                                                });
                                            }
                                        }

                                        if !msg.content.trim().is_empty() {
                                            ui.add_space(6.0);
                                            let segments = parse_content_segments(&msg.content);
                                            for seg in segments {
                                                match seg {
                                                    ContentSegment::MarkdownBlock(text) => {
                                                        render_markdown_block(ui, &text);
                                                    }
                                                    ContentSegment::CodeBlock { lang, code, closed } => {
                                                        ui.add_space(3.0);
                                                        egui::Frame::new()
                                                            .fill(egui::Color32::from_rgb(6, 8, 12))
                                                            .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(50, 56, 70)))
                                                            .corner_radius(6u8)
                                                            .inner_margin(8i8)
                                                            .show(ui, |ui| {
                                                                ui.horizontal(|ui| {
                                                                    let title = if closed {
                                                                        format!("📄 {}", lang)
                                                                    } else {
                                                                        format!("📄 {} (streaming...)", lang)
                                                                    };
                                                                    ui.label(
                                                                        egui::RichText::new(title)
                                                                            .monospace()
                                                                            .size(11.0)
                                                                            .color(egui::Color32::from_rgb(130, 200, 255)),
                                                                    );
                                                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                                        if ui.small_button("📋 Copiar Código").clicked() {
                                                                            ui.ctx().copy_text(code.clone());
                                                                            copy_toast = Some("Código copiado.".to_string());
                                                                        }
                                                                    });
                                                                });
                                                                ui.add_space(3.0);
                                                                ui.label(
                                                                    egui::RichText::new(&code)
                                                                        .monospace()
                                                                        .size(11.5)
                                                                        .color(egui::Color32::from_rgb(225, 235, 245)),
                                                                );
                                                            });
                                                        ui.add_space(3.0);
                                                    }
                                                }
                                            }
                                        }
                                    });
                            }
                            MessageRole::System => {
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new(format!("ℹ️ {}", msg.content))
                                            .italics()
                                            .size(12.0)
                                            .color(egui::Color32::from_rgb(140, 160, 180)),
                                    );
                                });
                            }
                            MessageRole::Error => {
                                egui::Frame::new()
                                    .fill(egui::Color32::from_rgb(60, 25, 25))
                                    .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(120, 40, 40)))
                                    .corner_radius(8u8)
                                    .inner_margin(8i8)
                                    .show(ui, |ui| {
                                        ui.horizontal(|ui| {
                                            ui.label(
                                                egui::RichText::new("❌ Erro")
                                                    .strong()
                                                    .color(egui::Color32::from_rgb(235, 87, 87)),
                                            );
                                            ui.label(
                                                egui::RichText::new(&msg.timestamp)
                                                    .size(10.0)
                                                    .color(egui::Color32::GRAY),
                                            );
                                        });
                                        ui.add_space(2.0);
                                        ui.label(
                                            egui::RichText::new(&msg.content)
                                                .color(egui::Color32::from_rgb(255, 120, 120)),
                                        );
                                    });
                            }
                        }
                    }
                }
            });

        ui.separator();

        // Chips de arquivos anexados
        if !app.attached_files.is_empty() {
            let mut remove_attach: Option<usize> = None;
            ui.horizontal_wrapped(|ui| {
                for (idx, p) in app.attached_files.iter().enumerate() {
                    let fname = p
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| p.display().to_string());
                    ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new(format!("📎 {}", fname))
                                .size(11.0)
                                .color(egui::Color32::from_rgb(160, 220, 255)),
                        );
                        if ui.small_button("✖").clicked() {
                            remove_attach = Some(idx);
                        }
                    });
                }
            });
            if let Some(idx) = remove_attach {
                app.attached_files.remove(idx);
            }
        }

        // Linha 1: Input Multilinha + Anexar + Botão Enviar / Parar
        let mut trigger_send = false;

        ui.horizontal(|ui| {
            let input_width = (ui.available_width() - 155.0).max(100.0);
            let input_response = ui.add_sized(
                [input_width, 48.0],
                egui::TextEdit::multiline(&mut app.input_text)
                    .hint_text("Digite sua instrução ou /comando (Enter envia, Shift+Enter quebra linha)...")
                    .lock_focus(true)
                    .desired_rows(2),
            );

            if input_response.has_focus() {
                if ui.input(|i| i.key_pressed(egui::Key::ArrowUp)) {
                    app.navigate_history_up();
                }
                if ui.input(|i| i.key_pressed(egui::Key::ArrowDown)) {
                    app.navigate_history_down();
                }
                if ui.input(|i| i.key_pressed(egui::Key::Enter) && !i.modifiers.shift && !i.modifiers.ctrl) {
                    if app.input_text.ends_with('\n') {
                        app.input_text.pop();
                    }
                    trigger_send = true;
                }
            }

            if ui
                .add_sized([34.0, 48.0], egui::Button::new("📎"))
                .on_hover_text("Anexar arquivos do projeto ao prompt")
                .clicked()
            {
                let picked = ZeusApp::pick_files(&app.current_dir);
                for p in picked {
                    if !app.attached_files.contains(&p) {
                        app.attached_files.push(p);
                    }
                }
            }

            if app.is_running {
                if ui
                    .add_sized([105.0, 48.0], egui::Button::new("⏹ Parar"))
                    .clicked()
                {
                    app.cancel_execution();
                }
            } else if ui
                .add_sized([105.0, 48.0], egui::Button::new("Enviar ↵"))
                .clicked()
            {
                trigger_send = true;
            }
        });

        if trigger_send {
            app.send_message();
        }

        ui.add_space(4.0);

        // Linha 2: Barra inferior - Modelo, Raciocínio (esquerda) e Modo (direita)
        ui.scope(|ui| {
            let bg = ui.visuals().panel_fill;
            let visuals = ui.visuals_mut();

            visuals.widgets.inactive.weak_bg_fill = bg;
            visuals.widgets.inactive.bg_fill = bg;
            visuals.widgets.inactive.bg_stroke = egui::Stroke::NONE;

            visuals.widgets.hovered.weak_bg_fill = bg;
            visuals.widgets.hovered.bg_fill = bg;
            visuals.widgets.hovered.bg_stroke = egui::Stroke::NONE;

            visuals.widgets.active.weak_bg_fill = bg;
            visuals.widgets.active.bg_fill = bg;
            visuals.widgets.active.bg_stroke = egui::Stroke::NONE;

            ui.horizontal(|ui| {
                // 1. MODELO
                let model_label = egui::RichText::new(format!("{} ▾", app.selected_model))
                    .color(egui::Color32::from_rgb(210, 220, 235))
                    .size(12.0);
                ui.menu_button(model_label, |ui| {
                    ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                    ui.set_min_width(320.0);
                    let provider_display = app
                        .catalog
                        .as_ref()
                        .and_then(|c| c.providers.iter().find(|p| p.id == app.current_provider))
                        .map(|p| p.name.as_str())
                        .unwrap_or_else(|| provider_display_name(&app.current_provider));
                    ui.label(
                        egui::RichText::new(format!("🌐 Modelos {}", provider_display))
                            .strong()
                            .color(egui::Color32::from_rgb(100, 200, 255)),
                    );
                    ui.separator();

                    let available_models: Vec<(String, String)> = if let Some(cat) = &app.catalog {
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

                    let mut selected_new_model: Option<String> = None;
                    egui::ScrollArea::vertical()
                        .id_salt("models_menu_scroll")
                        .max_height(320.0)
                        .show(ui, |ui| {
                            for (mod_id, mod_label) in &available_models {
                                let is_sel = &app.selected_model == mod_id;
                                let item_text = format!("{} — {}", mod_id, mod_label);
                                if ui.selectable_label(is_sel, item_text).clicked() {
                                    selected_new_model = Some(mod_id.clone());
                                    ui.close();
                                }
                            }
                        });
                    if let Some(m) = selected_new_model {
                        app.selected_model = m;
                        app.save_state_now();
                    }
                });

                ui.add_space(8.0);

                // 2. RACIOCÍNIO (padronizado)
                let reasoning_label = egui::RichText::new(format!("{} ▾", app.selected_reasoning))
                    .color(egui::Color32::from_rgb(210, 220, 235))
                    .size(12.0);
                ui.menu_button(reasoning_label, |ui| {
                    ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                    ui.set_min_width(180.0);
                    ui.label(
                        egui::RichText::new("⚡ Esforço de Raciocínio")
                            .strong()
                            .color(egui::Color32::from_rgb(230, 190, 120)),
                    );
                    ui.separator();
                    for opt in ["Mínimo", "Baixo", "Médio", "Alto"] {
                        if ui.selectable_label(app.selected_reasoning == opt, opt).clicked() {
                            app.selected_reasoning = opt.to_string();
                            app.save_state_now();
                            ui.close();
                        }
                    }
                });

                // 3. MODO (direita)
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let mode_label = egui::RichText::new(format!("{} ▾", app.selected_mode.label()))
                        .color(egui::Color32::from_rgb(210, 220, 235))
                        .size(12.0);
                    ui.menu_button(mode_label, |ui| {
                        ui.visuals_mut().widgets = egui::Visuals::dark().widgets;
                        ui.set_min_width(320.0);
                        ui.label(
                            egui::RichText::new("🛡️ Modos do Zeus")
                                .strong()
                                .color(egui::Color32::from_rgb(255, 200, 100)),
                        );
                        ui.separator();

                        let all_modes = [
                            ZeusMode::Sandbox,
                            ZeusMode::Terminal,
                            ZeusMode::Auto,
                            ZeusMode::DryRun,
                            ZeusMode::ReadOnly,
                        ];

                        for m in all_modes {
                            let is_active = app.selected_mode == m;
                            ui.horizontal(|ui| {
                                if ui.selectable_label(is_active, m.label()).clicked() {
                                    app.selected_mode = m;
                                    app.save_state_now();
                                    ui.close();
                                }
                                ui.label(
                                    egui::RichText::new(m.description())
                                        .size(11.0)
                                        .color(egui::Color32::from_rgb(160, 170, 180)),
                                );
                            });
                        }
                    });
                });
            });
        });
    });

    if trigger_edit_last {
        app.edit_last_user_message();
    }
    if let Some(msg) = copy_toast {
        app.show_toast(msg);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_content_segments() {
        let content = "Aqui está o código:\n```python\nprint('hello')\n```\nFim da mensagem.";
        let segments = parse_content_segments(content);

        assert_eq!(segments.len(), 3);
        match &segments[0] {
            ContentSegment::MarkdownBlock(t) => assert!(t.contains("Aqui está o código:")),
            _ => panic!("Esperado segmento markdown"),
        }
        match &segments[1] {
            ContentSegment::CodeBlock { lang, code, closed } => {
                assert_eq!(lang, "python");
                assert_eq!(code, "print('hello')");
                assert!(*closed);
            }
            _ => panic!("Esperado bloco de código"),
        }
        match &segments[2] {
            ContentSegment::MarkdownBlock(t) => assert!(t.contains("Fim da mensagem.")),
            _ => panic!("Esperado segmento markdown"),
        }
    }

    #[test]
    fn test_parse_unclosed_streaming_code_block() {
        let content = "Gerando:\n```rust\nfn main() {";
        let segments = parse_content_segments(content);
        assert_eq!(segments.len(), 2);
        match &segments[1] {
            ContentSegment::CodeBlock { lang, code, closed } => {
                assert_eq!(lang, "rust");
                assert_eq!(code, "fn main() {");
                assert!(!*closed);
            }
            _ => panic!("Esperado bloco de código aberto"),
        }
    }
}
