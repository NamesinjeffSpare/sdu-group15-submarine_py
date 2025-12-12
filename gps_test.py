import serial, time

ser = serial.Serial("/dev/serial0", 9600, timeout=1)

last = time.time()
while True:
    line = ser.readline().decode("ascii", errors="ignore").strip()
    if not line:
        continue

    if line.startswith("$") and ("GGA" in line or "GSA" in line or "RMC" in line):
        print(line)

        # Simple human hint for GGA/RMC
        if "GGA" in line:
            parts = line.split(",")
            # GGA field 6 = fix quality (0 = none, 1 = GPS fix, 2 = DGPS, etc.)
            # field 7 = satellites used
            fq = parts[6] if len(parts) > 6 else "?"
            sats = parts[7] if len(parts) > 7 else "?"
            print("  -> GGA fix_quality:", fq, "sats_used:", sats)
        if "RMC" in line:
            parts = line.split(",")
            # RMC field 2 = status (A=active, V=void)
            status = parts[2] if len(parts) > 2 else "?"
            print("  -> RMC status:", status)
