package BLOSSM.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * DTO that shapes historical data into the format Chart.js expects.
 *
 * Never stored in the database — built by services, serialised to JSON,
 * and consumed by the browser's JavaScript.
 *
 * Uses @JsonInclude so that plant-only fields (temperature, etc.) don't
 * appear in hub JSON, and vice versa.
 *
 * ── Plant JSON shape ──────────────────────
 * {
 *   "labels":           ["08:00","08:05"],
 *   "temperature":      [22.5, 23.1],
 *   "soilMoisture":     [45.0, 44.2],
 *   "soilConductivity": [1.20, 1.25]
 * }
 *
 * ── Hub JSON shape ────────────────────────
 * {
 *   "labels":   ["08:00","08:05"],
 *   "light":    [850.0, 920.0],
 *   "humidity": [62.0, 60.5]
 * }
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ReadingJson(
        List<String> labels,
        List<Double> temperature,
        List<Double> soilMoisture,
        List<Double> soilConductivity,
        List<Double> light,
        List<Double> humidity
) {

    // ── Formatters ──────────────────────────────────────

    private static final DateTimeFormatter TIME_ONLY =
            DateTimeFormatter.ofPattern("HH:mm");

    private static final DateTimeFormatter DATE_TIME =
            DateTimeFormatter.ofPattern("MMM dd HH:mm");

    // ── Factory: build from a list of Plant readings ────

    public static ReadingJson fromPlants(List<Plant> readings) {
        List<String> labels         = new ArrayList<>();
        List<Double> temps          = new ArrayList<>();
        List<Double> moistures      = new ArrayList<>();
        List<Double> conductivities = new ArrayList<>();

        for (Plant r : readings) {
            if (r.getTimestamp() == null) continue;          // skip registration rows
            if (r.getTemperature() == null
                    && r.getSoilMoisture() == null
                    && r.getSoilConductivity() == null) continue;

            labels.add(r.getTimestamp().format(TIME_ONLY));
            temps.add(r.getTemperature());
            moistures.add(r.getSoilMoisture());
            conductivities.add(r.getSoilConductivity());
        }

        return new ReadingJson(
                labels, temps, moistures, conductivities,
                null,   // light    → omitted from JSON
                null    // humidity → omitted from JSON
        );
    }

    // ── Factory: build from a list of Hub readings ──────

    public static ReadingJson fromHub(List<Hub> readings) {
        List<String> labels     = new ArrayList<>();
        List<Double> lights     = new ArrayList<>();
        List<Double> humidities = new ArrayList<>();

        for (Hub r : readings) {
            labels.add(r.getTimestamp().format(TIME_ONLY));
            lights.add(r.getLight());
            humidities.add(r.getHumidity());
        }

        return new ReadingJson(
                labels,
                null,   // temperature      → omitted
                null,   // soilMoisture     → omitted
                null,   // soilConductivity → omitted
                lights,
                humidities
        );
    }

    // ── Empty instance for when there's no data ─────────

    public static ReadingJson empty() {
        return new ReadingJson(
                List.of(), null, null, null, null, null
        );
    }
}