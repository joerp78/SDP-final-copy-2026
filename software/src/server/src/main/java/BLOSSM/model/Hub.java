package BLOSSM.model;

import jakarta.persistence.*;
import java.time.Duration;
import java.time.LocalDateTime;

@Entity
@Table(name = "hub_readings", indexes = {
        @Index(name = "idx_hub_timestamp", columnList = "timestamp")
})
public class Hub {

    // ── Persisted fields ────────────────────────────────

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Double humidity;     // %
    private Double temperature;  // deg C

    // AS7343 spectral readings
    private Double  lux;                 // estimated illuminance (R/G/B weighted)
    private Integer brightness;          // raw R+G+B sum from AS7343
    private String  colorLabel;          // e.g. "white / neutral", "red / warm"
    private String  spectrumLabel;       // e.g. "mostly visible light"
    private String  dominantWavelength;  // e.g. "~550 nm"
    private String  dominantChannel;     // e.g. "VIS3"

    /**
     * Full 12-channel raw counts, stored as a JSON object string.
     * Example: {"FZ":12,"FY":18,"FXL":25,"NIR":40,"VIS1":30,...}
     *
     * Stored as TEXT to avoid baking the AS7343's channel layout into the
     * schema - if the sensor is ever swapped, only the column contents change.
     */
    @Lob
    @Column(columnDefinition = "TEXT")
    private String channelsJson;

    @Column(nullable = false)
    private LocalDateTime timestamp;

    // ── Constructors ────────────────────────────────────

    protected Hub() { }

    public Hub(Double temperature,
               Double humidity,
               Double lux,
               Integer brightness,
               String colorLabel,
               String spectrumLabel,
               String dominantWavelength,
               String dominantChannel,
               String channelsJson,
               LocalDateTime timestamp) {
        this.temperature        = temperature;
        this.humidity           = humidity;
        this.lux                = lux;
        this.brightness         = brightness;
        this.colorLabel         = colorLabel;
        this.spectrumLabel      = spectrumLabel;
        this.dominantWavelength = dominantWavelength;
        this.dominantChannel    = dominantChannel;
        this.channelsJson       = channelsJson;
        this.timestamp          = timestamp;
    }

    // ── Lifecycle callback ──────────────────────────────

    @PrePersist
    protected void onCreate() {
        if (this.timestamp == null) {
            this.timestamp = LocalDateTime.now();
        }
    }

    // ── Computed getter ─────────────────────────────────

    public String getLastUpdated() {
        if (timestamp == null) return "No data";

        long minutes = Duration.between(timestamp, LocalDateTime.now()).toMinutes();
        if (minutes < 0)  return "Just now";
        if (minutes < 1)  return "Just now";
        if (minutes < 60) return minutes + " min ago";

        long hours = minutes / 60;
        if (hours < 24) return hours + "h ago";

        return (hours / 24) + "d ago";
    }

    // ── Standard getters & setters ──────────────────────

    public Long getId()                              { return id; }
    public void setId(Long id)                       { this.id = id; }

    public Double getHumidity()                      { return humidity; }
    public void setHumidity(Double humidity)         { this.humidity = humidity; }

    public Double getTemperature()                   { return temperature; }
    public void setTemperature(Double temperature)   { this.temperature = temperature; }

    public Double getLux()                           { return lux; }
    public void setLux(Double lux)                   { this.lux = lux; }

    public Integer getBrightness()                   { return brightness; }
    public void setBrightness(Integer brightness)    { this.brightness = brightness; }

    public String getColorLabel()                    { return colorLabel; }
    public void setColorLabel(String colorLabel)     { this.colorLabel = colorLabel; }

    public String getSpectrumLabel()                 { return spectrumLabel; }
    public void setSpectrumLabel(String s)           { this.spectrumLabel = s; }

    public String getDominantWavelength()                 { return dominantWavelength; }
    public void setDominantWavelength(String w)           { this.dominantWavelength = w; }

    public String getDominantChannel()               { return dominantChannel; }
    public void setDominantChannel(String c)         { this.dominantChannel = c; }

    public String getChannelsJson()                  { return channelsJson; }
    public void setChannelsJson(String channelsJson) { this.channelsJson = channelsJson; }

    public LocalDateTime getTimestamp()                         { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp)           { this.timestamp = timestamp; }

    @Override
    public String toString() {
        return "Hub{id=" + id
                + ", temperature=" + temperature
                + ", humidity=" + humidity
                + ", lux=" + lux
                + ", brightness=" + brightness
                + ", dominantChannel=" + dominantChannel
                + ", dominantWavelength=" + dominantWavelength
                + ", colorLabel=" + colorLabel
                + ", spectrumLabel=" + spectrumLabel
                + ", timestamp=" + timestamp + '}';
    }
}