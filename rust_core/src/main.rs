use std::env;

mod telemetry;
mod scanner;
mod grep;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: agent-rust-core <telemetry|scan|grep> [args...]");
        std::process::exit(1);
    }

    let command = &args[1];
    match command.as_str() {
        "telemetry" => {
            let data = telemetry::collect_telemetry();
            println!("{}", serde_json::to_string_pretty(&data).unwrap());
        }
        "scan" => {
            let root = args.get(2).map(|s| s.as_str()).unwrap_or(".");
            let depth = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(4);
            let limit = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(500);
            let data = scanner::scan_directory(root, depth, limit);
            println!("{}", serde_json::to_string_pretty(&data).unwrap());
        }
        "grep" => {
            let root = args.get(2).map(|s| s.as_str()).unwrap_or(".");
            let query = args.get(3).map(|s| s.as_str()).unwrap_or("");
            let is_regex = args.get(4).map(|s| s == "true" || s == "1").unwrap_or(false);
            let limit = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(100);
            let data = grep::grep_code(root, query, is_regex, limit);
            println!("{}", serde_json::to_string_pretty(&data).unwrap());
        }
        other => {
            eprintln!("Unknown command: {}", other);
            std::process::exit(1);
        }
    }
}
