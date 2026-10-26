use std::io::{self, Read};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let log = convlog::tenhou::Log::from_json_str(&input)?;
    let events = convlog::tenhou_to_mjai(&log)?;
    for event in events { println!("{}", serde_json::to_string(&event)?); }
    Ok(())
}
