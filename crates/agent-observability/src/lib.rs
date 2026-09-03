use tracing_subscriber::EnvFilter;

pub fn init_observability(quiet: bool) {
    let filter = if quiet {
        EnvFilter::new("warn")
    } else {
        EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| EnvFilter::new("info,agent=debug"))
    };

    let _ = tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .try_init();
}
