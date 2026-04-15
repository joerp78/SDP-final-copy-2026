package BLOSSM.model;

public record RFIDReading(
        Long id,
        String timestamp,
        String eventType,
        String epc,
        String userMemory,
        Integer rssi,
        Integer antennaId
) {

    public Double getTemperatureC() {
        if (userMemory() == null || userMemory().length() < 4) {
            return null;
        }

        try {
            // Take first 4 chars, then drop the first nibble
            String hex = userMemory().substring(0, 4).substring(1);

            int value = Integer.parseInt(hex, 16);

            return value / 10.0;
        } catch (Exception e) {
            return null;
        }
    }
}
