mod app;
mod config;
mod data;
mod process;
mod state;
mod ui;

use app::ZeusApp;
use eframe::egui;

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([960.0, 640.0])
            .with_min_inner_size([640.0, 480.0])
            .with_title("Zeus Desktop"),
        ..Default::default()
    };

    eframe::run_native(
        "Zeus Desktop",
        native_options,
        Box::new(|cc| Ok(Box::new(ZeusApp::new(cc)))),
    )
}
