package rfid.model;

public record RFIDEvent(
        Long id,
        String timestamp,
        String eventType,
        String epc,
        String userMemory,
        Integer rssi,
        Integer antennaId
) {}