package BLOSSM.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * Time-series payload for the dashboard (Chart.js).
 *
 * Hub readings populate: labels, lux, brightness, humidity, temperature,
 *                        dominantChannel.
 * Plant readings populate: labels, temperature, soilMoisture, soilConductivity,
 *                          battery.
 *
 * Unused arrays are omitted from the JSON via @JsonInclude(NON_EMPTY) so the
 * front-end can detect which series are available.
 */
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class ReadingJson {

    private static final DateTimeFormatter LABEL_FMT =
            DateTimeFormatter.ofPattern("HH:mm");

    // Shared
    private List<String> labels = new ArrayList<>();

    // Hub series
    private List<Double>  lux              = new ArrayList<>();
    private List<Integer> brightness       = new ArrayList<>();
    private List<Double>  humidity         = new ArrayList<>();
    private List<Double>  temperature      = new ArrayList<>();
    private List<String>  dominantChannel  = new ArrayList<>();

    // Plant series
    private List<Double> soilMoisture     = new ArrayList<>();
    private List<Double> soilConductivity = new ArrayList<>();
    private List<Double> battery          = new ArrayList<>();

    public ReadingJson() { }

    // ── Factories ───────────────────────────────────────

    public static ReadingJson empty() {
        return new ReadingJson();
    }

    public static ReadingJson fromHub(List<Hub> readings) {
        ReadingJson out = new ReadingJson();
        for (Hub r : readings) {
            out.labels.add(formatLabel(r.getTimestamp()));
            out.lux.add(r.getLux());
            out.brightness.add(r.getBrightness());
            out.humidity.add(r.getHumidity());
            out.temperature.add(r.getTemperature());
            out.dominantChannel.add(r.getDominantChannel());
        }
        return out;
    }

    public static ReadingJson fromPlant(List<Plant> readings) {
        ReadingJson out = new ReadingJson();
        for (Plant p : readings) {
            out.labels.add(formatLabel(p.getTimestamp()));
            out.temperature.add(p.getTemperature());
            out.soilMoisture.add(p.getSoilMoisture());
            out.soilConductivity.add(p.getSoilConductivity());
            out.battery.add(p.getBattery());
        }
        return out;
    }

    private static String formatLabel(LocalDateTime ts) {
        return ts == null ? "" : ts.format(LABEL_FMT);
    }

    // ── Getters (Jackson) ───────────────────────────────

    public List<String>  getLabels()           { return labels; }
    public List<Double>  getLux()              { return lux; }
    public List<Integer> getBrightness()       { return brightness; }
    public List<Double>  getHumidity()         { return humidity; }
    public List<Double>  getTemperature()      { return temperature; }
    public List<String>  getDominantChannel()  { return dominantChannel; }
    public List<Double>  getSoilMoisture()     { return soilMoisture; }
    public List<Double>  getSoilConductivity() { return soilConductivity; }
    public List<Double>  getBattery()          { return battery; }
}