use serde::{Deserialize, Serialize};
use sysinfo::{CpuRefreshKind, Disks, MemoryRefreshKind, RefreshKind, System};

#[derive(Serialize, Deserialize, Debug)]
pub struct CpuCoreInfo {
    pub name: String,
    pub usage_percent: f32,
    pub frequency_mhz: u64,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct DiskInfo {
    pub mount_point: String,
    pub name: String,
    pub total_space_gb: f64,
    pub available_space_gb: f64,
    pub file_system: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub cpu_usage: f32,
    pub memory_mb: f64,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct SystemTelemetry {
    pub os_name: String,
    pub os_version: String,
    pub hostname: String,
    pub cpu_brand: String,
    pub total_memory_gb: f64,
    pub used_memory_gb: f64,
    pub free_memory_gb: f64,
    pub memory_usage_percent: f64,
    pub cpu_cores: Vec<CpuCoreInfo>,
    pub disks: Vec<DiskInfo>,
    pub top_processes: Vec<ProcessInfo>,
}

pub fn collect_telemetry() -> SystemTelemetry {
    let mut sys = System::new_with_specifics(
        RefreshKind::new()
            .with_cpu(CpuRefreshKind::everything())
            .with_memory(MemoryRefreshKind::everything())
            .with_processes(sysinfo::ProcessRefreshKind::everything()),
    );
    // Refresh twice for accurate CPU metrics
    std::thread::sleep(sysinfo::MINIMUM_CPU_UPDATE_INTERVAL);
    sys.refresh_cpu_all();
    sys.refresh_memory();
    sys.refresh_processes();

    let total_mem = sys.total_memory() as f64 / 1_073_741_824.0;
    let used_mem = sys.used_memory() as f64 / 1_073_741_824.0;
    let free_mem = sys.free_memory() as f64 / 1_073_741_824.0;
    let mem_percent = if total_mem > 0.0 { (used_mem / total_mem) * 100.0 } else { 0.0 };

    let cpu_brand = sys.cpus().first().map(|c| c.brand().to_string()).unwrap_or_else(|| "Unknown CPU".into());

    let cpu_cores: Vec<CpuCoreInfo> = sys.cpus().iter().enumerate().map(|(idx, cpu)| {
        CpuCoreInfo {
            name: format!("Core #{}", idx),
            usage_percent: cpu.cpu_usage(),
            frequency_mhz: cpu.frequency(),
        }
    }).collect();

    let disks_obj = Disks::new_with_refreshed_list();
    let disks: Vec<DiskInfo> = disks_obj.iter().map(|d| {
        DiskInfo {
            mount_point: d.mount_point().to_string_lossy().to_string(),
            name: d.name().to_string_lossy().to_string(),
            total_space_gb: d.total_space() as f64 / 1_073_741_824.0,
            available_space_gb: d.available_space() as f64 / 1_073_741_824.0,
            file_system: d.file_system().to_string_lossy().to_string(),
        }
    }).collect();

    let mut proc_list: Vec<ProcessInfo> = sys.processes().iter().map(|(pid, proc_entry)| {
        ProcessInfo {
            pid: pid.as_u32(),
            name: proc_entry.name().to_string(),
            cpu_usage: proc_entry.cpu_usage(),
            memory_mb: proc_entry.memory() as f64 / 1_048_576.0,
        }
    }).collect();

    proc_list.sort_by(|a, b| b.memory_mb.partial_cmp(&a.memory_mb).unwrap_or(std::cmp::Ordering::Equal));
    proc_list.truncate(10);

    SystemTelemetry {
        os_name: System::name().unwrap_or_else(|| "Windows".into()),
        os_version: System::os_version().unwrap_or_else(|| "11".into()),
        hostname: System::host_name().unwrap_or_else(|| "localhost".into()),
        cpu_brand,
        total_memory_gb: (total_mem * 100.0).round() / 100.0,
        used_memory_gb: (used_mem * 100.0).round() / 100.0,
        free_memory_gb: (free_mem * 100.0).round() / 100.0,
        memory_usage_percent: (mem_percent * 10.0).round() / 10.0,
        cpu_cores,
        disks,
        top_processes: proc_list,
    }
}
